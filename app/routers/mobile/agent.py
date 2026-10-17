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
from app.models.warehouse import Warehouse
from app.services.mobile_service import distance_m, ensure_personal_wallet, idem_get, idem_put, personal_cash_balance
from app.services.warehouse_resolver import SALE_TYPES, resolve_warehouse
from app.services.warehouse_scope import sellable_warehouses_query, stock_totals
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
    # T1.17: katalogdan cost_price olib tashlandi — "tannarx" narx turidagi mijozlar uchun narx
    # serverda hisoblanib `prices` ga qo'shiladi (maxsus narx ustun; backend resolve_price bilan bir xil)
    cost_ids = [c.id for c in customers if (c.price_type or "sale") == "cost"]
    if cost_ids:
        for pid, cost, sale in db.query(Product.id, Product.cost_price, Product.sale_price).filter(
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,  # noqa: E712
            Product.status == ProductStatus.active,
            Product.product_type.notin_(["raw_material", "service"]),
        ).limit(5000).all():
            val = float(cost or sale or 0)
            for cid_ in cost_ids:
                prices.setdefault(cid_, {}).setdefault(str(pid), val)
    return [_customer_out(c, prices.get(c.id)) for c in customers]


@router.get("/plan")
def today_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(agent_user),
    date: Optional[str] = None,  # YYYY-MM-DD; bo'sh bo'lsa bugun
):
    """Kunlik reja: hafta kuni avto + menejer tomonidan rejalashtirilgan tashriflar.
    Ikkala manba birlashtiriladi, tashrif holati (planned/visited/cancelled) ko'rsatiladi."""
    from datetime import date as date_type
    try:
        plan_date = date_type.fromisoformat(date) if date else local_today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri sana formati. YYYY-MM-DD kerak.")

    weekday = plan_date.isoweekday()
    start = local_day_start(plan_date)
    end = start + timedelta(days=1)

    customers = db.query(Customer).filter(
        Customer.company_id == current_user.company_id, Customer.agent_id == current_user.id,
    ).all()
    cust_map = {c.id: c for c in customers}

    # 1) Hafta kuni bo'yicha avto-reja
    workday_ids = {c.id for c in customers if weekday in (c.work_days or [])}

    # 2) Menejer tomonidan aniq sana uchun rejalashtirilgan
    planned_visits = db.query(AgentVisit).filter(
        AgentVisit.agent_id == current_user.id,
        AgentVisit.planned_date == plan_date,
        AgentVisit.planned == True,  # noqa: E712
    ).all()
    planned_visit_map = {v.customer_id: v for v in planned_visits}

    # 3) Shu kunda haqiqiy bo'lgan tashriflar (check_in_at bo'yicha)
    actual_visits = db.query(AgentVisit).filter(
        AgentVisit.agent_id == current_user.id,
        AgentVisit.check_in_at >= start,
        AgentVisit.check_in_at < end,
        AgentVisit.planned == False,  # noqa: E712
    ).order_by(AgentVisit.check_in_at).all()
    actual_by_cust: dict = {}
    for v in actual_visits:
        actual_by_cust[v.customer_id] = _visit_out(v)

    # Barcha rejalashtirilgan mijozlar (avto + qo'lda)
    all_planned_ids = workday_ids | set(planned_visit_map.keys())
    planned_items = []
    for cid in all_planned_ids:
        c = cust_map.get(cid)
        if not c:
            continue
        pv = planned_visit_map.get(cid)
        actual = actual_by_cust.get(cid)
        if actual:
            visit_status = "visited"
            visit_data = actual
        elif pv and (pv.status or "planned") == "cancelled":
            visit_status = "cancelled"
            visit_data = _visit_out(pv)
        else:
            visit_status = "planned"
            visit_data = _visit_out(pv) if pv else None
        planned_items.append({
            **_customer_out(c),
            "visit": visit_data,
            "visit_status": visit_status,
            "plan_visit_id": pv.id if pv else None,
        })

    # Rejalanmagan, lekin haqiqiy bo'lgan tashriflar
    unplanned = [
        {**v, "customer_name": cust_map[cid].name if cid in cust_map else "—"}
        for cid, v in actual_by_cust.items() if cid not in all_planned_ids
    ]

    return {
        "date": plan_date.isoformat(),
        "weekday": weekday,
        "planned": planned_items,
        "unplanned_visits": unplanned,
    }


# ── Tashriflar ───────────────────────────────────────────────────────────────

def _visit_out(v: AgentVisit) -> dict:
    return {
        "id": v.id, "customer_id": v.customer_id, "planned": v.planned,
        "planned_date": v.planned_date.isoformat() if v.planned_date else None,
        "status": v.status or "visited",
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
    today = local_today()
    is_planned = today.isoweekday() in (c.work_days or [])
    # Menejer rejalashtirilgan tashrif bormi — bo'lsa o'sha yozuvni yangilaymiz
    existing_plan = db.query(AgentVisit).filter(
        AgentVisit.agent_id == current_user.id,
        AgentVisit.customer_id == c.id,
        AgentVisit.planned_date == today,
        AgentVisit.planned == True,  # noqa: E712
        AgentVisit.status == "planned",
    ).first()
    if existing_plan:
        v = existing_plan
        v.lat, v.lng = data.lat, data.lng
        v.distance_m = dist
        v.within_radius = None if dist is None else dist <= radius
        v.check_in_at = _client_time(data.check_in_at) or datetime.now(timezone.utc)
        v.check_out_at = _client_time(data.check_out_at)
        v.result = data.result
        v.note = data.note
        v.status = "visited"
    else:
        v = AgentVisit(
            company_id=current_user.company_id, agent_id=current_user.id, customer_id=c.id,
            planned=is_planned, planned_date=today if is_planned else None,
            status="visited",
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
    """Sotiladigan mahsulotlar (xom ashyo va xizmatlardan tashqari) va agent filialining
    sotiladigan omborlaridagi qoldiq (T1.17). Narx mijozga qarab ilovada hisoblanadi: maxsus
    narx > price_type (sale/wholesale); "tannarx" mijozlar narxi /customers `prices` da keladi.
    Tannarx (cost_price) agentga berilmaydi."""
    from app.core.branch_context import effective_branch_id
    # T1.5: faqat faol main/shop omborlar (returns/transit/raw_material/wip qoldig'i agentga ko'rinmaydi)
    agent_branch_id = effective_branch_id(db, current_user)
    wh_ids = [w.id for w in sellable_warehouses_query(
        db, current_user.company_id, branch_id=agent_branch_id,
    ).filter(Warehouse.type.in_(SALE_TYPES)).order_by(Warehouse.id).all()]
    products = db.query(Product).filter(
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,  # noqa: E712
        Product.status == ProductStatus.active,
        Product.product_type.notin_(["raw_material", "service"]),
    ).order_by(Product.name).limit(5000).all()
    stock = stock_totals(db, [p.id for p in products], wh_ids)
    # T4.3: agent filialining narxlari (bo'lsa korxona narxini ustidan yozadi; NULL ustun korxona narxida qoladi)
    from app.services.branch_price_service import get_branch_prices
    branch_prices = get_branch_prices(db, current_user.company_id, agent_branch_id, [p.id for p in products])

    def _prices(p):
        bp = branch_prices.get((p.id, None))
        sale = float(p.sale_price or 0)
        wholesale = float(p.wholesale_price or 0) if p.wholesale_price else None
        if bp is None:
            return sale, wholesale, "product"
        if bp.sale_price is not None:
            sale = float(bp.sale_price)
        if bp.wholesale_price is not None:
            wholesale = float(bp.wholesale_price)
        return sale, wholesale, "branch"

    out = []
    for p in products:
        sale, wholesale, source = _prices(p)
        out.append({
            "id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode, "unit": p.unit,
            "sale_price": sale,
            "wholesale_price": wholesale,
            "price_source": source,
            "stock": float(stock.get(p.id, 0) or 0),
            "image_url": p.image_url,
        })
    return out


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
    lat: Optional[float] = None
    lng: Optional[float] = None


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

    # ── Geo-radius tekshiruvi: agent do'kon radiusida bo'lishi shart ──
    from app.models.company import Company
    comp = db.query(Company).filter(Company.id == current_user.company_id).first()
    geo_check_enabled = getattr(comp, "agent_order_geo_radius_check", True) if comp else True

    radius = c.visit_radius_m or DEFAULT_RADIUS_M
    if geo_check_enabled:
        if data.visit_id:
            v = db.query(AgentVisit).filter(AgentVisit.id == data.visit_id, AgentVisit.agent_id == current_user.id).first()
            if v and v.within_radius is False:
                raise HTTPException(
                    status_code=400,
                    detail=f"Siz do'kon radiusidan tashqaridasiz ({v.distance_m} m, ruxsat: {radius} m). Buyurtma faqat do'kon yaqinida qabul qilinadi."
                )
        if c.lat is not None and c.lng is not None:
            if data.lat is not None and data.lng is not None:
                dist = distance_m(data.lat, data.lng, c.lat, c.lng)
                if dist is not None and dist > radius:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Siz do'kondan {dist} metr uzoqdasiz (ruxsat: {radius} m). Buyurtma faqat do'kon yaqinida qabul qilinadi."
                    )
            elif not data.visit_id:
                raise HTTPException(
                    status_code=400,
                    detail="Buyurtma berish uchun GPS joylashuvingiz kerak. Do'kon yaqinida bo'lishingiz shart."
                )
    # Birinchi buyurtmada do'kon nuqtasi hali belgilanmagan bo'lsa — agent koordinatasini saqlash
    if c.lat is None and data.lat is not None:
        c.lat, c.lng, c.location_source = round(data.lat, 7), round(data.lng, 7), "agent"

    from app.schemas.sale import SaleCreate
    from app.services.sale_create import create_pending_sale

    note = "📱 Agent buyurtmasi" + (f": {data.note}" if data.note else "")
    delivery = None
    if data.delivery and company_has_feature(db, current_user.company_id, "distribution"):
        delivery = {"planned_date": data.planned_date} if data.planned_date else {}
    # T1.5: ombor — mijoz filiali (agent shu filialga ruxsatli bo'lsa), aks holda agent filiali;
    # main/shop turidagi default ombor, filialda ombor yo'q bo'lsa 409 (boshqa filialga o'tilmaydi)
    from app.core.branch_context import effective_branch_ids, effective_branch_id
    agent_branch = effective_branch_id(db, current_user)
    allowed = effective_branch_ids(db, current_user)
    cust_branch = c.branch_id if (c.branch_id and (not allowed or c.branch_id in allowed)) else None
    warehouse_id = resolve_warehouse(
        db, current_user.company_id, branch_id=cust_branch or agent_branch,
        customer_branch_id=cust_branch, purpose="order",
    )
    payload = SaleCreate(
        items=[{"product_id": it.product_id, "quantity": it.quantity} for it in data.items],
        payment_type="debt", paid_amount=0, customer_id=c.id, note=note, delivery=delivery,
        warehouse_id=warehouse_id,
    )
    # create_pending_sale commit qiladi — idempotentlik yozuvi o'sha tranzaksiyaga kirishi uchun oldin qo'shamiz
    idem_row = idem_put(db, current_user, idempotency_key, "agent/orders", {"pending": True})
    sale = create_pending_sale(db, payload, current_user, agent_id=current_user.id)
    if data.visit_id:
        v = db.query(AgentVisit).filter(AgentVisit.id == data.visit_id, AgentVisit.agent_id == current_user.id).first()
        if v:
            v.result = "order"
    out = _order_out(sale)
    # Kredit limiti — buyurtma qabul qilinadi, lekin yakunlashda (PUT /sales/{id}, ulgurji sahifa) BLOKLANADI
    # (credit_service.check_credit_limit); agentga ogohlantirish beriladi.
    from app.services.credit_service import credit_limit_applies
    if credit_limit_applies(db, c):
        new_debt = float(c.debt_balance or 0) + out["total"]
        if new_debt > float(c.debt_limit):
            out["warning"] = (
                f"Kredit limitidan oshadi: {new_debt:,.0f} / {float(c.debt_limit):,.0f}. "
                f"Buyurtmani yakunlashda bloklanadi — qarz yopilishi yoki limit oshirilishi kerak"
            ).replace(",", " ")
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
    # T2.6: yagona servis (`customer_ledger.pay_debt`); agentning shaxsiy (qo'l) kassasi saqlanadi
    from app.services import customer_ledger
    reason = f"Agent {current_user.name} qabul qildi" + (f": {data.note}" if data.note else "")
    placeholder = {"customer_id": c.id, "amount": float(data.amount)}
    idem_row = idem_put(db, current_user, idempotency_key, "agent/payments", placeholder)
    res = customer_ledger.pay_debt(
        db, c, user=current_user,
        payments=[{"amount": data.amount, "currency": "UZS", "payment_type": "cash"}],
        wallet_id=wallet.id, reason=reason,
    )
    db.commit()  # idempotentlik yozuvi ham shu tranzaksiyada saqlanadi
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
    from app.core.branch_context import effective_branch_id
    from app.routers.customers import CustomerIn, create_customer
    body = CustomerIn(
        name=data.name.strip(), phone=(data.phone or "").strip() or None,
        address=data.address, region=data.region, district=data.district,
        lat=data.lat, lng=data.lng, location_source="map" if data.lat is not None else None,
        work_days=[d for d in data.work_days if 1 <= d <= 7], agent_id=current_user.id,
        # T1.5: agent yaratgan mijoz agent filialiga yoziladi (filialsiz agentda None)
        branch_id=effective_branch_id(db, current_user),
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
        "cash_on_hand": float(personal_cash_balance(db, wallet)),  # T3.14: faqat naqd (karta tushumi kirmaydi)
    }
    db.commit()
    return out


# ── Menejer: Agent tashriflarini rejalashtirish (CRM tomoni) ─────────────────

PLAN_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)


class PlanVisitIn(BaseModel):
    agent_id: int
    customer_id: int
    planned_date: str  # YYYY-MM-DD
    note: Optional[str] = Field(None, max_length=500)


class PlanVisitBulkIn(BaseModel):
    agent_id: int
    planned_date: str  # YYYY-MM-DD
    customer_ids: List[int] = Field(..., min_length=1, max_length=200)


@router.post("/visits/plan", status_code=201)
def create_planned_visit(
    data: PlanVisitIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Menejer agent uchun aniq sanaga tashrif rejalashtiradi."""
    from datetime import date as date_type
    try:
        pd = date_type.fromisoformat(data.planned_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri sana formati. YYYY-MM-DD kerak.")
    agent = db.query(User).filter(
        User.id == data.agent_id, User.company_id == current_user.company_id,
        User.role == UserRole.agent,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent topilmadi")
    customer = db.query(Customer).filter(
        Customer.id == data.customer_id, Customer.company_id == current_user.company_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    existing = db.query(AgentVisit).filter(
        AgentVisit.agent_id == data.agent_id,
        AgentVisit.customer_id == data.customer_id,
        AgentVisit.planned_date == pd,
        AgentVisit.planned == True,  # noqa: E712
    ).first()
    if existing:
        return _visit_out(existing)
    v = AgentVisit(
        company_id=current_user.company_id,
        agent_id=data.agent_id,
        customer_id=data.customer_id,
        planned=True,
        planned_date=pd,
        status="planned",
        note=data.note,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return _visit_out(v)


@router.post("/visits/plan/bulk", status_code=201)
def create_planned_visits_bulk(
    data: PlanVisitBulkIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Menejer agent uchun bir necha mijozni birdan rejalashtiradi."""
    from datetime import date as date_type
    try:
        pd = date_type.fromisoformat(data.planned_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri sana formati. YYYY-MM-DD kerak.")
    agent = db.query(User).filter(
        User.id == data.agent_id, User.company_id == current_user.company_id,
        User.role == UserRole.agent,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent topilmadi")
    existing_ids = {
        v.customer_id for v in db.query(AgentVisit).filter(
            AgentVisit.agent_id == data.agent_id,
            AgentVisit.planned_date == pd,
            AgentVisit.planned == True,  # noqa: E712
        ).all()
    }
    created = 0
    for cid in data.customer_ids:
        if cid in existing_ids:
            continue
        customer = db.query(Customer).filter(
            Customer.id == cid, Customer.company_id == current_user.company_id,
        ).first()
        if not customer:
            continue
        db.add(AgentVisit(
            company_id=current_user.company_id,
            agent_id=data.agent_id,
            customer_id=cid,
            planned=True,
            planned_date=pd,
            status="planned",
        ))
        created += 1
    db.commit()
    return {"created": created, "skipped": len(data.customer_ids) - created}


@router.delete("/visits/{visit_id}/plan", status_code=200)
def cancel_planned_visit(
    visit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Rejalashtirilgan tashrifni bekor qilish (menejer)."""
    v = db.query(AgentVisit).filter(
        AgentVisit.id == visit_id,
        AgentVisit.company_id == current_user.company_id,
        AgentVisit.planned == True,  # noqa: E712
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="Rejalashtirilgan tashrif topilmadi")
    v.status = "cancelled"
    db.commit()
    return {"ok": True, "visit_id": visit_id}


@router.get("/visits/report")
def visits_report(
    agent_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Menejer uchun: agentlar tashriflari hisoboti (filter: agent, sana oraliq)."""
    from datetime import date as date_type
    from sqlalchemy import or_, and_
    today = local_today()
    try:
        d_from = date_type.fromisoformat(date_from) if date_from else today
        d_to = date_type.fromisoformat(date_to) if date_to else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Noto'g'ri sana formati. YYYY-MM-DD kerak.")
    start = local_day_start(d_from)
    end = local_day_start(d_to) + timedelta(days=1)
    q = db.query(AgentVisit).filter(AgentVisit.company_id == current_user.company_id)
    if agent_id:
        q = q.filter(AgentVisit.agent_id == agent_id)
    q = q.filter(or_(
        and_(AgentVisit.planned == True, AgentVisit.planned_date >= d_from, AgentVisit.planned_date <= d_to),  # noqa: E712
        and_(AgentVisit.planned == False, AgentVisit.check_in_at >= start, AgentVisit.check_in_at < end),  # noqa: E712
    ))
    visits = q.order_by(AgentVisit.planned_date, AgentVisit.check_in_at).all()
    agent_ids = {v.agent_id for v in visits}
    cust_ids = {v.customer_id for v in visits}
    agents = {u.id: u.name for u in db.query(User).filter(User.id.in_(agent_ids)).all()} if agent_ids else {}
    custs = {c.id: c.name for c in db.query(Customer).filter(Customer.id.in_(cust_ids)).all()} if cust_ids else {}
    return [
        {**_visit_out(v), "agent_name": agents.get(v.agent_id, "—"), "customer_name": custs.get(v.customer_id, "—")}
        for v in visits
    ]
