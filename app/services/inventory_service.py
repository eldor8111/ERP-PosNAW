from decimal import Decimal
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
) -> None:
    """FIFO tartibida Batch qoldiqlarini kamaytirish (chiqim/boshqa chiqim turlari uchun)."""
    from app.models.batch import Batch
    q = db.query(Batch).filter(
        Batch.product_id == product_id,
        Batch.quantity > 0,
        Batch.company_id == company_id,
    )
    if warehouse_id is not None:
        q = q.filter(Batch.warehouse_id == warehouse_id)
    batches = q.order_by(Batch.created_at.asc(), Batch.id.asc()).with_for_update().all()
    remaining = quantity
    for batch in batches:
        if remaining <= 0:
            break
        take = min(remaining, batch.quantity)
        batch.quantity -= take
        remaining -= take


def get_or_create_stock(db: Session, product_id: int, warehouse_id: Optional[int] = None) -> StockLevel:
    q = db.query(StockLevel).filter(StockLevel.product_id == product_id)
    if warehouse_id is not None:
        q = q.filter(StockLevel.warehouse_id == warehouse_id)
    # with_for_update() — qatorni DB darajasida bloklaydi (race condition oldini oladi)
    stock = q.with_for_update().first()
    if not stock:
        stock = StockLevel(product_id=product_id, warehouse_id=warehouse_id, quantity=Decimal("0"))
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
) -> StockMovement:
    product = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Mahsulot ID={product_id} topilmadi")

    stock = get_or_create_stock(db, product_id, warehouse_id)
    qty_before = stock.quantity
    stock.quantity += quantity

    # Agar ombor tanlangan bo'lsa va mahsulotda NULL-warehouse StockLevel mavjud bo'lsa — uni ham yangilash
    # (mahsulot avval warehouse_id=None bilan yaratilgan bo'lsa kerak)
    if warehouse_id is not None:
        null_stock = db.query(StockLevel).filter(
            StockLevel.product_id == product_id,
            StockLevel.warehouse_id == None
        ).with_for_update().first()
        if null_stock:
            null_stock.quantity += quantity

    movement = StockMovement(
        product_id=product_id,
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
            warehouse_id=warehouse_id,
            lot_number=lot,
            initial_quantity=quantity,
            quantity=quantity,
            purchase_price=purchase_price,
            company_id=company_id,
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
):
    """
    TZ talabi: minus qoldiqqa yo'l qo'ymaslik — agar qoldiq yetarli bo'lmasa BLOKLASH.
    Agar warehouse_id ko'rsatilmagan bo'lsa, barcha omborlardagi haqiqiy qoldiqdan chegiradi.
    """
    if warehouse_id is not None:
        stock = get_or_create_stock(db, product_id, warehouse_id)

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
        stocks = db.query(StockLevel).filter(
            StockLevel.product_id == product_id,
            StockLevel.quantity > 0
        ).order_by(StockLevel.quantity.desc()).with_for_update().all()

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
            # Agar umuman stock yo'q bo'lsa, bitta dummy stock yaratamiz default warehouse bilan (yo'q bo'lsa warehouse_id=None)
            if not stocks:
                stock = get_or_create_stock(db, product_id, None)
                stocks = [stock]
            
            # Qolgan minus qismini birinchi stockdan yechib qoyamiz
            stocks[0].quantity -= (quantity - total_available)
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
) -> StockMovement:
    stock = get_or_create_stock(db, product_id, warehouse_id)
    qty_before = stock.quantity
    diff = new_quantity - qty_before
    stock.quantity = new_quantity

    movement = StockMovement(
        product_id=product_id,
        type=MovementType.ADJUST,
        qty_before=qty_before,
        qty_after=new_quantity,
        quantity=abs(diff),
        user_id=user_id,
        reason=reason,
    )
    db.add(movement)
    db.flush()
    return movement


def create_chiqim_batch(
    db: Session,
    items,  # type: List[ChiqimBatchItem]
    user_id: int,
    company_id: Optional[int] = None,
) -> int:
    from sqlalchemy import func
    max_ref = db.query(func.max(StockMovement.reference_id)).filter(StockMovement.reference_type == "chiqim").scalar()
    ref_id = (max_ref or 0) + 1

    for item in items:
        reason_parts = [item.type]
        if item.doc_num:
            reason_parts.append(f"Hujjat: {item.doc_num}")
        if item.reason:
            reason_parts.append(item.reason)
        full_reason = " | ".join(reason_parts)

        stock = get_or_create_stock(db, item.product_id, None)
        qty_before = stock.quantity
        new_quantity = max(Decimal("0"), qty_before - item.quantity)
        diff = qty_before - new_quantity
        stock.quantity = new_quantity

        movement = StockMovement(
            product_id=item.product_id,
            type=MovementType.ADJUST,
            qty_before=qty_before,
            qty_after=new_quantity,
            quantity=diff,
            reference_type="chiqim",
            reference_id=ref_id,
            user_id=user_id,
            reason=full_reason,
        )
        db.add(movement)

        # FIFO: chiqim bo'lganda Batch qoldiqlarini ham kamaytirish
        if company_id is not None and diff > 0:
            _deduct_batches_fifo(db, item.product_id, diff, None, company_id)

    db.flush()
    return ref_id


def delete_chiqim_batch(db: Session, reference_id: int, user_id: int, company_id: Optional[int] = None):
    movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "chiqim",
        StockMovement.reference_id == reference_id
    ).all()
    
    if not movements:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chiqim topilmadi")

    for mov in movements:
        stock = get_or_create_stock(db, mov.product_id, None)
        qty_before = stock.quantity
        stock.quantity += mov.quantity

        db.add(StockMovement(
            product_id=mov.product_id,
            type=MovementType.ADJUST,
            qty_before=qty_before,
            qty_after=stock.quantity,
            quantity=mov.quantity,
            reference_type="chiqim_revert",
            reference_id=reference_id,
            user_id=user_id,
            reason=f"Chiqim bekor qilindi (ID: {reference_id})",
        ))

        # FIFO: bekor qilingan chiqimni so'nggi Batch'ga qaytarish
        if company_id is not None and mov.quantity > 0:
            from app.models.batch import Batch
            last_batch = db.query(Batch).filter(
                Batch.product_id == mov.product_id,
                Batch.company_id == company_id,
            ).order_by(Batch.created_at.desc(), Batch.id.desc()).first()
            if last_batch:
                last_batch.quantity += mov.quantity
            else:
                product_obj = db.query(Product).filter(Product.id == mov.product_id).first()
                db.add(Batch(
                    product_id=mov.product_id,
                    warehouse_id=None,
                    lot_number="chiqim-revert",
                    initial_quantity=mov.quantity,
                    quantity=mov.quantity,
                    purchase_price=product_obj.cost_price if product_obj else Decimal("0"),
                    company_id=company_id,
                ))

        db.delete(mov)

    db.flush()
