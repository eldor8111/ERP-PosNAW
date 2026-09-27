"""
Logistika: transport reestri va ko'p to'xtovli yetkazib berish marshrutlari.

Marshrut = bir kuryerning bir kunlik buyurtma guruhlari ro'yxati (tartib
bilan). To'xtov holati alohida saqlanmaydi — Order.status dan olinadi,
shuning uchun kuryer boti orqali "yetkazildi" bosilsa ham marshrut to'g'ri
ko'rinadi. Status o'zgarishlari orders.py/courier_bot.py dagi bilan bir xil
yon ta'sirlarga ega (mijozga xabar, avto-sotuv).
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.courier import Courier
from app.models.customer import Customer
from app.models.delivery_route import DeliveryRoute, DeliveryRouteStatus, DeliveryRouteStop
from app.models.order import Order, OrderStatus
from app.models.sale_delivery import SaleDelivery, SaleDeliveryStatus
from app.models.user import User, UserRole
from app.models.vehicle import Vehicle
from app.services import sale_delivery_service as sd_service

router = APIRouter(prefix="/logistics", tags=["logistics"],
                   dependencies=[Depends(require_feature("distribution"))])

MANAGE_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)
ACTIVE_ROUTE = (DeliveryRouteStatus.planned, DeliveryRouteStatus.in_progress)
# Marshrutga qo'shsa bo'ladigan buyurtma holatlari
ROUTABLE = (OrderStatus.pending, OrderStatus.confirmed, OrderStatus.preparing, OrderStatus.assigned)
FINAL = (OrderStatus.delivered, OrderStatus.cancelled)


# ── Transport ────────────────────────────────────────────────────────────────

class VehicleIn(BaseModel):
    plate_number: str = Field(..., min_length=2, max_length=20)
    model: Optional[str] = Field(None, max_length=100)
    capacity_kg: Optional[Decimal] = None
    fuel_type: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = True


def _vehicle_out(v: Vehicle) -> dict:
    return {
        "id": v.id,
        "plate_number": v.plate_number,
        "model": v.model,
        "capacity_kg": float(v.capacity_kg) if v.capacity_kg is not None else None,
        "fuel_type": v.fuel_type,
        "is_active": bool(v.is_active),
    }


def _norm_plate(p: str) -> str:
    return "".join(p.split()).upper()


def _check_plate_free(db: Session, company_id: int, plate: str, exclude_id: Optional[int] = None) -> None:
    q = db.query(Vehicle.id).filter(Vehicle.company_id == company_id, Vehicle.plate_number == plate)
    if exclude_id:
        q = q.filter(Vehicle.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail=f"{plate} raqamli transport allaqachon mavjud")


@router.get("/vehicles")
def list_vehicles(include_inactive: bool = False, db: Session = Depends(get_db),
                  current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    q = db.query(Vehicle).filter(Vehicle.company_id == current_user.company_id)
    if not include_inactive:
        q = q.filter(Vehicle.is_active == True)  # noqa: E712
    return [_vehicle_out(v) for v in q.order_by(Vehicle.plate_number).all()]


@router.post("/vehicles", status_code=201)
def create_vehicle(data: VehicleIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    plate = _norm_plate(data.plate_number)
    _check_plate_free(db, current_user.company_id, plate)
    v = Vehicle(
        company_id=current_user.company_id,
        plate_number=plate,
        model=(data.model or "").strip() or None,
        capacity_kg=data.capacity_kg,
        fuel_type=data.fuel_type,
        is_active=True,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return _vehicle_out(v)


@router.put("/vehicles/{vehicle_id}")
def update_vehicle(vehicle_id: int, data: VehicleIn, db: Session = Depends(get_db),
                   current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    v = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.company_id == current_user.company_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Transport topilmadi")
    plate = _norm_plate(data.plate_number)
    _check_plate_free(db, current_user.company_id, plate, exclude_id=v.id)
    v.plate_number = plate
    v.model = (data.model or "").strip() or None
    v.capacity_kg = data.capacity_kg
    v.fuel_type = data.fuel_type
    if data.is_active is not None:
        v.is_active = data.is_active
    db.commit()
    db.refresh(v)
    return _vehicle_out(v)


@router.delete("/vehicles/{vehicle_id}")
def deactivate_vehicle(vehicle_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    v = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.company_id == current_user.company_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Transport topilmadi")
    v.is_active = False
    db.commit()
    return {"message": "Transport nofaol qilindi"}


# ── Marshrutlar ──────────────────────────────────────────────────────────────

class RouteIn(BaseModel):
    route_date: date
    courier_id: int
    vehicle_id: Optional[int] = None
    note: Optional[str] = None
    group_keys: List[str] = Field(..., min_length=1)


class StopsIn(BaseModel):
    group_keys: List[str] = Field(..., min_length=1)


SALE_PREFIX = "sale-"
SALE_ROUTABLE = (SaleDeliveryStatus.pending, SaleDeliveryStatus.assigned)
SALE_FINAL = (SaleDeliveryStatus.delivered, SaleDeliveryStatus.cancelled)


def _group_key(o: Order) -> str:
    return o.order_group_id or f"single-{o.id}"


class _Stop:
    """Marshrut to'xtovi: Telegram-do'kon buyurtma guruhi (orders) yoki
    ulgurji sotuv yetkazmasi (delivery). Status manbasi — Order.status /
    SaleDelivery.status, shuning uchun kuryer boti o'zgartirsa ham to'g'ri."""

    def __init__(self, key: str, orders: Optional[list] = None, delivery: Optional[SaleDelivery] = None):
        self.key = key
        self.orders = orders or []
        self.delivery = delivery

    @property
    def is_sale(self) -> bool:
        return self.delivery is not None

    @property
    def customer_id(self):
        return self.delivery.sale.customer_id if self.is_sale else self.orders[0].customer_id

    @property
    def status(self) -> str:
        if self.is_sale:
            return self.delivery.status.value
        statuses = {o.status for o in self.orders}
        st = self.orders[0].status if len(statuses) == 1 else min(statuses, key=lambda x: list(OrderStatus).index(x))
        return st.value if hasattr(st, "value") else st

    @property
    def is_final(self) -> bool:
        if self.is_sale:
            return self.delivery.status in SALE_FINAL
        return all(o.status in FINAL for o in self.orders)

    @property
    def is_routable(self) -> bool:
        if self.is_sale:
            return self.delivery.status in SALE_ROUTABLE
        return all(o.status in ROUTABLE for o in self.orders)

    def assign(self, courier_id: int) -> bool:
        if self.is_sale:
            d = self.delivery
            if d.courier_id == courier_id and d.status == SaleDeliveryStatus.assigned:
                return False
            sd_service.set_status(d, SaleDeliveryStatus.assigned, courier_id)
            return True
        now = datetime.now(timezone.utc)
        changed = False
        for o in self.orders:
            if o.courier_id != courier_id or o.status != OrderStatus.assigned:
                o.courier_id, o.status, o.assigned_at = courier_id, OrderStatus.assigned, now
                changed = True
        return changed

    def start(self) -> bool:
        if self.is_final:
            return False
        if self.is_sale:
            sd_service.set_status(self.delivery, SaleDeliveryStatus.on_way)
            return True
        now = datetime.now(timezone.utc)
        for o in self.orders:
            if o.status not in FINAL:
                o.status, o.on_way_at = OrderStatus.on_way, now
        return True

    def finish(self, delivered: bool) -> None:
        if self.is_sale:
            if delivered:
                sd_service.set_status(self.delivery, SaleDeliveryStatus.delivered)
            else:
                self.delivery.status = SaleDeliveryStatus.cancelled
                self.delivery.cancel_reason = "Marshrutda yetkazilmadi"
            return
        now = datetime.now(timezone.utc)
        for o in self.orders:
            if delivered:
                o.status, o.delivered_at = OrderStatus.delivered, now
            else:
                o.status, o.cancel_reason = OrderStatus.cancelled, "Marshrutda yetkazilmadi"

    def release(self) -> None:
        """Qayta rejalashtirishga qaytarish (marshrutdan chiqarilganda/yopilganda)."""
        if self.is_sale:
            sd_service.release(self.delivery)
            return
        for o in self.orders:
            if o.status not in FINAL:
                o.status, o.courier_id, o.assigned_at, o.on_way_at = OrderStatus.confirmed, None, None, None

    def summary(self, customers: dict) -> dict:
        cust = customers.get(self.customer_id)
        if self.is_sale:
            d, sale = self.delivery, self.delivery.sale
            pt = sale.payment_type.value if hasattr(sale.payment_type, "value") else sale.payment_type
            return {
                "group_key": self.key, "source": "sale", "sale_id": sale.id, "sale_number": sale.number,
                "customer_id": sale.customer_id,
                "customer_name": cust.name if cust else "—",
                "phone": d.contact_phone or (cust.phone if cust else None),
                "address": d.address,
                "lat": float(d.lat) if d.lat is not None else None,
                "lng": float(d.lng) if d.lng is not None else None,
                "amount": float(sale.total_amount or 0),
                "delivery_fee": float(d.delivery_fee or 0),
                "collect_amount": sd_service.collect_amount(d),
                "payment_type": pt,
                "items_count": len(sale.items),
                "planned_date": d.planned_date.isoformat() if d.planned_date else None,
                "note": d.note,
                "status": self.status,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
        first = self.orders[0]
        return {
            "group_key": self.key, "source": "order",
            "customer_id": first.customer_id,
            "customer_name": cust.name if cust else "—",
            "phone": first.contact_phone or (cust.phone if cust else None),
            "address": first.delivery_address,
            "lat": float(first.delivery_lat) if first.delivery_lat is not None else None,
            "lng": float(first.delivery_lng) if first.delivery_lng is not None else None,
            "amount": float(sum(Decimal(str(o.total_amount or 0)) for o in self.orders)),
            "delivery_fee": float(first.delivery_fee or 0),
            # Telegram buyurtmasi: qarzga bo'lsa kuryer pul olmaydi
            "collect_amount": 0.0 if (first.payment_type or "") == "debt" else float(
                sum(Decimal(str(o.total_amount or 0)) for o in self.orders) + Decimal(str(first.delivery_fee or 0))),
            "payment_type": first.payment_type,
            "items_count": len(self.orders),
            "status": self.status,
            "created_at": first.created_at.isoformat() if first.created_at else None,
        }


def _load_stops(db: Session, company_id: int, keys: List[str]) -> dict:
    """{key: _Stop} — faqat shu kompaniyaniki; topilmagan kalit qaytmaydi."""
    from sqlalchemy import or_
    result: dict = {}
    sale_ids, single_ids, group_ids = [], [], []
    for k in keys:
        if k.startswith(SALE_PREFIX):
            try:
                sale_ids.append(int(k[len(SALE_PREFIX):]))
            except ValueError:
                pass
        elif k.startswith("single-"):
            try:
                single_ids.append(int(k.split("-", 1)[1]))
            except ValueError:
                pass
        else:
            group_ids.append(k)

    conds = []
    if single_ids:
        conds.append(Order.id.in_(single_ids))
    if group_ids:
        conds.append(Order.order_group_id.in_(group_ids))
    if conds:
        q = db.query(Order).join(Customer, Customer.id == Order.customer_id).filter(
            Customer.company_id == company_id, or_(*conds))
        by_key: dict = {}
        for o in q.all():
            k = _group_key(o)
            if k in keys:
                by_key.setdefault(k, []).append(o)
        result.update({k: _Stop(k, orders=v) for k, v in by_key.items()})

    if sale_ids:
        for d in db.query(SaleDelivery).filter(
            SaleDelivery.company_id == company_id, SaleDelivery.sale_id.in_(sale_ids),
        ).all():
            k = f"{SALE_PREFIX}{d.sale_id}"
            result[k] = _Stop(k, delivery=d)
    return result


def _customers_map(db: Session, stops: dict) -> dict:
    ids = {s.customer_id for s in stops.values() if s.customer_id}
    if not ids:
        return {}
    return {c.id: c for c in db.query(Customer).filter(Customer.id.in_(ids)).all()}


def _keys_on_active_routes(db: Session, company_id: int, exclude_route_id: Optional[int] = None) -> set:
    q = db.query(DeliveryRouteStop.group_key).join(DeliveryRoute).filter(
        DeliveryRoute.company_id == company_id, DeliveryRoute.status.in_(ACTIVE_ROUTE),
    )
    if exclude_route_id:
        q = q.filter(DeliveryRoute.id != exclude_route_id)
    return {r[0] for r in q.all()}


def _route_out(db: Session, route: DeliveryRoute, with_stops: bool = True) -> dict:
    loaded = _load_stops(db, route.company_id, [s.group_key for s in route.stops])
    customers = _customers_map(db, loaded)
    stops = [
        {"sequence": s.sequence, **loaded[s.group_key].summary(customers)}
        for s in route.stops if s.group_key in loaded
    ]
    delivered = sum(1 for s in stops if s["status"] == "delivered")
    cancelled = sum(1 for s in stops if s["status"] == "cancelled")
    out = {
        "id": route.id,
        "number": route.number,
        "route_date": route.route_date.isoformat(),
        "status": route.status.value,
        "courier_id": route.courier_id,
        "courier_name": route.courier.name if route.courier else None,
        "courier_phone": route.courier.phone if route.courier else None,
        "vehicle_id": route.vehicle_id,
        "vehicle_plate": route.vehicle.plate_number if route.vehicle else None,
        "note": route.note,
        "stops_total": len(stops),
        "stops_delivered": delivered,
        "stops_cancelled": cancelled,
        "total_amount": sum(s["amount"] for s in stops),
        "total_fee": sum(s["delivery_fee"] for s in stops),
        "total_collect": sum(s["collect_amount"] for s in stops),
        "started_at": route.started_at.isoformat() if route.started_at else None,
        "completed_at": route.completed_at.isoformat() if route.completed_at else None,
    }
    if with_stops:
        out["stops"] = stops
    return out


def _get_route(db: Session, route_id: int, company_id: int, lock: bool = False) -> DeliveryRoute:
    q = db.query(DeliveryRoute).filter(DeliveryRoute.id == route_id, DeliveryRoute.company_id == company_id)
    if lock:
        q = q.with_for_update()
    route = q.first()
    if not route:
        raise HTTPException(status_code=404, detail="Marshrut topilmadi")
    return route


def _generate_route_number(db: Session, company_id: int, d: date) -> str:
    prefix = f"RT{d.strftime('%Y%m%d')}"
    count = db.query(func.count(DeliveryRoute.id)).filter(
        DeliveryRoute.company_id == company_id, DeliveryRoute.number.like(f"{prefix}%"),
    ).scalar() or 0
    return f"{prefix}{count + 1:03d}"


def _validate_courier_vehicle(db: Session, company_id: int, courier_id: int, vehicle_id: Optional[int]):
    courier = db.query(Courier).filter(
        Courier.id == courier_id, Courier.company_id == company_id, Courier.is_active == True,  # noqa: E712
    ).first()
    if not courier:
        raise HTTPException(status_code=404, detail="Faol dostavchik topilmadi")
    vehicle_id = vehicle_id or courier.vehicle_id
    if vehicle_id:
        v = db.query(Vehicle).filter(
            Vehicle.id == vehicle_id, Vehicle.company_id == company_id, Vehicle.is_active == True,  # noqa: E712
        ).first()
        if not v:
            raise HTTPException(status_code=404, detail="Faol transport topilmadi")
    return courier, vehicle_id


def _validate_stops(db: Session, company_id: int, keys: List[str], exclude_route_id: Optional[int] = None) -> dict:
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=400, detail="Bitta buyurtma marshrutda ikki marta kelgan")
    stops = _load_stops(db, company_id, keys)
    missing = [k for k in keys if k not in stops]
    if missing:
        raise HTTPException(status_code=404, detail=f"Buyurtma topilmadi: {', '.join(missing)}")
    busy = _keys_on_active_routes(db, company_id, exclude_route_id) & set(keys)
    if busy:
        raise HTTPException(status_code=409, detail="Ba'zi buyurtmalar boshqa faol marshrutga biriktirilgan")
    if any(not st.is_routable for st in stops.values()):
        raise HTTPException(status_code=400, detail="Yo'lga chiqqan, yetkazilgan yoki bekor qilingan buyurtmani marshrutga qo'shib bo'lmaydi")
    return stops


def _notify_courier_sales(db: Session, stops: list, courier_id: int) -> None:
    """Kuryerga biriktirilgan sotuv yetkazmalari haqida bot xabari."""
    try:
        from app.models.company import Company
        from app.services.sale_helpers import send_tg_sync
        courier = db.query(Courier).filter(Courier.id == courier_id).first()
        if not courier or not courier.tg_chat_id:
            return
        company = db.query(Company).filter(Company.id == courier.company_id).first()
        if not company or not getattr(company, "courier_bot_token", None):
            return
        lines = [f"🆕 <b>Sizga {len(stops)} ta yetkazma biriktirildi</b>\n"]
        for st in stops:
            d = st.delivery
            lines.append(f"🧾 #{d.sale.number} — {d.address or 'manzil kiritilmagan'}")
        lines.append("\n📦 Buyurtmalarim tugmasi orqali boshqaring.")
        send_tg_sync(company.courier_bot_token, courier.tg_chat_id, "\n".join(lines))
    except Exception:
        pass


def _push_courier(db: Session, courier_id: int, count: int) -> None:
    from app.services.mobile_service import push_to_user
    c = db.query(Courier).filter(Courier.id == courier_id).first()
    if c and c.user_id:
        push_to_user(db, c.user_id, "🆕 Yangi yetkazmalar", f"Sizga {count} ta manzil biriktirildi", {"type": "route"})


def _notify_assigned(background_tasks: BackgroundTasks, db: Session, changed: list, courier_id: int) -> None:
    from app.routers.orders import _notify_courier_assigned, _notify_customer_status
    background_tasks.add_task(_push_courier, db, courier_id, len(changed))
    order_stops = [st for st in changed if not st.is_sale]
    sale_stops = [st for st in changed if st.is_sale]
    for st in order_stops:
        background_tasks.add_task(_notify_customer_status, db, st.orders, OrderStatus.assigned)
    if order_stops:
        background_tasks.add_task(_notify_courier_assigned, db, [o for st in order_stops for o in st.orders], courier_id)
    if sale_stops:
        background_tasks.add_task(_notify_courier_sales, db, sale_stops, courier_id)


@router.get("/available-orders")
def available_orders(db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    """Marshrutga qo'shsa bo'ladigan yetkazmalar: Telegram buyurtmalari
    (guruhlab) va ulgurji sotuv yetkazmalari."""
    from app.models.sale import Sale, SaleStatus
    cid = current_user.company_id
    busy = _keys_on_active_routes(db, cid)
    stops: dict = {}

    orders = db.query(Order).join(Customer, Customer.id == Order.customer_id).filter(
        Customer.company_id == cid,
        Order.delivery_type == "delivery",
        Order.status.in_(ROUTABLE),
    ).order_by(Order.created_at.asc()).all()
    for o in orders:
        k = _group_key(o)
        if k not in busy:
            stops.setdefault(k, _Stop(k)).orders.append(o)

    deliveries = db.query(SaleDelivery).join(Sale, Sale.id == SaleDelivery.sale_id).filter(
        SaleDelivery.company_id == cid,
        SaleDelivery.status.in_(SALE_ROUTABLE),
        Sale.status.notin_([SaleStatus.cancelled, SaleStatus.refunded]),
    ).order_by(SaleDelivery.planned_date.asc().nullslast(), SaleDelivery.created_at.asc()).all()
    for d in deliveries:
        k = f"{SALE_PREFIX}{d.sale_id}"
        if k not in busy:
            stops[k] = _Stop(k, delivery=d)

    customers = _customers_map(db, stops)
    return [st.summary(customers) for st in stops.values()]


@router.get("/routes")
def list_routes(route_date: Optional[date] = None, status: Optional[DeliveryRouteStatus] = None,
                db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    q = db.query(DeliveryRoute).filter(DeliveryRoute.company_id == current_user.company_id)
    if route_date:
        q = q.filter(DeliveryRoute.route_date == route_date)
    if status:
        q = q.filter(DeliveryRoute.status == status)
    routes = q.order_by(DeliveryRoute.route_date.desc(), DeliveryRoute.id.desc()).limit(200).all()
    return [_route_out(db, r, with_stops=False) for r in routes]


@router.get("/routes/{route_id}")
def get_route(route_id: int, db: Session = Depends(get_db),
              current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    return _route_out(db, _get_route(db, route_id, current_user.company_id))


@router.post("/routes", status_code=201)
def create_route(data: RouteIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                 current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    cid = current_user.company_id
    courier, vehicle_id = _validate_courier_vehicle(db, cid, data.courier_id, data.vehicle_id)
    stops = _validate_stops(db, cid, data.group_keys)

    route = DeliveryRoute(
        number=_generate_route_number(db, cid, data.route_date),
        company_id=cid,
        route_date=data.route_date,
        courier_id=courier.id,
        vehicle_id=vehicle_id,
        status=DeliveryRouteStatus.planned,
        note=(data.note or "").strip() or None,
        created_by=current_user.id,
    )
    for i, k in enumerate(data.group_keys, start=1):
        route.stops.append(DeliveryRouteStop(group_key=k, sequence=i))
    db.add(route)
    changed = [st for st in stops.values() if st.assign(courier.id)]
    db.commit()
    db.refresh(route)

    if changed:
        _notify_assigned(background_tasks, db, changed, courier.id)
    return _route_out(db, route)


@router.put("/routes/{route_id}/stops")
def update_route_stops(route_id: int, data: StopsIn, background_tasks: BackgroundTasks,
                       db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    """Rejalashtirilgan marshrut to'xtovlarini qayta tartiblash/qo'shish/olib tashlash."""
    cid = current_user.company_id
    route = _get_route(db, route_id, cid, lock=True)
    if route.status != DeliveryRouteStatus.planned:
        raise HTTPException(status_code=400, detail="Faqat rejalashtirilgan marshrutni tahrirlash mumkin")

    old_keys = {s.group_key for s in route.stops}
    new_keys = set(data.group_keys)
    added = [k for k in data.group_keys if k not in old_keys]
    changed = []
    if added:
        added_stops = _validate_stops(db, cid, added, exclude_route_id=route.id)
        changed = [st for st in added_stops.values() if st.assign(route.courier_id)]
    removed = old_keys - new_keys
    if removed:
        for st in _load_stops(db, cid, list(removed)).values():
            st.release()

    route.stops.clear()
    db.flush()
    for i, k in enumerate(data.group_keys, start=1):
        route.stops.append(DeliveryRouteStop(group_key=k, sequence=i))
    db.commit()
    db.refresh(route)
    if changed:
        _notify_assigned(background_tasks, db, changed, route.courier_id)
    return _route_out(db, route)


@router.post("/routes/{route_id}/start")
def start_route(route_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    """Kuryer yo'lga chiqdi — barcha yakunlanmagan to'xtovlar "yo'lda"."""
    route = _get_route(db, route_id, current_user.company_id, lock=True)
    if route.status != DeliveryRouteStatus.planned:
        raise HTTPException(status_code=400, detail="Faqat rejalashtirilgan marshrutni boshlash mumkin")
    stops = _load_stops(db, route.company_id, [s.group_key for s in route.stops])
    moved = [st for st in stops.values() if st.start()]
    route.status = DeliveryRouteStatus.in_progress
    route.started_at = datetime.now(timezone.utc)
    db.commit()

    from app.routers.orders import _notify_customer_status
    for st in moved:
        if not st.is_sale:
            background_tasks.add_task(_notify_customer_status, db, st.orders, OrderStatus.on_way)
    return _route_out(db, route)


class StopStatusIn(BaseModel):
    status: str  # delivered | cancelled


@router.post("/routes/{route_id}/stops/{group_key}/status")
def set_stop_status(route_id: int, group_key: str, data: StopStatusIn, background_tasks: BackgroundTasks,
                    db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    """To'xtovni "yetkazildi" yoki "yetkazilmadi" deb belgilash.
    Telegram buyurtmasi — avto-sotuv (sozlama yoqilgan bo'lsa);
    sotuv yetkazmasi — faqat yetkazish haqi moliyaga yoziladi."""
    route = _get_route(db, route_id, current_user.company_id, lock=True)
    if route.status != DeliveryRouteStatus.in_progress:
        raise HTTPException(status_code=400, detail="Avval marshrutni boshlang")
    if group_key not in {s.group_key for s in route.stops}:
        raise HTTPException(status_code=404, detail="Bu buyurtma marshrutda yo'q")
    if data.status not in ("delivered", "cancelled"):
        raise HTTPException(status_code=400, detail="Faqat 'delivered' yoki 'cancelled' mumkin")

    st = _load_stops(db, route.company_id, [group_key]).get(group_key)
    if not st or st.is_final:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon yakunlangan")

    delivered = data.status == "delivered"
    st.finish(delivered)
    if st.is_sale and delivered:
        sd_service.record_fee_once(db, st.delivery, current_user)
    db.commit()

    if not st.is_sale:
        new_status = OrderStatus(data.status)
        from app.routers.orders import _notify_customer_status
        background_tasks.add_task(_notify_customer_status, db, st.orders, new_status)
        if delivered:
            from app.services.order_to_sale import maybe_create_sale_for_delivered_group
            background_tasks.add_task(maybe_create_sale_for_delivered_group, db, st.orders)
    return _route_out(db, route)


@router.post("/routes/{route_id}/complete")
def complete_route(route_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    """Marshrutni yopish. Yetkazilmay qolganlar qayta rejalashtirishga qaytadi."""
    route = _get_route(db, route_id, current_user.company_id, lock=True)
    if route.status != DeliveryRouteStatus.in_progress:
        raise HTTPException(status_code=400, detail="Faqat jarayondagi marshrutni yakunlash mumkin")
    for st in _load_stops(db, route.company_id, [s.group_key for s in route.stops]).values():
        st.release()
    route.status = DeliveryRouteStatus.completed
    route.completed_at = datetime.now(timezone.utc)
    db.commit()
    return _route_out(db, route)


@router.post("/routes/{route_id}/cancel")
def cancel_route(route_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(require_roles(*MANAGE_ROLES))):
    route = _get_route(db, route_id, current_user.company_id, lock=True)
    if route.status != DeliveryRouteStatus.planned:
        raise HTTPException(status_code=400, detail="Faqat rejalashtirilgan marshrutni bekor qilish mumkin")
    for st in _load_stops(db, route.company_id, [s.group_key for s in route.stops]).values():
        st.release()
    route.status = DeliveryRouteStatus.cancelled
    db.commit()
    return _route_out(db, route)
