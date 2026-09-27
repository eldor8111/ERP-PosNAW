"""
Savdo agenti ish maydoni: mijozlarim, kunlik reja, tashrif (check-in/out),
katalog, buyurtma (oflayn, idempotent), qarz yig'ish, yangi mijoz, KPI.

Agent faqat o'ziga biriktirilgan (Customer.agent_id) mijozlarni ko'radi.
Buyurtma — "to'lovsiz saqlangan" (pending) sotuv: omborchi/menejer
Ulgurji sotuv ekranida tekshirib yakunlaydi (qoldiq, limit, kassa o'shanda).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.features import company_has_feature, require_feature
from app.database import get_db
from app.models.agent_visit import AgentVisit
from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.inventory import StockLevel
from app.models.product import Product, ProductStatus
from app.models.sale import Sale, SaleStatus
from app.models.user import User, UserRole
from app.services.mobile_service import distance_m, ensure_personal_wallet, idem_get, idem_put
from app.utils.report_utils import local_day_start, local_today

router = APIRouter(prefix="/mobile/agent", tags=["mobile-agent"],
                   dependencies=[Depends(require_feature("distribution"))])

agent_user = require_roles(UserRole.agent)
DEFAULT_RADIUS_M = 150
VISIT_PHOTO_DIR = os.path.join("uploads_private", "visit_photos")


def _my_customer(db: Session, user: User, customer_id: int) -> Customer:
    c = db.query(Customer).filter(
        Customer.id == customer_id, Customer.company_id == user.company_id, Customer.agent_id == user.id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi yoki sizga biriktirilmagan")
    return c


def _customer_out(c: Customer, prices: Optional[dict] = None) -> dict:
    return {
        "id": c.id, "name": c.name, "phone": c.phone,
        "address": ", ".join(x for x in (c.district, c.address) if x) or None,
        "lat": float(c.lat) if c.lat is not None else None,
        "lng": float(c.lng) if c.lng is not None else None,
        "debt": float(c.debt_balance or 0),
        "debt_limit": float(c.debt_limit or 0),
        "price_type": c.price_type or "sale",
        "discount_percent": float(c.discount_percent or 0),
        "customer_type": c.customer_type,
        "work_days": list(c.work_days or []),
        "visit_radius_m": c.visit_radius_m,
        "photo_url": c.photo_url,
        "prices": prices or {},   # maxsus narxlar {product_id: narx} — oflayn narx hisobi uchun
    }


# ── Mijozlar va reja ─────────────────────────────────────────────────────────

@router.get("/customers")
def my_customers(db: Session = Depends(get_db), current_user: User = Depends(agent_user)):
    """Barcha biriktirilgan mijozlar (oflayn kesh uchun bir yo'la)."""
    customers = db.query(Customer).filter(
        Customer.company_id == current_user.company_id, Customer.agent_id == current_user.id,
    ).order_by(Customer.name).limit(3000).all()
    ids = [c.id for c in customers]
    prices: dict = {}
    if ids:
        for cp in db.query(CustomerPrice).filter(CustomerPrice.customer_id.in_(ids)).all():
            prices.setdefault(cp.customer_id, {})[str(cp.product_id)] = float(cp.price)
    return [_customer_out(c, prices.get(c.id)) for c in customers]


@router.get("/plan")
def today_plan(db: Session = Depends(get_db), current_user: User = Depends(agent_user)):
    """Bugungi hafta kuniga (Toshkent vaqti) mos mijozlar + bugungi tashriflar."""
    today = local_today()
    weekday = today.isoweekday()
    start = local_day_start(today)
    customers = db.query(Customer).filter(
        Customer.company_id == current_user.company_id, Customer.agent_id == current_user.id,
    ).all()
    planned = [c for c in customers if weekday in (c.work_days or [])]
    visits = db.query(AgentVisit).filter(
        AgentVisit.agent_id == current_user.id, AgentVisit.check_in_at >= start,
    ).order_by(AgentVisit.check_in_at).all()
    by_customer: dict = {}
    for v in visits:
        by_customer[v.customer_id] = _visit_out(v)
    names = {c.id: c.name for c in customers}
    return {
        "date": today.isoformat(),
        "weekday": weekday,
        "planned": [{**_customer_out(c), "visit": by_customer.get(c.id)} for c in planned],
        "unplanned_visits": [
            {**v, "customer_name": names.get(v["customer_id"])}
            for cid_, v in by_customer.items() if cid_ not in {c.id for c in planned}
        ],
    }


# ── Tashriflar ───────────────────────────────────────────────────────────────

def _visit_out(v: AgentVisit) -> dict:
    return {
        "id": v.id, "customer_id": v.customer_id, "planned": v.planned,
        "check_in_at": v.check_in_at.isoformat() if v.check_in_at else None,
        "check_out_at": v.check_out_at.isoformat() if v.check_out_at else None,
        "distance_m": v.distance_m, "within_radius": v.within_radius,
        "result": v.result, "note": v.note,
    }


class CheckInIn(BaseModel):
    customer_id: int
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    # Oflayn ilova tashrifni oxirida bitta so'rovda yuboradi (telefon vaqti bilan)
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    result: Optional[str] = Field(None, pattern="^(order|no_order|closed|payment)$")
    note: Optional[str] = Field(None, max_length=500)


def _client_time(t: Optional[datetime]) -> Optional[datetime]:
    """Telefon vaqti — kelajakdagi yoki 3 kundan eski qiymat qabul qilinmaydi."""
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return t if now - timedelta(days=3) <= t <= now + timedelta(minutes=5) else now


@router.post("/visits")
def check_in(data: CheckInIn, db: Session = Depends(get_db), current_user: User = Depends(agent_user),
             idempotency_key: Optional[str] = Header(None)):
    prev = idem_get(db, current_user, idempotency_key)
    if prev is not None:
        return prev
    c = _my_customer(db, current_user, data.customer_id)
    dist = distance_m(data.lat, data.lng, c.lat, c.lng)
    radius = c.visit_radius_m or DEFAULT_RADIUS_M
    # Do'kon nuqtasi hali belgilanmagan bo'lsa — birinchi tashrifda agent turgan joy
    if c.lat is None and data.lat is not None:
        c.lat, c.lng, c.location_source = round(data.lat, 7), round(data.lng, 7), "agent"
    v = AgentVisit(
        company_id=current_user.company_id, agent_id=current_user.id, customer_id=c.id,
        planned=local_today().isoweekday() in (c.work_days or []),
        lat=data.lat, lng=data.lng, distance_m=dist,
        within_radius=None if dist is None else dist <= radius,
        check_in_at=_client_time(data.check_in_at) or datetime.now(timezone.utc),
        check_out_at=_client_time(data.check_out_at),
        result=data.result, note=data.note,
    )
    db.add(v)
    db.flush()
    out = _visit_out(v)
    idem_put(db, current_user, idempotency_key, "agent/visits", out)
    db.commit()
    return out


class CheckOutIn(BaseModel):
    result: str = Field(..., pattern="^(order|no_order|closed|payment)$")
    note: Optional[str] = Field(None, max_length=500)


@router.post("/visits/{visit_id}/checkout")
def check_out(visit_id: int, data: CheckOutIn, db: Session = Depends(get_db), current_user: User = Depends(agent_user)):
    v = db.query(AgentVisit).filter(AgentVisit.id == visit_id, AgentVisit.agent_id == current_user.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Tashrif topilmadi")
    if v.check_out_at is None:
        v.check_out_at = datetime.now(timezone.utc)
    v.result = data.result
    v.note = data.note
    db.commit()
    return _visit_out(v)


@router.post("/visits/{visit_id}/photo", status_code=201)
async def visit_photo(visit_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                      current_user: User = Depends(agent_user)):
    from app.routers.customer_profile import _image_ext
    v = db.query(AgentVisit).filter(AgentVisit.id == visit_id, AgentVisit.agent_id == current_user.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Tashrif topilmadi")
    content = await file.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Rasm hajmi 8 MB dan oshmasligi kerak")
    ext = _image_ext(content)
    rel = os.path.join(str(current_user.company_id), f"{uuid.uuid4().hex}.{ext}")
    os.makedirs(os.path.join(VISIT_PHOTO_DIR, str(current_user.company_id)), exist_ok=True)
    with open(os.path.join(VISIT_PHOTO_DIR, rel), "wb") as f:
        f.write(content)
    v.photo_path = rel.replace("\\", "/")
    db.commit()
    return {"ok": True}


# ── Katalog ──────────────────────────────────────────────────────────────────

@router.get("/catalog")
def catalog(db: Session = Depends(get_db), current_user: User = Depends(agent_user)):
    """Sotiladigan mahsulotlar (xom ashyo va xizmatlardan tashqari) va umumiy
    qoldiq. Narx mijozga qarab ilovada hisoblanadi: maxsus narx >
    price_type (sale/wholesale/cost) — backend resolve_price bilan bir xil."""
    stock = dict(db.query(StockLevel.product_id, func.coalesce(func.sum(StockLevel.quantity), 0)).join(
        Product, Product.id == StockLevel.product_id,
    ).filter(Product.company_id == current_user.company_id).group_by(StockLevel.product_id).all())
    products = db.query(Product).filter(
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,  # noqa: E712
        Product.status == ProductStatus.active,
        Product.product_type.notin_(["raw_material", "service"]),
    ).order_by(Product.name).limit(5000).all()
    return [
        {
            "id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode, "unit": p.unit,
            "sale_price": float(p.sale_price or 0),
            "wholesale_price": float(p.wholesale_price or 0) if p.wholesale_price else None,
            "cost_price": float(p.cost_price or 0),
            "stock": float(stock.get(p.id, 0) or 0),
            "image_url": p.image_url,
        }
        for p in products
    ]


# ── Buyurtma ─────────────────────────────────────────────────────────────────

class OrderItemIn(BaseModel):
    product_id: int
    quantity: Decimal = Field(..., gt=0)


class AgentOrderIn(BaseModel):
    customer_id: int
    items: List[OrderItemIn] = Field(..., min_length=1, max_length=300)
    note: Optional[str] = Field(None, max_length=500)
    visit_id: Optional[int] = None
    delivery: bool = True
    planned_date: Optional[str] = None


def _order_out(s: Sale) -> dict:
    return {
        "id": s.id, "number": s.number, "status": s.status.value if hasattr(s.status, "value") else s.status,
        "customer_id": s.customer_id, "customer_name": s.customer.name if s.customer else None,
        "total": float(s.total_amount or 0), "items_count": len(s.items),
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "delivery_status": s.delivery.status.value if getattr(s, "delivery", None) else None,
    }


@router.post("/orders")
def create_order(data: AgentOrderIn, db: Session = Depends(get_db), current_user: User = Depends(agent_user),
                 idempotency_key: Optional[str] = Header(None)):
    prev = idem_get(db, current_user, idempotency_key)
    if prev is not None:
        return prev
    c = _my_customer(db, current_user, data.customer_id)
    from app.schemas.sale import SaleCreate
    from app.services.sale_create import create_pending_sale

    note = "📱 Agent buyurtmasi" + (f": {data.note}" if data.note else "")
    delivery = None
    if data.delivery and company_has_feature(db, current_user.company_id, "distribution"):
        delivery = {"planned_date": data.planned_date} if data.planned_date else {}
    payload = SaleCreate(
        items=[{"product_id": it.product_id, "quantity": it.quantity} for it in data.items],
        payment_type="debt", paid_amount=0, customer_id=c.id, note=note, delivery=delivery,
    )
    # create_pending_sale commit qiladi — idempotentlik yozuvi o'sha tranzaksiyaga kirishi uchun oldin qo'shamiz
    idem_row = idem_put(db, current_user, idempotency_key, "agent/orders", {"pending": True})
    sale = create_pending_sale(db, payload, current_user, agent_id=current_user.id)
    if data.visit_id:
        v = db.query(AgentVisit).filter(AgentVisit.id == data.visit_id, AgentVisit.agent_id == current_user.id).first()
        if v:
            v.result = "order"
    out = _order_out(sale)
    # Kredit limiti — faqat ogohlantirish (bloklash sotuv yakunlanganda, mavjud qoida bo'yicha)
    if (c.customer_type == "distributor") and float(c.debt_limit or 0) > 0:
        new_debt = float(c.debt_balance or 0) + out["total"]
        if new_debt > float(c.debt_limit):
            out["warning"] = f"Kredit limitidan oshadi: {new_debt:,.0f} / {float(c.debt_limit):,.0f}".replace(",", " ")
    if idem_row is not None:
        idem_row.response = out
    db.commit()
    return out


@router.get("/orders")
def my_orders(days: int = 14, db: Session = Depends(get_db), current_user: User = Depends(agent_user)):
    since = datetime.now(timezone.utc) - timedelta(days=min(max(days, 1), 90))
    sales = db.query(Sale).filter(
        Sale.company_id == current_user.company_id, Sale.agent_id == current_user.id, Sale.created_at >= since,
    ).order_by(Sale.created_at.desc()).limit(300).all()
    return [_order_out(s) for s in sales]


# ── Qarz yig'ish ─────────────────────────────────────────────────────────────

class PaymentIn(BaseModel):
    customer_id: int
    amount: Decimal = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=300)
    visit_id: Optional[int] = None


@router.post("/payments")
def collect_payment(data: PaymentIn, db: Session = Depends(get_db), current_user: User = Depends(agent_user),
                    idempotency_key: Optional[str] = Header(None)):
    """Naqd to'lov — agentning qo'l kassasiga kirim, qarz FIFO bo'yicha
    yopiladi (mavjud pay-debt mantig'i)."""
    prev = idem_get(db, current_user, idempotency_key)
    if prev is not None:
        return prev
    c = _my_customer(db, current_user, data.customer_id)
    if Decimal(str(data.amount)) > Decimal(str(c.debt_balance or 0)) + Decimal("0.01"):
        raise HTTPException(status_code=400, detail=f"To'lov qarzdan ko'p: qarz {float(c.debt_balance or 0):,.0f} so'm".replace(",", " "))
    wallet = ensure_personal_wallet(db, current_user)
    if data.visit_id:
        v = db.query(AgentVisit).filter(AgentVisit.id == data.visit_id, AgentVisit.agent_id == current_user.id).first()
        if v and v.result is None:
            v.result = "payment"
    from app.routers import customers as C
    reason = f"Agent {current_user.name} qabul qildi" + (f": {data.note}" if data.note else "")
    placeholder = {"customer_id": c.id, "amount": float(data.amount)}
    idem_row = idem_put(db, current_user, idempotency_key, "agent/payments", placeholder)
    res = C.pay_debt(c.id, C.DebtUpdate(amount=data.amount, reason=reason, wallet_id=wallet.id, payment_type="cash"),
                     db, current_user)  # commit ichida — idempotentlik yozuvi ham saqlanadi
    out = {**placeholder, "remaining_debt": res["remaining_debt"], "wallet_balance": float(wallet.balance or 0)}
    if idem_row is not None:
        idem_row.response = out
        db.commit()
    return out


# ── Yangi mijoz ──────────────────────────────────────────────────────────────

class NewCustomerIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = Field(None, max_length=500)
    region: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    work_days: List[int] = []


@router.post("/customers")
def add_customer(data: NewCustomerIn, db: Session = Depends(get_db), current_user: User = Depends(agent_user),
                 idempotency_key: Optional[str] = Header(None)):
    prev = idem_get(db, current_user, idempotency_key)
    if prev is not None:
        return prev
    from app.routers.customers import CustomerIn, create_customer
    body = CustomerIn(
        name=data.name.strip(), phone=(data.phone or "").strip() or None,
        address=data.address, region=data.region, district=data.district,
        lat=data.lat, lng=data.lng, location_source="map" if data.lat is not None else None,
        work_days=[d for d in data.work_days if 1 <= d <= 7], agent_id=current_user.id,
    )
    # create_customer telefon takrorini tekshiradi (409) va commit qiladi —
    # idempotentlik yozuvi o'sha commit'ga kirishi uchun oldin qo'shiladi
    idem_row = idem_put(db, current_user, idempotency_key, "agent/customers", {"pending": True})
    cust = create_customer(body, db, current_user)
    if data.lat is not None:
        cust.location_source = "agent"
    out = _customer_out(cust)
    if idem_row is not None:
        idem_row.response = out
    db.commit()
    return out


@router.post("/customers/{customer_id}/photo")
async def customer_photo(customer_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                         current_user: User = Depends(agent_user)):
    _my_customer(db, current_user, customer_id)
    from app.routers.customer_profile import upload_customer_photo
    return await upload_customer_photo(customer_id, file, db, current_user)


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(agent_user)):
    c = _my_customer(db, current_user, customer_id)
    sales = db.query(Sale).filter(Sale.customer_id == c.id, Sale.status != SaleStatus.cancelled).order_by(
        Sale.created_at.desc()).limit(10).all()
    visits = db.query(AgentVisit).filter(AgentVisit.customer_id == c.id).order_by(AgentVisit.check_in_at.desc()).limit(5).all()
    return {
        **_customer_out(c),
        "recent_sales": [
            {"id": s.id, "number": s.number, "total": float(s.total_amount or 0),
             "paid": float(s.paid_amount or 0) * float(s.exchange_rate or 1),
             "status": s.status.value, "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in sales
        ],
        "recent_visits": [_visit_out(v) for v in visits],
    }


# ── KPI ──────────────────────────────────────────────────────────────────────

@router.get("/kpi")
def kpi(db: Session = Depends(get_db), current_user: User = Depends(agent_user)):
    from app.models.moliya import KassaMovement
    today = local_today()
    day0, month0 = local_day_start(today), local_day_start(today.replace(day=1))
    wallet = ensure_personal_wallet(db, current_user)

    def orders_since(t0):
        q = db.query(func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0)).filter(
            Sale.agent_id == current_user.id, Sale.created_at >= t0, Sale.status != SaleStatus.cancelled)
        n, s = q.first()
        return {"count": int(n or 0), "sum": float(s or 0)}

    def collected_since(t0):
        s = db.query(func.coalesce(func.sum(KassaMovement.amount), 0)).filter(
            KassaMovement.wallet_id == wallet.id, KassaMovement.direction == "in",
            KassaMovement.reference_type == "customer_payment", KassaMovement.created_at >= t0).scalar()
        return float(s or 0)

    weekday = today.isoweekday()
    planned = sum(1 for (wd,) in db.query(Customer.work_days).filter(
        Customer.company_id == current_user.company_id, Customer.agent_id == current_user.id).all() if weekday in (wd or []))
    visited = db.query(func.count(func.distinct(AgentVisit.customer_id))).filter(
        AgentVisit.agent_id == current_user.id, AgentVisit.check_in_at >= day0, AgentVisit.planned == True).scalar()  # noqa: E712
    out = {
        "today": {"orders": orders_since(day0), "collected": collected_since(day0),
                  "visits_planned": planned, "visits_done": int(visited or 0)},
        "month": {"orders": orders_since(month0), "collected": collected_since(month0)},
        "cash_on_hand": float(wallet.balance or 0),
    }
    db.commit()
    return out
