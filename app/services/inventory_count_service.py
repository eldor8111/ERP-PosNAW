from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.inventory import StockLevel
from app.models.inventory_count import CountStatus, InventoryCount, InventoryCountItem
from app.models.product import Product, ProductConversion
from app.models.warehouse import Warehouse
from app.services.document_numbers import next_document_number
from app.services.inventory_service import adjust_stock


def generate_count_number(db: Session, company_id: int, branch_id: Optional[int] = None) -> str:
    """Revizya raqami (T1.14): `IC{YYYYMMDD}-{korxona}-{filial}-{NNNN}`, atomar hisoblagich bilan
    (hujjat o'chirilsa ham raqam qayta ishlatilmaydi)."""
    return next_document_number(db, company_id=company_id, branch_id=branch_id, doc_type="IC")


OPEN_STATUSES = (CountStatus.draft, CountStatus.in_progress)


def find_open_count(db: Session, warehouse_id: int, exclude_id: Optional[int] = None) -> Optional[InventoryCount]:
    """Shu omborda ochiq (draft/in_progress) revizya bo'lsa qaytaradi."""
    q = db.query(InventoryCount).filter(
        InventoryCount.warehouse_id == warehouse_id,
        InventoryCount.status.in_(OPEN_STATUSES),
    )
    if exclude_id is not None:
        q = q.filter(InventoryCount.id != exclude_id)
    return q.order_by(InventoryCount.id.desc()).first()


def open_count_conflict(existing: InventoryCount) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=f"Bu omborda ochiq inventarizatsiya bor: {existing.number} (ID {existing.id})",
    )


def _stock_qty_map(db: Session, warehouse_id: int) -> dict:
    """Ombordagi joriy qoldiqlar: {(product_id, variant_id): quantity}."""
    return {
        (s.product_id, s.variant_id): s.quantity
        for s in db.query(StockLevel).filter(StockLevel.warehouse_id == warehouse_id).all()
    }


def get_company_count(db: Session, count_id: int, company_id: Optional[int],
                      lock: bool = False) -> InventoryCount:
    """Revizyani korxona bo'yicha oladi. company_id=None faqat super_admin uchun (filtrsiz).
    lock=True — qatorni bloklab oladi (parallel yakunlash/o'zgartirishdan himoya)."""
    q = db.query(InventoryCount).filter(InventoryCount.id == count_id)
    if lock:
        q = q.with_for_update().populate_existing()
    if company_id is not None:
        q = q.filter(InventoryCount.warehouse_id.in_(
            db.query(Warehouse.id).filter(Warehouse.company_id == company_id)
        ))
    count = q.first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    return count


def create_inventory_count(db: Session, data, user_id: int, company_id: Optional[int] = None) -> InventoryCount:
    wh_q = db.query(Warehouse).filter(Warehouse.id == data.warehouse_id, Warehouse.is_active == True)
    if company_id is not None:
        wh_q = wh_q.filter(Warehouse.company_id == company_id)
    wh = wh_q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")

    # Bitta omborda bir vaqtda faqat bitta ochiq revizya
    existing = find_open_count(db, data.warehouse_id)
    if existing:
        raise open_count_conflict(existing)

    count = InventoryCount(
        number=generate_count_number(db, company_id or wh.company_id, wh.branch_id),
        warehouse_id=data.warehouse_id,
        note=data.note,
        created_by=user_id,
        status=CountStatus.draft,
    )
    db.add(count)
    try:
        db.flush()
    except IntegrityError:
        # Parallel so'rov (uq_inventory_counts_one_open_per_wh indeksi)
        db.rollback()
        existing = find_open_count(db, data.warehouse_id)
        if existing:
            raise open_count_conflict(existing)
        raise

    # T3.8: tezkor revizya (prepopulate=False) — qatorlar oldindan to'ldirilmaydi, ular keyin
    # update_count_items orqali (system_qty = StockLevel dan) qo'shiladi
    count._items_created = 0
    if not getattr(data, "prepopulate", True):
        return count

    # Load ALL active (non-deleted) products; filter by category if partial count
    products_q = db.query(Product).filter(
        Product.is_deleted == False,
        Product.status == "active",
        Product.product_type != "sell",
        Product.company_id == wh.company_id,
    )
    if data.category_ids:
        products_q = products_q.filter(Product.category_id.in_(data.category_ids))
    products = products_q.order_by(Product.name).all()
    product_ids = [p.id for p in products]

    # Variantli mahsulotlarda har bir variant alohida sanaladi
    from app.models.product_variant import ProductVariant
    variants_by_product: dict = {}
    if product_ids:
        for v in db.query(ProductVariant).filter(ProductVariant.product_id.in_(product_ids)).all():
            variants_by_product.setdefault(v.product_id, []).append(v)

    # Build a map of existing stock levels for this warehouse, keyed by (product_id, variant_id)
    stock_map = _stock_qty_map(db, data.warehouse_id)

    items_to_insert = []
    for product in products:
        variants = variants_by_product.get(product.id)
        if variants:
            for v in variants:
                items_to_insert.append({
                    "count_id": count.id,
                    "product_id": product.id,
                    "variant_id": v.id,
                    "system_qty": stock_map.get((product.id, v.id), 0),
                    "counted_qty": None,
                    "variance": None,
                })
        else:
            items_to_insert.append({
                "count_id": count.id,
                "product_id": product.id,
                "variant_id": None,
                "system_qty": stock_map.get((product.id, None), 0),
                "counted_qty": None,
                "variance": None,
            })
    if items_to_insert:
        db.execute(InventoryCountItem.__table__.insert(), items_to_insert)
    count._items_created = len(items_to_insert)  # javobda len(items) o'rniga (qatorlarni qayta yuklamaslik uchun)

    return count


def start_inventory_count(db: Session, count_id: int, company_id: Optional[int] = None) -> InventoryCount:
    count = get_company_count(db, count_id, company_id)
    if count.status != CountStatus.draft:
        raise HTTPException(status_code=400, detail="Faqat draft holatdagi inventarizatsiyani boshlash mumkin")
    count.status = CountStatus.in_progress
    count.started_at = datetime.now(timezone.utc)

    # Hali sanalmagan qatorlarning system_qty i boshlanish paytidagi joriy qoldiqqa yangilanadi
    stock_map = _stock_qty_map(db, count.warehouse_id)
    for item in count.items:
        if item.counted_qty is None:
            item.system_qty = stock_map.get((item.product_id, item.variant_id), 0)
    db.flush()
    return count


def update_count_items(db: Session, count_id: int, items_data: list, user_id: int,
                       company_id: Optional[int] = None) -> InventoryCount:
    count = get_company_count(db, count_id, company_id, lock=True)
    if count.status not in (CountStatus.draft, CountStatus.in_progress):
        raise HTTPException(status_code=400, detail="Bu holатdagi inventarizatsiyani o'zgartirib bo'lmaydi")

    items_map = {(item.product_id, item.variant_id): item for item in count.items}

    # Mahsulot/variant korxonaga tegishliligi — hech narsa yozilishidan oldin tekshiriladi.
    # company_id=None (super_admin) bo'lsa, ombor egasi korxonasi olinadi.
    from app.models.product_variant import ProductVariant
    owner_company_id = company_id
    if owner_company_id is None:
        owner_company_id = db.query(Warehouse.company_id).filter(Warehouse.id == count.warehouse_id).scalar()
    for item_data in items_data:
        prod_ok = db.query(Product.id).filter(
            Product.id == item_data.product_id,
            Product.company_id == owner_company_id,
        ).first()
        if not prod_ok:
            raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_data.product_id} topilmadi")
        v_id = getattr(item_data, 'variant_id', None)
        if v_id is not None:
            var_ok = db.query(ProductVariant.id).filter(
                ProductVariant.id == v_id,
                ProductVariant.product_id == item_data.product_id,
            ).first()
            if not var_ok:
                raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_data.product_id} topilmadi")

    # Block sell products
    product_ids = [item.product_id for item in items_data]
    if product_ids:
        sell_product = db.query(Product).filter(
            Product.id.in_(product_ids),
            Product.product_type == 'sell'
        ).first()
        if sell_product:
            raise HTTPException(status_code=400, detail="Tarkibiy (Kalkulyatsiya) mahsulotni revizya qilib bo'lmaydi")

    now = datetime.now(timezone.utc)
    stock_map = _stock_qty_map(db, count.warehouse_id)
    for item_data in items_data:
        variant_id = getattr(item_data, 'variant_id', None)
        count_item = items_map.get((item_data.product_id, variant_id))
        current_qty = stock_map.get((item_data.product_id, variant_id), 0)
        if not count_item:
            # Add new item if not in list
            count_item = InventoryCountItem(
                count_id=count_id,
                product_id=item_data.product_id,
                variant_id=variant_id,
                system_qty=current_qty,
            )
            db.add(count_item)
            db.flush()
            items_map[(item_data.product_id, variant_id)] = count_item
        if count_item.counted_qty is None or count_item.counted_qty != item_data.counted_qty:
            # Yangi yoki o'zgargan sanoq: system_qty sanash paytidagi joriy qoldiqqa yangilanadi,
            # shunda yakunlashda delta (counted - system_qty) oradagi sotuv/kirimlarni yo'qotmaydi
            count_item.system_qty = current_qty
            count_item.counted_qty = item_data.counted_qty
            count_item.counted_at = now
            count_item.variance = item_data.counted_qty - count_item.system_qty
        # Qiymat o'zgarmagan bo'lsa (UI hamma qatorni qayta yuboradi) system_qty tegilmaydi
        count_item.variance_reason = getattr(item_data, 'variance_reason', None)

    db.flush()
    return count


def finalize_inventory_count(db: Session, count_id: int, user_id: int,
                             company_id: Optional[int] = None) -> InventoryCount:
    from decimal import Decimal
    from app.models.inventory import MovementType, StockMovement

    # Qatorni bloklaymiz: ikki marta bosish/parallel chaqiruvda delta ikki marta qo'llanmasligi uchun
    count = get_company_count(db, count_id, company_id, lock=True)
    if count.status != CountStatus.in_progress:
        raise HTTPException(status_code=400, detail="Faqat jarayondagi inventarizatsiyani yakunlash mumkin")

    audit_diffs = []
    for item in count.items:
        if item.counted_qty is None:
            continue

        prod = db.query(Product).filter(Product.id == item.product_id).first()
        if prod and (prod.product_type == "sell" or db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == item.product_id
        ).first()):
            continue  # Tarkibiy mahsulot qoldig'i reviziya qilinmaydi

        # Sanash paytidagi qoldiqqa nisbatan farq (delta): oradagi sotuv/kirimlar saqlanadi
        system_qty = item.system_qty if item.system_qty is not None else Decimal("0")
        delta = item.counted_qty - system_qty
        if delta == 0:
            continue  # farq yo'q — harakat yozilmaydi

        # Find the EXACT StockLevel for this product + variant + warehouse,
        # bloklab olamiz — parallel sotuv/prixod bilan to'qnashmasligi uchun
        stock_q = db.query(StockLevel).filter(
            StockLevel.product_id == item.product_id,
            StockLevel.warehouse_id == count.warehouse_id,
        )
        stock_q = stock_q.filter(StockLevel.variant_id == item.variant_id) if item.variant_id is not None \
            else stock_q.filter(StockLevel.variant_id.is_(None))
        stock = stock_q.with_for_update().first()
        if stock is None:
            # No record yet for this warehouse — create one starting at 0
            stock = StockLevel(
                product_id=item.product_id,
                variant_id=item.variant_id,
                warehouse_id=count.warehouse_id,
                quantity=Decimal("0"),
            )
            db.add(stock)
            db.flush()

        qty_before = stock.quantity
        stock.quantity = qty_before + delta

        reason = f"Revizya #{count.number}"
        if stock.quantity < 0:
            reason += f" (ogohlantirish: qoldiq manfiy bo'ldi: {stock.quantity})"

        # Record the movement with the real previous balance
        movement = StockMovement(
            product_id=item.product_id,
            variant_id=item.variant_id,
            warehouse_id=count.warehouse_id,
            type=MovementType.ADJUST,
            qty_before=qty_before,
            qty_after=stock.quantity,
            quantity=abs(delta),
            user_id=user_id,
            reference_type="revision",
            reference_id=count.id,
            reason=reason,
        )
        db.add(movement)
        db.flush()
        audit_diffs.append({
            "product_id": item.product_id, "variant_id": item.variant_id,
            "system_qty": float(system_qty), "counted_qty": float(item.counted_qty), "delta": float(delta),
        })

    count.status = CountStatus.completed
    count.finished_at = datetime.now(timezone.utc)
    db.flush()
    wh = db.get(Warehouse, count.warehouse_id)
    log_action(
        db, "COUNT_FINALIZE", "inventory_count", count.id, user_id=user_id,
        old_values={"status": "in_progress"},
        new_values={"number": count.number, "warehouse_id": count.warehouse_id,
                    "status": "completed", "diff_count": len(audit_diffs), "diffs": audit_diffs},
        company_id=wh.company_id if wh else None, branch_id=wh.branch_id if wh else None,
    )
    return count


def revert_inventory_count(db: Session, count: InventoryCount, user_id: int) -> None:
    """Yakunlangan revizyani qaytaradi (T1.19): asl `revision` harakatlari O'CHIRILMAYDI — farqning teskarisi
    `revision_revert` (ADJUST) harakati bilan yoziladi. Takroriy yakunlash/qaytarishda ikki marta
    qaytarilmasligi uchun faqat sof (asl + storno) ta'sir qaytariladi. Statusni in_progress qiladi."""
    from decimal import Decimal
    from app.models.inventory import MovementType, StockMovement

    movements = db.query(StockMovement).filter(
        StockMovement.reference_type.in_(("revision", "revision_revert")),
        StockMovement.reference_id == count.id,
    ).order_by(StockMovement.id.asc()).all()

    applied: dict = {}
    for mov in movements:
        key = (mov.product_id, mov.variant_id)
        applied[key] = applied.get(key, Decimal(0)) + (Decimal(mov.qty_after) - Decimal(mov.qty_before))

    reverted = []
    for (product_id, variant_id), net_change in applied.items():
        if net_change == 0:
            continue
        stock_q = db.query(StockLevel).filter(
            StockLevel.product_id == product_id,
            StockLevel.warehouse_id == count.warehouse_id,
        )
        stock_q = stock_q.filter(StockLevel.variant_id == variant_id) if variant_id is not None             else stock_q.filter(StockLevel.variant_id.is_(None))
        stock = stock_q.with_for_update().first()
        if stock is None:
            stock = StockLevel(product_id=product_id, variant_id=variant_id,
                               warehouse_id=count.warehouse_id, quantity=Decimal("0"))
            db.add(stock)
            db.flush()
        qty_before = Decimal(stock.quantity or 0)
        stock.quantity = qty_before - net_change
        db.add(StockMovement(
            product_id=product_id, variant_id=variant_id, warehouse_id=count.warehouse_id,
            type=MovementType.ADJUST,
            qty_before=qty_before, qty_after=stock.quantity, quantity=abs(net_change),
            user_id=user_id, reference_type="revision_revert", reference_id=count.id,
            reason=f"Revizya #{count.number} qaytarildi (storno)",
        ))
        reverted.append({"product_id": product_id, "variant_id": variant_id, "delta": float(-net_change)})

    count.status = CountStatus.in_progress
    db.flush()
    wh = db.get(Warehouse, count.warehouse_id)
    log_action(
        db, "COUNT_REVERT", "inventory_count", count.id, user_id=user_id,
        old_values={"status": "completed"},
        new_values={"number": count.number, "warehouse_id": count.warehouse_id,
                    "status": "in_progress", "reverted": reverted},
        company_id=wh.company_id if wh else None, branch_id=wh.branch_id if wh else None,
    )

