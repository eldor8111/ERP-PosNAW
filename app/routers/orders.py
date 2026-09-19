from typing import Optional, List
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User  # type: ignore
from app.models.order import Order, OrderStatus  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.product import Product  # type: ignore

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderIn(BaseModel):
    customer_id: int
    product_id: int
    quantity: int
    payment_type: Optional[str] = "cash"
    notes: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    customer_id: int
    branch_id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    status: OrderStatus
    payment_type: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    data: OrderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buyurtma yaratish (Bot/API orqali)."""
    customer = db.query(Customer).filter(
        Customer.id == data.customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    if not customer.branch_id:
        raise HTTPException(status_code=400, detail="Mijozga dokon biriktirilmagan")

    product = db.query(Product).filter(
        Product.id == data.product_id,
        Product.company_id == current_user.company_id,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Miqdor 0 dan katta bo'lishi kerak")

    unit_price = Decimal(str(product.sale_price))
    total_amount = unit_price * data.quantity

    order = Order(
        customer_id=data.customer_id,
        branch_id=customer.branch_id,
        product_id=data.product_id,
        quantity=data.quantity,
        unit_price=unit_price,
        total_amount=total_amount,
        status=OrderStatus.pending,
        payment_type=data.payment_type,
        notes=data.notes,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return order


@router.get("", response_model=List[dict])
def list_orders(
    branch_id: Optional[int] = None,
    status: Optional[OrderStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buyurtmalarni ko'rish (status bo'yicha filter)."""
    query = db.query(Order).join(Customer).filter(
        Customer.company_id == current_user.company_id
    )

    if branch_id:
        query = query.filter(Order.branch_id == branch_id)
    if status:
        query = query.filter(Order.status == status)

    orders = query.order_by(Order.created_at.desc()).all()

    result = []
    for order in orders:
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
        product = db.query(Product).filter(Product.id == order.product_id).first()

        result.append({
            "id": order.id,
            "customer_id": order.customer_id,
            "customer_name": customer.name if customer else "—",
            "customer_phone": customer.phone if customer else "—",
            "product_id": order.product_id,
            "product_name": product.name if product else "—",
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
            "status": order.status,
            "payment_type": order.payment_type,
            "notes": order.notes,
            "created_at": order.created_at.isoformat(),
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        })

    return result


class StatusIn(BaseModel):
    status: Optional[OrderStatus] = None


@router.put("/{order_id}/confirm")
def confirm_order(
    order_id: int,
    data: Optional[StatusIn] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buyurtma statusini yangilash (Dokon egasi).

    Body bo'lmasa yoki status ko'rsatilmasa — pending → confirmed.
    Body bilan status yuborilsa (masalan 'delivered') — o'sha statusga o'tadi.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    new_status = data.status if (data and data.status) else OrderStatus.confirmed
    order.status = new_status
    if new_status == OrderStatus.confirmed:
        order.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(order)

    return {"message": "Buyurtma yangilandi", "order": order}


@router.delete("/{order_id}")
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buyurtmani bekor qilish."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    if order.status == OrderStatus.confirmed:
        raise HTTPException(status_code=400, detail="Tasdiqlangan buyurtmani bekor qila olmaysiz")

    order.status = OrderStatus.cancelled
    db.commit()

    return {"message": "Buyurtma bekor qilindi"}


@router.get("/branch/{branch_id}/pending")
def get_pending_orders_for_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dokon uchun pending buyurtmalar."""
    orders = db.query(Order).filter(
        Order.branch_id == branch_id,
        Order.status == OrderStatus.pending
    ).order_by(Order.created_at.desc()).all()

    result = []
    for order in orders:
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
        product = db.query(Product).filter(Product.id == order.product_id).first()

        result.append({
            "id": order.id,
            "customer_name": customer.name if customer else "—",
            "customer_phone": customer.phone if customer else "—",
            "product_name": product.name if product else "—",
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
            "payment_type": order.payment_type,
            "status": order.status,
            "created_at": order.created_at.isoformat(),
            "notes": order.notes,
        })

    return result
