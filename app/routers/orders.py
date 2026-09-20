from typing import Optional, List
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks  # type: ignore
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

    customer_ids = {o.customer_id for o in orders}
    product_ids = {o.product_id for o in orders}
    courier_ids = {o.courier_id for o in orders if getattr(o, "courier_id", None)}
    couriers_by_id = {}
    if courier_ids:
        from app.models.courier import Courier
        for c in db.query(Courier.id, Courier.name, Courier.phone).filter(Courier.id.in_(courier_ids)).all():
            couriers_by_id[c.id] = c
    customers_by_id = {}
    if customer_ids:
        for c in db.query(Customer.id, Customer.name, Customer.phone).filter(Customer.id.in_(customer_ids)).all():
            customers_by_id[c.id] = c
    products_by_id = {}
    if product_ids:
        for p in db.query(Product.id, Product.name).filter(Product.id.in_(product_ids)).all():
            products_by_id[p.id] = p.name

    groups: dict = {}
    for order in orders:
        key = _group_key(order)
        if key not in groups:
            customer = customers_by_id.get(order.customer_id)
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
                # Yetkazib berish (guruh darajasida — barcha qatorlarda bir xil)
                "delivery_type": getattr(order, "delivery_type", None) or "pickup",
                "delivery_address": getattr(order, "delivery_address", None),
                "delivery_lat": float(order.delivery_lat) if getattr(order, "delivery_lat", None) else None,
                "delivery_lng": float(order.delivery_lng) if getattr(order, "delivery_lng", None) else None,
                "contact_phone": getattr(order, "contact_phone", None),
                "delivery_fee": float(getattr(order, "delivery_fee", 0) or 0),
                "courier_id": getattr(order, "courier_id", None),
                "courier_name": couriers_by_id[order.courier_id].name if getattr(order, "courier_id", None) in couriers_by_id else None,
                "courier_phone": couriers_by_id[order.courier_id].phone if getattr(order, "courier_id", None) in couriers_by_id else None,
                "assigned_at": order.assigned_at.isoformat() if getattr(order, "assigned_at", None) else None,
                "on_way_at": order.on_way_at.isoformat() if getattr(order, "on_way_at", None) else None,
                "delivered_at": order.delivered_at.isoformat() if getattr(order, "delivered_at", None) else None,
            }

        groups[key]["items"].append({
            "id": order.id,
            "product_id": order.product_id,
            "product_name": products_by_id.get(order.product_id, "—"),
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
        })
        groups[key]["total_amount"] += float(order.total_amount)

    # dict Python 3.7+da qo'shilish tartibini saqlaydi (created_at desc bo'yicha)
    return list(groups.values())


class StatusIn(BaseModel):
    status: Optional[OrderStatus] = None


# Mijozga yuboriladigan status xabarlari (mijoz boti orqali)
_STATUS_CUSTOMER_MSGS = {
    OrderStatus.confirmed: "✅ Buyurtmangiz tasdiqlandi!",
    OrderStatus.preparing: "📦 Buyurtmangiz tayyorlanmoqda...",
    OrderStatus.assigned: "🛵 Buyurtmangiz kuryerga topshirildi.",
    OrderStatus.on_way: "🚚 Buyurtmangiz yo'lda! Tez orada yetkaziladi.",
    OrderStatus.delivered: "🎉 Buyurtmangiz yetkazildi. Xaridingiz uchun rahmat!",
    OrderStatus.cancelled: "❌ Buyurtmangiz bekor qilindi.",
}


def _notify_customer_status(db: Session, orders: list, new_status: "OrderStatus") -> None:
    """Status o'zgarganda mijozga mijoz boti orqali xabar (background)."""
    try:
        from app.models.company import Company
        from app.services.sale_helpers import send_tg_sync

        msg = _STATUS_CUSTOMER_MSGS.get(new_status)
        if not msg or not orders:
            return
        customer = db.query(Customer).filter(Customer.id == orders[0].customer_id).first()
        if not customer or not customer.tg_chat_id:
            return
        company = db.query(Company).filter(Company.id == customer.company_id).first()
        if not company or not company.tg_bot_token:
            return

        total = sum(float(o.total_amount or 0) for o in orders) + float(getattr(orders[0], "delivery_fee", 0) or 0)
        text = f"{msg}\n\n🧾 Buyurtma summasi: {total:,.0f} so'm"
        send_tg_sync(company.tg_bot_token, customer.tg_chat_id, text)
    except Exception:
        pass  # bildirishnoma xatosi status yangilashni to'xtatmasin


@router.put("/group/{group_id}/status")
def update_order_group_status(
    group_id: str,
    background_tasks: BackgroundTasks,
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
    now = datetime.now(timezone.utc)
    for order in orders:
        order.status = new_status
        if new_status == OrderStatus.confirmed:
            order.confirmed_at = now
        elif new_status == OrderStatus.assigned:
            order.assigned_at = now
        elif new_status == OrderStatus.on_way:
            order.on_way_at = now
        elif new_status == OrderStatus.delivered:
            order.delivered_at = now
    db.commit()

    background_tasks.add_task(_notify_customer_status, db, orders, new_status)

    return {"message": "Buyurtma yangilandi", "count": len(orders)}


class AssignIn(BaseModel):
    courier_id: int


@router.put("/group/{group_id}/assign")
def assign_order_group_courier(
    group_id: str,
    data: AssignIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Buyurtma guruhiga dostavchik biriktiradi (status -> assigned)."""
    from app.models.courier import Courier

    courier = db.query(Courier).filter(
        Courier.id == data.courier_id,
        Courier.company_id == current_user.company_id,
        Courier.is_active == True,  # noqa: E712
    ).first()
    if not courier:
        raise HTTPException(status_code=404, detail="Faol dostavchik topilmadi")

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
    if any(o.status in (OrderStatus.delivered, OrderStatus.cancelled) for o in orders):
        raise HTTPException(status_code=400, detail="Yetkazilgan/bekor qilingan buyurtmaga kuryer biriktirib bo'lmaydi")

    now = datetime.now(timezone.utc)
    for order in orders:
        order.courier_id = courier.id
        order.status = OrderStatus.assigned
        order.assigned_at = now
    db.commit()

    # Mijozga xabar (mijoz boti orqali)
    background_tasks.add_task(_notify_customer_status, db, orders, OrderStatus.assigned)

    # Kuryerga xabar (kuryer boti orqali, ulangan bo'lsa)
    background_tasks.add_task(_notify_courier_assigned, db, orders, courier.id)

    return {"message": f"Dostavchik biriktirildi: {courier.name}", "count": len(orders)}


def _notify_courier_assigned(db: Session, orders: list, courier_id: int) -> None:
    """Kuryerga yangi buyurtma haqida kuryer boti orqali xabar."""
    try:
        from app.models.company import Company
        from app.models.courier import Courier
        from app.services.sale_helpers import send_tg_sync

        courier = db.query(Courier).filter(Courier.id == courier_id).first()
        if not courier or not courier.tg_chat_id:
            return
        company = db.query(Company).filter(Company.id == courier.company_id).first()
        if not company or not getattr(company, "courier_bot_token", None):
            return

        first = orders[0]
        customer = db.query(Customer).filter(Customer.id == first.customer_id).first()
        total = sum(float(o.total_amount or 0) for o in orders) + float(getattr(first, "delivery_fee", 0) or 0)
        lines = [
            "🆕 <b>Yangi buyurtma biriktirildi!</b>\n",
            f"👤 Mijoz: <b>{customer.name if customer else '—'}</b>",
        ]
        phone = getattr(first, "contact_phone", None) or (customer.phone if customer else None)
        if phone:
            lines.append(f"📞 Tel: {phone}")
        if getattr(first, "delivery_address", None):
            lines.append(f"📍 Manzil: {first.delivery_address}")
        lines.append(f"💰 Summa: <b>{total:,.0f} so'm</b>")
        lines.append("\n📦 Buyurtmalarim tugmasi orqali boshqaring.")
        send_tg_sync(company.courier_bot_token, courier.tg_chat_id, "\n".join(lines))
    except Exception:
        pass  # bildirishnoma xatosi biriktirish natijasiga ta'sir qilmasin


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

    customer_ids = {o.customer_id for o in orders}
    product_ids = {o.product_id for o in orders}
    customers_by_id = {}
    if customer_ids:
        for c in db.query(Customer.id, Customer.name, Customer.phone).filter(Customer.id.in_(customer_ids)).all():
            customers_by_id[c.id] = c
    products_by_id = {}
    if product_ids:
        for p in db.query(Product.id, Product.name).filter(Product.id.in_(product_ids)).all():
            products_by_id[p.id] = p.name

    result = []
    for order in orders:
        customer = customers_by_id.get(order.customer_id)

        result.append({
            "id": order.id,
            "customer_name": customer.name if customer else "—",
            "customer_phone": customer.phone if customer else "—",
            "product_name": products_by_id.get(order.product_id, "—"),
            "quantity": order.quantity,
            "unit_price": float(order.unit_price),
            "total_amount": float(order.total_amount),
            "payment_type": order.payment_type,
            "status": order.status,
            "created_at": order.created_at.isoformat(),
            "notes": order.notes,
        })

    return result
