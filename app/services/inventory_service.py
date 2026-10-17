from decimal import Decimal
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product


def _deduct_batches_fifo(
    db: Session,
    product_id: int,
    quantity: Decimal,
    warehouse_id: Optional[int],
    company_id: int,
    variant_id: Optional[int] = None,
    strict: bool = True,
) -> list[tuple]:
    """FEFO yoki FIFO tartibida Batch qoldiqlarini kamaytirish (chiqim/boshqa chiqim turlari uchun).
    strict=False: partiyalar yetmasa xato bermaydi, borini kamaytiradi — narxsiz kirim
    qilingan (partiyasiz) qoldiqlar uchun.
    Qaytaradi: [(Batch, olingan_miqdor), ...] — haqiqiy yechilgan partiyalar (tannarx hisobi uchun);
    chaqiruvchilar xohlasa e'tiborsiz qoldirishi mumkin."""
    from app.services.batch_allocator import (
        allocate_batches, apply_allocations, is_perishable_product, tashkent_today,
    )

    product = db.query(Product).filter(Product.id == product_id).first()
    # T1.6: yagona qoida — avval shu ombor partiyalari, so'ng omborsiz (NULL) eskilari;
    # perishable kategoriyada muddati o'tganlar chiqariladi va FEFO tartib.
    # (warehouse_id=None — ombor cheklovi yo'q, eski chaqiruvlar uchun)
    allocations, shortfall = allocate_batches(
        db, company_id=company_id, product_id=product_id, variant_id=variant_id,
        warehouse_id=warehouse_id, quantity=quantity,
        perishable=is_perishable_product(product), today=tashkent_today(),
        deduct=not strict,
    )
    if strict and shortfall > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Sotuv uchun yetarli yaroqli mahsulot (yoki yaroqlilik muddati o'tmagan qoldiq) yo'q. Hozirgi imkoniyat: {Decimal(str(quantity)) - shortfall}"
        )
    if strict:
        apply_allocations(allocations)
    return [(a["batch"], a["quantity"]) for a in allocations]


def first_active_warehouse_id(db: Session, company_id: Optional[int]) -> Optional[int]:
    """T1.7: korxonaning birinchi faol ombori (ORDER BY id) — ombor berilmagan oqimlar uchun zaxira."""
    if not company_id:
        return None
    from app.models.warehouse import Warehouse
    row = (
        db.query(Warehouse.id)
        .filter(Warehouse.company_id == company_id, Warehouse.is_active == True)  # noqa: E712
        .order_by(Warehouse.id.asc())
        .first()
    )
    return row[0] if row else None


def get_or_create_stock(
    db: Session,
    product_id: int,
    warehouse_id: Optional[int] = None,
    variant_id: Optional[int] = None,
    allow_null: bool = False,
) -> StockLevel:
    # T1.7: omborsiz (NULL) qoldiq qatori yaratilmaydi — faqat migratsiya/tozalash skripti allow_null=True beradi
    if warehouse_id is None and not allow_null:
        raise HTTPException(status_code=400, detail="Ombor ko'rsatilmagan")
    q = db.query(StockLevel).filter(StockLevel.product_id == product_id)
    if warehouse_id is not None:
        q = q.filter(StockLevel.warehouse_id == warehouse_id)
    if variant_id is not None:
        q = q.filter(StockLevel.variant_id == variant_id)
    else:
        q = q.filter(StockLevel.variant_id.is_(None))
    # with_for_update() — qatorni DB darajasida bloklaydi (race condition oldini oladi)
    stock = q.with_for_update().first()
    if not stock:
        stock = StockLevel(product_id=product_id, variant_id=variant_id, warehouse_id=warehouse_id, quantity=Decimal("0"))
        db.add(stock)
        db.flush()
    return stock


def receive_stock(
    db: Session,
    product_id: int,
    quantity: Decimal,
    user_id: int,
    reason: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    purchase_price: Optional[Decimal] = None,
    company_id: Optional[int] = None,
    variant_id: Optional[int] = None,
    expiry_date: Optional[date] = None,
    production_order_id: Optional[int] = None,
) -> StockMovement:
    product = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Mahsulot ID={product_id} topilmadi")
    if getattr(product, "product_type", "stock") == "sell":
        raise HTTPException(status_code=400, detail=f"Virtual mahsulotga ({product.name}) to'g'ridan-to'g'ri kirim qilish mumkin emas. Asosiy mahsulotiga kirim qiling.")

    stock = get_or_create_stock(db, product_id, warehouse_id, variant_id)
    qty_before = stock.quantity
    stock.quantity += quantity

    # NULL-warehouse StockLevel ni yangilamaymiz — bu double counting muammosini keltirib chiqaradi.

    movement = StockMovement(
        product_id=product_id,
        variant_id=variant_id,
        warehouse_id=warehouse_id,
        type=MovementType.IN,
        qty_before=qty_before,
        qty_after=stock.quantity,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=reference_id,
        user_id=user_id,
        reason=reason,
    )
    db.add(movement)
    db.flush()

    # Manual kirim: purchase_price va company_id berilsa, Batch yaratamiz (FIFO uchun)
    if purchase_price is not None and company_id is not None:
        from app.models.batch import Batch
        lot = f"{reference_type}-{reference_id}" if reference_type and reference_id else "manual"
        batch = Batch(
            product_id=product_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            lot_number=lot,
            initial_quantity=quantity,
            quantity=quantity,
            purchase_price=purchase_price,
            company_id=company_id,
            expiry_date=expiry_date,
            production_order_id=production_order_id,
        )
        db.add(batch)

    return movement


def deduct_stock(
    db: Session,
    product_id: int,
    quantity: Decimal,
    user_id: int,
    reason: Optional[str] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    allow_negative: bool = False,
    variant_id: Optional[int] = None,
):
    """
    TZ talabi: minus qoldiqqa yo'l qo'ymaslik — agar qoldiq yetarli bo'lmasa BLOKLASH.
    Agar warehouse_id ko'rsatilmagan bo'lsa, barcha omborlardagi haqiqiy qoldiqdan chegiradi.
    """
    if warehouse_id is not None:
        stock = get_or_create_stock(db, product_id, warehouse_id, variant_id)

        if not allow_negative and stock.quantity < quantity:
            product = db.query(Product).filter(Product.id == product_id).first()
            name = product.name if product else f"ID={product_id}"
            raise HTTPException(
                status_code=400,
                detail=f"'{name}' mahsuloti qoldig'i yetarli emas. "
                       f"Mavjud: {stock.quantity}, So'ralgan: {quantity}",
            )

        qty_before = stock.quantity
        stock.quantity -= quantity

        movement = StockMovement(
            product_id=product_id,
            variant_id=variant_id,
            warehouse_id=warehouse_id,
            type=MovementType.OUT,
            qty_before=qty_before,
            qty_after=stock.quantity,
            quantity=quantity,
            reference_type=reference_type,
            reference_id=reference_id,
            user_id=user_id,
            reason=reason,
        )
        db.add(movement)
        db.flush()
        return movement
    else:
        q_stocks = db.query(StockLevel).filter(
            StockLevel.product_id == product_id,
            StockLevel.quantity > 0
        )
        if variant_id is not None:
            q_stocks = q_stocks.filter(StockLevel.variant_id == variant_id)
        else:
            q_stocks = q_stocks.filter(StockLevel.variant_id.is_(None))
            
        stocks = q_stocks.order_by(StockLevel.quantity.desc()).with_for_update().all()

        total_available = sum((s.quantity for s in stocks), Decimal("0"))
        if not allow_negative and total_available < quantity:
            product = db.query(Product).filter(Product.id == product_id).first()
            name = product.name if product else f"ID={product_id}"
            raise HTTPException(
                status_code=400,
                detail=f"'{name}' mahsuloti qoldig'i yetarli emas. "
                       f"Mavjud: {total_available}, So'ralgan: {quantity}",
            )

        remaining = quantity
        movements = []
        
        # Agar qoldiq yetarli bo'lmasa lekin allow_negative=True bo'lsa,
        # qoldiq nol bo'lgan omborga minus qilib yozib qoyamiz (yoki birinchi omborga)
        if total_available < quantity and allow_negative:
            # T1.7: umuman qoldiq bo'lmasa — korxonaning birinchi faol omborida qator ochiladi
            # (NULL-omborli "egasiz" qator yaratilmaydi); ombor yo'q bo'lsa 400
            if not stocks:
                company_id = db.query(Product.company_id).filter(Product.id == product_id).scalar()
                fallback_wh_id = first_active_warehouse_id(db, company_id)
                if fallback_wh_id is None:
                    raise HTTPException(status_code=400, detail="Korxonada faol ombor yo'q")
                stock = get_or_create_stock(db, product_id, fallback_wh_id, variant_id)
                stocks = [stock]
            
            diff = quantity - total_available
            qty_before_diff = stocks[0].quantity
            stocks[0].quantity -= diff
            
            wh_note = f"Ombor #{stocks[0].warehouse_id}" if stocks[0].warehouse_id else "No-WH"
            final_reason = f"{reason} ({wh_note})" if reason else wh_note
            
            movement = StockMovement(
                product_id=product_id,
                variant_id=variant_id,
                warehouse_id=stocks[0].warehouse_id,
                type=MovementType.OUT,
                qty_before=qty_before_diff,
                qty_after=stocks[0].quantity,
                quantity=diff,
                reference_type=reference_type,
                reference_id=reference_id,
                user_id=user_id,
                reason=final_reason,
            )
            db.add(movement)
            
            # remaining qismini esa bor qoldiqqa tenglashtiramiz toki for loop oddiy ishlasin
            remaining = total_available
        for stock in stocks:
            if remaining <= 0:
                break
            qty_to_deduct = min(remaining, stock.quantity)
            qty_before = stock.quantity
            stock.quantity -= qty_to_deduct
            remaining -= qty_to_deduct

            wh_note = f"Ombor #{stock.warehouse_id}" if stock.warehouse_id else "No-WH"
            final_reason = f"{reason} ({wh_note})" if reason else wh_note

            movement = StockMovement(
                product_id=product_id,
                variant_id=variant_id,
                warehouse_id=stock.warehouse_id,
                type=MovementType.OUT,
                qty_before=qty_before,
                qty_after=stock.quantity,
                quantity=qty_to_deduct,
                reference_type=reference_type,
                reference_id=reference_id,
                user_id=user_id,
                reason=final_reason,
            )
            db.add(movement)
            movements.append(movement)

        db.flush()
        return movements


def adjust_stock(
    db: Session,
    product_id: int,
    new_quantity: Decimal,
    user_id: int,
    reason: str,
    warehouse_id: Optional[int] = None,
    variant_id: Optional[int] = None,
    company_id: Optional[int] = None,
) -> StockMovement:
    from app.models.product import Product
    from fastapi import HTTPException

    # Ombor majburiy: aks holda get_or_create_stock tasodifiy (yoki NULL-omborli) qator oladi
    if warehouse_id is None:
        raise HTTPException(status_code=400, detail="Omborni tanlang")
    if company_id is None:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")

    p = db.query(Product).filter(
        Product.id == product_id,
        Product.company_id == company_id,
        Product.is_deleted == False,  # noqa: E712
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail=f"Mahsulot ID={product_id} topilmadi")
    if p.product_type in ('sell', 'service'):
        raise HTTPException(status_code=400, detail="Tarkibiy (Kalkulyatsiya) mahsulot qoldig'ini o'zgartirib bo'lmaydi")

    stock = get_or_create_stock(db, product_id, warehouse_id, variant_id)
    qty_before = stock.quantity
    diff = new_quantity - qty_before
    stock.quantity = new_quantity

    movement = StockMovement(
        product_id=product_id,
        variant_id=variant_id,
        warehouse_id=warehouse_id,
        type=MovementType.ADJUST,
        qty_before=qty_before,
        qty_after=new_quantity,
        quantity=abs(diff),
        reference_type="adjustment",
        user_id=user_id,
        reason=reason,
    )
    db.add(movement)
    db.flush()
    return movement


def resolve_chiqim_warehouse(db: Session, user, warehouse_id: Optional[int]) -> int:
    """T1.8: chiqim ombori majburiy. Ko'rsatilsa — korxona/faollik/(non-admin uchun) filial tekshiriladi
    (404/403). Ko'rsatilmasa (eski mijoz) — foydalanuvchi ko'lamida aynan bitta faol ombor bo'lsa shu,
    aks holda 400 "Ombor tanlanmagan"."""
    from app.models.warehouse import Warehouse
    from app.services.tenant_guards import get_company_warehouse
    if warehouse_id:
        return get_company_warehouse(db, user, warehouse_id).id
    q = db.query(Warehouse.id).filter(
        Warehouse.company_id == user.company_id,
        Warehouse.is_active == True,  # noqa: E712
    )
    if user.branch_id:
        q = q.filter(Warehouse.branch_id == user.branch_id)
    ids = [r[0] for r in q.order_by(Warehouse.id.asc()).limit(2).all()]
    if len(ids) == 1:
        return ids[0]
    raise HTTPException(status_code=400, detail="Ombor tanlanmagan")


def _next_chiqim_ref(db: Session) -> int:
    """T1.8: chiqim hujjat raqami — PostgreSQL sequence (parallel so'rovlarda ham noyob);
    sequence bo'lmagan muhitda (testlar/SQLite) max()+1."""
    from sqlalchemy import func, text
    if db.get_bind().dialect.name == "postgresql":
        return int(db.execute(text("SELECT nextval('stock_chiqim_ref_seq')")).scalar())
    max_ref = db.query(func.max(StockMovement.reference_id)).filter(StockMovement.reference_type == "chiqim").scalar()
    return (max_ref or 0) + 1


def create_chiqim_batch(
    db: Session,
    items,  # type: List[ChiqimBatchItem]
    user_id: int,
    company_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    reference_id: Optional[int] = None,
) -> int:
    from app.models.product import ProductConversion, Product
    # T1.8: ombor majburiy — aks holda deduct_stock "eng ko'p qoldiqli" tasodifiy ombordan yechardi
    if not warehouse_id:
        raise HTTPException(status_code=400, detail="Ombor tanlanmagan")
    ref_id = reference_id if reference_id is not None else _next_chiqim_ref(db)

    for item in items:
        reason_parts = [item.type]
        if item.doc_num:
            reason_parts.append(f"Hujjat: {item.doc_num}")
        if item.reason:
            reason_parts.append(item.reason)
        full_reason = " | ".join(reason_parts)

        # Mahsulotni tekshiramiz (begona korxona mahsuloti — 404)
        pq = db.query(Product).filter(Product.id == item.product_id)
        if company_id is not None:
            pq = pq.filter(Product.company_id == company_id)
        product = pq.first()
        if company_id is not None and product is None:
            raise HTTPException(status_code=404, detail=f"Mahsulot ID={item.product_id} topilmadi")
        if product and getattr(product, 'product_type', 'stock') == 'sell':
            # Tarkibiy mahsulot: uning xom-ashyolarini chiqim qilamiz
            conversions = db.query(ProductConversion).filter(ProductConversion.sell_product_id == product.id).all()
            if not conversions:
                raise HTTPException(status_code=400, detail=f"'{product.name}' tarkibiy mahsulot uchun xom-ashyo (konversiya) topilmadi")

            for conv in conversions:
                qty_needed = conv.ratio * item.quantity
                deduct_stock(
                    db=db,
                    product_id=conv.source_product_id,
                    quantity=qty_needed,
                    user_id=user_id,
                    reason=f"{full_reason} (Tarkibiy: {product.name})",
                    reference_type="chiqim",
                    reference_id=ref_id,
                    allow_negative=True,
                    warehouse_id=warehouse_id,
                    variant_id=getattr(item, 'variant_id', None)
                )
                if company_id is not None and qty_needed > 0:
                    # strict=False: import/revizya/qaytarish orqali kirgan partiyasiz qoldiq ham chiqim qilinadi
                    _deduct_batches_fifo(db, conv.source_product_id, qty_needed, warehouse_id, company_id,
                                         variant_id=getattr(item, 'variant_id', None), strict=False)
        else:
            # Oddiy mahsulot
            deduct_stock(
                db=db,
                product_id=item.product_id,
                quantity=item.quantity,
                user_id=user_id,
                reason=full_reason,
                reference_type="chiqim",
                reference_id=ref_id,
                allow_negative=True,
                warehouse_id=warehouse_id,
                variant_id=getattr(item, 'variant_id', None)
            )
            if company_id is not None and item.quantity > 0:
                _deduct_batches_fifo(db, item.product_id, item.quantity, warehouse_id, company_id,
                                     variant_id=getattr(item, 'variant_id', None), strict=False)

    db.flush()
    return ref_id


def active_chiqim_movements(db: Session, company_id: Optional[int], reference_id: int):
    """T1.8: chiqim hujjatining JORIY harakatlari. Bekor qilishda asl harakatlar o'chirilmaydi
    (T1.19), tahrirda esa shu reference_id bilan yangilari yoziladi — shuning uchun oxirgi
    `chiqim_revert` (storno) dan keyingi harakatlargina joriy hisoblanadi."""
    from sqlalchemy import func
    rq = db.query(func.max(StockMovement.id)).join(Product, Product.id == StockMovement.product_id).filter(
        StockMovement.reference_type == "chiqim_revert",
        StockMovement.reference_id == reference_id,
    )
    if company_id is not None:
        rq = rq.filter(Product.company_id == company_id)
    last_revert = rq.scalar() or 0
    q = db.query(StockMovement).join(Product, Product.id == StockMovement.product_id).filter(
        StockMovement.reference_type == "chiqim",
        StockMovement.reference_id == reference_id,
        StockMovement.id > last_revert,
    )
    if company_id is not None:
        q = q.filter(Product.company_id == company_id)
    return q.order_by(StockMovement.id.asc()).all()


def delete_chiqim_batch(db: Session, reference_id: int, user_id: int, company_id: Optional[int] = None):
    movements = active_chiqim_movements(db, company_id, reference_id)

    if not movements:
        # Hujjat umuman yo'qmi yoki allaqachon bekor qilinganmi — farqlaymiz
        eq = db.query(StockMovement.id).join(Product, Product.id == StockMovement.product_id).filter(
            StockMovement.reference_type == "chiqim",
            StockMovement.reference_id == reference_id,
        )
        if company_id is not None:
            eq = eq.filter(Product.company_id == company_id)
        if not eq.first():
            raise HTTPException(status_code=404, detail="Chiqim topilmadi")
        # T1.19: asl harakatlar o'chirilmaydi (tarix saqlanadi) — takroriy bekor qilishda qoldiq ikki marta qaytmaydi
        raise HTTPException(status_code=400, detail="Chiqim allaqachon bekor qilingan")

    # Eski (warehouse_id NULL) harakatlar uchungina zaxira: korxonaning birinchi faol ombori
    fallback_wh_id = first_active_warehouse_id(db, company_id)

    # (mahsulot, variant, ombor) bo'yicha guruhlash — deduct_stock bitta mahsulot uchun bir nechta harakat yozgan bo'lishi mumkin
    totals = {}
    for mov in movements:
        key = (mov.product_id, mov.variant_id, mov.warehouse_id or fallback_wh_id)
        totals[key] = totals.get(key, Decimal("0")) + mov.quantity

    for (product_id, variant_id, wh_id), total_qty in totals.items():
        if total_qty > 0:
            if wh_id is None:
                raise HTTPException(status_code=400, detail="Korxonada faol ombor yo'q")
            receive_stock(
                db=db,
                product_id=product_id,
                quantity=total_qty,
                user_id=user_id,
                reason=f"Chiqim bekor qilindi (ID: {reference_id})",
                reference_type="chiqim_revert",
                reference_id=reference_id,
                warehouse_id=wh_id,
                variant_id=variant_id
            )

            # FIFO: bekor qilingan chiqimni shu ombordagi so'nggi Batch'ga qaytarish
            if company_id is not None:
                from app.models.batch import Batch
                q_last_batch = db.query(Batch).filter(
                    Batch.product_id == product_id,
                    Batch.company_id == company_id,
                    Batch.warehouse_id == wh_id,
                )
                if variant_id is not None:
                    q_last_batch = q_last_batch.filter(Batch.variant_id == variant_id)
                else:
                    q_last_batch = q_last_batch.filter(Batch.variant_id.is_(None))

                last_batch = q_last_batch.order_by(Batch.created_at.desc(), Batch.id.desc()).first()

                if last_batch:
                    last_batch.quantity += total_qty
                else:
                    product_obj = db.query(Product).filter(Product.id == product_id).first()
                    db.add(Batch(
                        product_id=product_id,
                        variant_id=variant_id,
                        warehouse_id=wh_id,
                        lot_number="chiqim-revert",
                        initial_quantity=total_qty,
                        quantity=total_qty,
                        purchase_price=product_obj.cost_price if product_obj else Decimal("0"),
                        company_id=company_id,
                    ))

    db.flush()
