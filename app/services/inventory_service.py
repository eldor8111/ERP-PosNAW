from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product


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
) -> StockMovement:
    product = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Mahsulot ID={product_id} topilmadi")

    stock = get_or_create_stock(db, product_id, warehouse_id)
    qty_before = stock.quantity
    stock.quantity += quantity

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
