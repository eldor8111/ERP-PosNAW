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


def _group_key(order: Order) -> str:
    """Bir checkout'dagi itemlar order_group_id bilan bog'langan; eski
    yozuvlarda (order_group_id yo'q) har biri o'z-o'zining guruhi."""
    return order.order_group_id or f"single-{order.id}"


@router.get("", response_model=List[dict])
def list_orders(
    branch_id: Optional[int] = None,
    status: Optional[OrderStatus] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buyurtmalarni guruhlab ko'rish (bitta checkout = bitta guruh, ichida
    bir nechta mahsulot bo'lishi mumkin)."""
    query = db.query(Order).join(Customer).filter(
        Customer.company_id == current_user.company_id
    )

    if branch_id:
        query = query.filter(Order.branch_id == branch_id)
    if status:
        query = query.filter(Order.status == status)

    orders = query.order_by(Order.created_at.desc()).all()

    groups: dict = {}
    for order in orders:
        key = _group_key(order)
        if key not in groups:
            customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
            groups[key] = {
                "group_id": key,
                "customer_id": order.customer_id,
                "customer_name": customer.name if customer else "—",
                "customer_phone": customer.phone if customer else "—",
                "status": order.status,
                "payment_type": order.payment_type,
                "notes": order.notes,
                "created_at": order.created_at.isoformat(),
                "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
                "total_amount": 0.0,
                "items": [],
            }

        product = db.query(Product).filter(Product.id == order.product_id).first()
        groups[key]["items"].append({
            "id": order.id,
            "product_id": order.product_id,
            "product_name": product.name if product else "—",
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
        })
        groups[key]["total_amount"] += float(order.total_amount)

    # dict Python 3.7+da qo'shilish tartibini saqlaydi (created_at desc bo'yicha)
    return list(groups.values())


class StatusIn(BaseModel):
    status: Optional[OrderStatus] = None


@router.put("/group/{group_id}/status")
def update_order_group_status(
    group_id: str,
    data: Optional[StatusIn] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Guruhdagi barcha buyurtmalar statusini birgalikda yangilaydi."""
    if group_id.startswith("single-"):
        order_ids = [int(group_id.split("-", 1)[1])]
        orders = db.query(Order).join(Customer).filter(
            Order.id.in_(order_ids),
            Customer.company_id == current_user.company_id,
        ).all()
    else:
        orders = db.query(Order).join(Customer).filter(
            Order.order_group_id == group_id,
            Customer.company_id == current_user.company_id,
        ).all()

    if not orders:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    new_status = data.status if (data and data.status) else OrderStatus.confirmed
    for order in orders:
        order.status = new_status
        if new_status == OrderStatus.confirmed:
            order.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Buyurtma yangilandi", "count": len(orders)}


@router.delete("/group/{group_id}")
def cancel_order_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Guruhdagi barcha buyurtmalarni bekor qiladi."""
    if group_id.startswith("single-"):
        order_ids = [int(group_id.split("-", 1)[1])]
        orders = db.query(Order).join(Customer).filter(
            Order.id.in_(order_ids),
            Customer.company_id == current_user.company_id,
        ).all()
    else:
        orders = db.query(Order).join(Customer).filter(
            Order.order_group_id == group_id,
            Customer.company_id == current_user.company_id,
        ).all()

    if not orders:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    if any(o.status == OrderStatus.confirmed for o in orders):
        raise HTTPException(status_code=400, detail="Tasdiqlangan buyurtmani bekor qila olmaysiz")

    for order in orders:
        order.status = OrderStatus.cancelled
    db.commit()

    return {"message": "Buyurtma bekor qilindi"}


@router.put("/{order_id}/confirm")
def confirm_order(
    order_id: int,
    data: Optional[StatusIn] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """[Eskirgan] Bitta buyurtma statusini yangilash — endi /group/{id}/status ishlatiladi,
    backward-compat uchun saqlanmoqda."""
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
    """[Eskirgan] Bitta buyurtmani bekor qilish — endi /group/{id} ishlatiladi."""
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
