import logging
from typing import Optional, List
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Response  # type: ignore
from sqlalchemy import String, cast, func, literal  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.core.branch_context import BranchContext, apply_branch_scope, get_branch_context  # type: ignore
from app.services.branch_helpers import NO_ACTIVE_BRANCH, resolve_customer_branch_id  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.order import Order, OrderStatus  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.product import Product  # type: ignore
from app.utils.report_utils import date_bounds  # type: ignore

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger(__name__)

# Eski (eskirgan) /orders endpointlariga faqat do'kon xodimlari kira oladi —
# kuryer, agent va marketplace agent uchun yopiq.
LEGACY_ORDER_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier, UserRole.super_admin)

# T1.15: holatni o'zgartirish rollari; bekor qilish (cancelled) faqat CANCEL_ROLES
STATUS_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier, UserRole.warehouse)
CANCEL_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin)

# T1.15: ruxsat etilgan holat o'tishlari (Orders.jsx dagi NEXT_STEPS bilan mos).
# delivered va cancelled — oxirgi holat.
ALLOWED_TRANSITIONS = {
    OrderStatus.pending: (OrderStatus.confirmed, OrderStatus.cancelled),
    OrderStatus.confirmed: (OrderStatus.preparing, OrderStatus.assigned, OrderStatus.on_way,
                            OrderStatus.delivered, OrderStatus.cancelled),
    OrderStatus.preparing: (OrderStatus.assigned, OrderStatus.on_way, OrderStatus.delivered,
                            OrderStatus.cancelled),
    OrderStatus.assigned: (OrderStatus.on_way, OrderStatus.delivered, OrderStatus.cancelled),
    OrderStatus.on_way: (OrderStatus.delivered, OrderStatus.cancelled),
    OrderStatus.delivered: (),
    OrderStatus.cancelled: (),
}


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
        Customer.is_active.is_(True),  # T0.26: arxivlangan mijozga buyurtma yo'q
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    # T1.15: mijoz filiali -> korxonaning birinchi faol filiali (mijozga filial biriktirilmagan
    # bo'lsa ham buyurtma qabul qilinadi)
    order_branch_id = resolve_customer_branch_id(db, customer, current_user.company_id)
    if not order_branch_id:
        raise HTTPException(status_code=400, detail=NO_ACTIVE_BRANCH)

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
        company_id=current_user.company_id,
        customer_id=data.customer_id,
        branch_id=order_branch_id,
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


def _group_key_expr():
    """`_group_key` ning SQL varianti: coalesce(order_group_id, 'single-' || id)."""
    return func.coalesce(Order.order_group_id, literal("single-").concat(cast(Order.id, String)))


@router.get("", response_model=List[dict])
def list_orders(
    response: Response,
    branch_id: Optional[int] = None,
    status: Optional[OrderStatus] = None,
    customer_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Buyurtmalarni guruhlab ko'rish (bitta checkout = bitta guruh, ichida
    bir nechta mahsulot bo'lishi mumkin). Sahifalash GURUHLAR bo'yicha (`skip/limit`),
    jami guruhlar soni `X-Total-Count` header'ida.

    Filial doirasi: admin/director/super_admin hammasini ko'radi (`branch_id` ixtiyoriy
    filtr); boshqa rollar faqat o'z filiali buyurtmalarini (filialsiz xodim — T1.1 qoidasi)."""
    query = db.query(Order).filter(Order.company_id == current_user.company_id)

    query = apply_branch_scope(query, ctx, Order.branch_id, explicit_branch_id=branch_id)
    if status:
        query = query.filter(Order.status == status)
    if customer_id:
        query = query.filter(Order.customer_id == customer_id)
    if date_from or date_to:
        start, end = date_bounds(date_from, date_to)
        query = query.filter(Order.created_at >= start, Order.created_at < end)

    # 1) Sahifadagi guruh kalitlari (eng yangisi birinchi), 2) shu guruhlarning qatorlari
    gkey = _group_key_expr()
    total_groups = query.with_entities(func.count(func.distinct(gkey))).scalar() or 0
    response.headers["X-Total-Count"] = str(total_groups)
    page_keys = [
        r[0] for r in query.with_entities(gkey.label("gk"), func.max(Order.created_at).label("mx"))
        .group_by(gkey).order_by(func.max(Order.created_at).desc(), gkey).offset(skip).limit(limit).all()
    ]
    if not page_keys:
        return []

    orders = query.filter(gkey.in_(page_keys)).order_by(Order.created_at.desc(), Order.id.desc()).all()

    branch_ids = {o.branch_id for o in orders if o.branch_id}
    branch_names = {}
    branch_addresses = {}
    if branch_ids:
        # T3.13: filial nomi va manzili bitta so'rov bilan (N+1 yo'q)
        for b in db.query(Branch.id, Branch.name, Branch.address).filter(
            Branch.id.in_(branch_ids), Branch.company_id == current_user.company_id,
        ).all():
            branch_names[b.id] = b.name
            branch_addresses[b.id] = b.address

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
                "branch_id": order.branch_id,
                "branch_name": branch_names.get(order.branch_id),
                "warehouse_id": getattr(order, "warehouse_id", None),
                # T3.13: olib ketish buyurtmasi uchun filial manzili
                "pickup_address": (
                    branch_addresses.get(order.branch_id)
                    if (getattr(order, "delivery_type", None) or "pickup") == "pickup" else None
                ),
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

    # Sahifa tartibi (guruhning eng yangi qatori bo'yicha kamayish) saqlanadi
    return [groups[k] for k in page_keys if k in groups]


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


def _sync_mirmaza(db: Session, orders: list, courier_id, status_value: str) -> None:
    """T3.14 (EDGE-X18): Mir-maza buyurtmasi (`mirmaza-...`) uchun kuryer holatini Mir-maza ga
    yuboradi. Telegram xabarnomalaridan mustaqil: mijozda tg_chat_id yoki kuryerda bot bo'lmasa ham
    ishlaydi. Xato status yangilashni to'xtatmaydi, lekin logga yoziladi."""
    gid = (orders[0].order_group_id or "") if orders else ""
    if not gid.startswith("mirmaza-"):
        return
    try:
        from app.services.marketplace_service import push_courier_status_to_mirmaza
        push_courier_status_to_mirmaza(db, gid, courier_id, status_value)
    except Exception:
        logger.exception("Mir-maza kuryer holatini yuborishda xatolik (%s, %s)", gid, status_value)


def _notify_customer_status(db: Session, orders: list, new_status: "OrderStatus") -> None:
    """Status o'zgarganda mijozga mijoz boti orqali xabar (background)."""
    if orders and new_status in (OrderStatus.on_way, OrderStatus.delivered, OrderStatus.cancelled):
        _sync_mirmaza(db, orders, getattr(orders[0], "courier_id", None), new_status.value)
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


def _load_group_orders(db: Session, group_id: str, current_user: User, ctx: BranchContext) -> list:
    """Guruh buyurtmalari: faqat shu korxona va (ruxsat doirasidagi) filialdan; boshqa
    filial guruhi uchun ham 404 (mavjudligini oshkor qilmaslik)."""
    q = db.query(Order).filter(Order.company_id == current_user.company_id)
    if group_id.startswith("single-"):
        try:
            order_id = int(group_id.split("-", 1)[1])
        except ValueError:
            raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
        q = q.filter(Order.id == order_id)
    else:
        q = q.filter(Order.order_group_id == group_id)
    orders = apply_branch_scope(q, ctx, Order.branch_id).all()
    if not orders:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return orders


@router.put("/group/{group_id}/status")
def update_order_group_status(
    group_id: str,
    background_tasks: BackgroundTasks,
    data: Optional[StatusIn] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STATUS_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Guruhdagi barcha buyurtmalar statusini birgalikda yangilaydi.

    Faqat ruxsat etilgan o'tishlar (`ALLOWED_TRANSITIONS`); `cancelled` ga faqat
    admin/director/manager o'tkaza oladi. Bir xil holatni qayta yuborish — 200 (hech narsa
    o'zgarmaydi, bildirishnoma va avto-sotuv qayta ishga tushmaydi)."""
    orders = _load_group_orders(db, group_id, current_user, ctx)

    new_status = data.status if (data and data.status) else OrderStatus.confirmed

    if new_status == OrderStatus.cancelled and current_user.role not in CANCEL_ROLES:
        raise HTTPException(status_code=403, detail="Buyurtmani bekor qilish uchun ruxsat yo'q")

    pending_change = [o for o in orders if o.status != new_status]
    if not pending_change:
        return {"message": "Buyurtma yangilandi", "count": len(orders)}
    for order in pending_change:
        if new_status not in ALLOWED_TRANSITIONS.get(order.status, ()):
            old = order.status.value if hasattr(order.status, "value") else order.status
            raise HTTPException(
                status_code=400,
                detail=f"Holatni '{old}' dan '{new_status.value}' ga o'tkazib bo'lmaydi",
            )

    now = datetime.now(timezone.utc)
    for order in pending_change:
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

    if new_status == OrderStatus.delivered:
        from app.services.order_to_sale import maybe_create_sale_for_delivered_group
        # T3.14: sotuv birinchi admin nomidan emas, holatni o'zgartirgan xodim nomidan ketadi
        background_tasks.add_task(maybe_create_sale_for_delivered_group, db, orders, current_user)

    return {"message": "Buyurtma yangilandi", "count": len(orders)}


class AssignIn(BaseModel):
    courier_id: int


@router.put("/group/{group_id}/assign")
def assign_order_group_courier(
    group_id: str,
    data: AssignIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STATUS_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
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

    orders = _load_group_orders(db, group_id, current_user, ctx)
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
    if orders:
        _sync_mirmaza(db, orders, courier_id, "assigned")
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
        # T3.14: tovarni qaysi filialdan olish kerakligi
        from app.routers.logistics import order_group_pickup
        pk = order_group_pickup(db, orders)
        if pk.get("pickup_branch_name"):
            pickup = pk["pickup_branch_name"] + (f", {pk['pickup_address']}" if pk.get("pickup_address") else "")
            lines.append(f"🏬 Olib ketish: {pickup}")
        lines.append(f"💰 Summa: <b>{total:,.0f} so'm</b>")
        lines.append("\n📦 Buyurtmalarim tugmasi orqali boshqaring.")
        send_tg_sync(company.courier_bot_token, courier.tg_chat_id, "\n".join(lines))
    except Exception:
        pass  # bildirishnoma xatosi biriktirish natijasiga ta'sir qilmasin


@router.delete("/group/{group_id}")
def cancel_order_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STATUS_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Guruhdagi barcha buyurtmalarni bekor qiladi."""
    orders = _load_group_orders(db, group_id, current_user, ctx)

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
    current_user: User = Depends(require_roles(*LEGACY_ORDER_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """[Eskirgan] Bitta buyurtma statusini yangilash — endi /group/{id}/status ishlatiladi,
    backward-compat uchun saqlanmoqda."""
    order = apply_branch_scope(db.query(Order).filter(
        Order.id == order_id,
        Order.company_id == current_user.company_id,
    ), ctx, Order.branch_id).first()
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
    current_user: User = Depends(require_roles(*LEGACY_ORDER_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """[Eskirgan] Bitta buyurtmani bekor qilish — endi /group/{id} ishlatiladi."""
    order = apply_branch_scope(db.query(Order).filter(
        Order.id == order_id,
        Order.company_id == current_user.company_id,
    ), ctx, Order.branch_id).first()
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
    current_user: User = Depends(require_roles(*LEGACY_ORDER_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """[Eskirgan] Filial uchun pending buyurtmalar."""
    branch = db.query(Branch).filter(
        Branch.id == branch_id,
        Branch.company_id == current_user.company_id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")

    # T0.36: egalik orders.company_id orqali; T0.10: mijozi boshqa korxonaniki bo'lgan
    # (buzilgan) qator ham chiqmasin — Customer.company_id qo'shimcha tekshiriladi
    orders = apply_branch_scope(db.query(Order).join(Customer, Customer.id == Order.customer_id).filter(
        Order.company_id == current_user.company_id,
        Customer.company_id == current_user.company_id,
        Order.branch_id == branch_id,
        Order.status == OrderStatus.pending
    ), ctx, Order.branch_id).order_by(Order.created_at.desc()).all()

    customer_ids = {o.customer_id for o in orders}
    product_ids = {o.product_id for o in orders}
    customers_by_id = {}
    if customer_ids:
        for c in db.query(Customer.id, Customer.name, Customer.phone).filter(
            Customer.id.in_(customer_ids), Customer.company_id == current_user.company_id
        ).all():
            customers_by_id[c.id] = c
    products_by_id = {}
    if product_ids:
        for p in db.query(Product.id, Product.name).filter(
            Product.id.in_(product_ids), Product.company_id == current_user.company_id
        ).all():
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
