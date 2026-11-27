"""Restoran: stol bron qilish (R8.1).

* Bron: filial, stol(lar), boshlanish vaqti, davomiylik, mehmonlar, ism, telefon (mijoz telefon bo'yicha
  bog'lanadi), izoh. Holat: booked -> arrived | no_show | cancelled.
* Bir stolga faol bronlar vaqti kesishmaydi (409 TABLE_BUSY). Faol: `booked` va cheki hali yopilmagan `arrived`.
  Tekshiruv paytida stollar qulflanadi (bir vaqtda ikki bron yozilmasin).
* Depozit bron paytida kassaga kirim qilinadi (Transaction + KassaMovement, `reference_type='reservation_deposit'`).
  Mehmon kelganda ochilgan chek to'langanda depozit `deposit` to'lov qatori bo'lib qo'llanadi (kassaga qayta kirim
  qilinmaydi); chekdan ortiq qismi naqd qaytariladi. Bekor qilinganda qaytarilishi mumkin, kelmasa qoladi.
* Eslatma: bron vaqtidan `reservation_remind_hours` oldin mijozga Telegram (korxona boti va mijoz chat_id), bo'lmasa
  sozlamada yoqilgan bo'lsa SMS.
"""
import re
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.restaurant import Hall, Reservation, RestaurantTable
from app.models.user import User

ZERO = Decimal("0")
CENT = Decimal("0.01")
STATUSES = ("booked", "arrived", "no_show", "cancelled")
PAY_TYPES = ("cash", "card", "uzcard", "humo", "click", "payme", "uzum")
DEPOSIT_REF = "reservation_deposit"
REFUND_REF = "reservation_deposit_refund"
MAX_TABLES = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _local_tz():
    from app.utils.report_utils import LOCAL_TZ
    return LOCAL_TZ


def _money(v) -> Decimal:
    try:
        return Decimal(str(v or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Summa noto'g'ri")


def parse_dt(v) -> datetime:
    """ISO vaqt -> UTC (tzsiz). Zonasiz qiymat mahalliy (Toshkent) vaqt deb olinadi."""
    if isinstance(v, datetime):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Vaqt noto'g'ri")
    if d.tzinfo is None:
        d = d.replace(tzinfo=_local_tz())
    return d.astimezone(timezone.utc).replace(tzinfo=None)


def iso(d: Optional[datetime]) -> Optional[str]:
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def local_day_bounds(day: date_cls) -> tuple:
    tz = _local_tz()
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)
    return (start.astimezone(timezone.utc).replace(tzinfo=None), end.astimezone(timezone.utc).replace(tzinfo=None))


def _digits(phone) -> str:
    return re.sub(r"\D", "", phone or "")


def find_customer(db: Session, company_id: int, phone: Optional[str]):
    """Telefonning oxirgi 9 raqami bo'yicha korxona mijozi (bitta topilsa)."""
    from app.models.customer import Customer
    d = _digits(phone)
    if len(d) < 9:
        return None
    tail = d[-9:]
    rows = db.query(Customer).filter(Customer.company_id == company_id, Customer.phone.isnot(None),
                                     Customer.phone.like(f"%{tail[-4:]}%")).limit(200).all()
    hits = [c for c in rows if _digits(c.phone)[-9:] == tail and getattr(c, "is_active", True) is not False]
    return hits[0] if len(hits) == 1 else None


# ── stollar va bandlik ─────────────────────────────────────────────

def _tables(db: Session, company_id: int, branch_id: int, table_ids, lock: bool = False) -> list:
    try:
        ids = sorted({int(x) for x in (table_ids or [])})
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Stol noto'g'ri")
    if not ids:
        raise HTTPException(status_code=400, detail="Stol tanlanmagan")
    if len(ids) > MAX_TABLES:
        raise HTTPException(status_code=400, detail=f"Bir bronda {MAX_TABLES} tadan ko'p stol bo'lmasin")
    q = (db.query(RestaurantTable).join(Hall, Hall.id == RestaurantTable.hall_id)
         .filter(RestaurantTable.id.in_(ids), RestaurantTable.company_id == company_id,
                 RestaurantTable.is_active == True, Hall.branch_id == branch_id))  # noqa: E712
    if lock:
        q = q.with_for_update(of=RestaurantTable)
    rows = q.order_by(RestaurantTable.id).all()
    if len(rows) != len(ids):
        raise HTTPException(status_code=400, detail="Stol topilmadi yoki boshqa filialga tegishli")
    return rows


def _blocking(q):
    from sqlalchemy import and_, or_
    return q.filter(or_(Reservation.status == "booked",
                        and_(Reservation.status == "arrived", Reservation.closed_at.is_(None))))


def conflicts(db: Session, company_id: int, branch_id: int, table_ids, start: datetime, end: datetime,
              exclude_id: Optional[int] = None) -> list:
    q = db.query(Reservation).filter(Reservation.company_id == company_id, Reservation.branch_id == branch_id,
                                     Reservation.starts_at < end, Reservation.ends_at > start)
    q = _blocking(q)
    if exclude_id:
        q = q.filter(Reservation.id != exclude_id)
    want = set(int(x) for x in table_ids)
    return [r for r in q.all() if want & set(int(x) for x in (r.table_ids or []))]


def _check_free(db: Session, company_id: int, branch_id: int, tables: list, start: datetime, end: datetime,
                exclude_id: Optional[int] = None) -> None:
    hits = conflicts(db, company_id, branch_id, [t.id for t in tables], start, end, exclude_id)
    if hits:
        names = {t.id: t.name for t in tables}
        raise HTTPException(status_code=409, detail={
            "code": "TABLE_BUSY",
            "message": "Bu vaqtda stol band: " + ", ".join(
                f"{', '.join(names.get(int(t), str(t)) for t in h.table_ids if int(t) in names)} ({h.name})"
                for h in hits),
            "conflicts": [{"id": h.id, "name": h.name, "starts_at": iso(h.starts_at), "ends_at": iso(h.ends_at),
                           "table_ids": h.table_ids} for h in hits],
        })


# ── yaratish va tahrirlash ─────────────────────────────────────────

def _fields(data: dict, settings: dict, current: Optional[Reservation] = None) -> dict:
    out = {}
    if current is None or "starts_at" in data:
        if not data.get("starts_at"):
            raise HTTPException(status_code=400, detail="Bron vaqti kiritilmagan")
        out["starts_at"] = parse_dt(data["starts_at"])
    if current is None or data.get("duration_min") is not None:
        dur = data.get("duration_min") or settings.get("reservation_duration_min") or 120
        try:
            dur = int(dur)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Davomiylik noto'g'ri")
        if not 15 <= dur <= 720:
            raise HTTPException(status_code=400, detail="Davomiylik 15 daqiqadan 12 soatgacha")
        out["duration_min"] = dur
    if current is None or data.get("guests") is not None:
        try:
            g = int(data.get("guests") or 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Mehmonlar soni noto'g'ri")
        if not 1 <= g <= 500:
            raise HTTPException(status_code=400, detail="Mehmonlar soni 1 dan 500 gacha")
        out["guests"] = g
    if current is None or "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Mijoz ismi kiritilmagan")
        out["name"] = name[:120]
    if current is None or "phone" in data:
        phone = (data.get("phone") or "").strip()[:30] or None
        if phone and len(_digits(phone)) < 7:
            raise HTTPException(status_code=400, detail="Telefon raqami noto'g'ri")
        out["phone"] = phone
    if current is None or "note" in data:
        out["note"] = (data.get("note") or "").strip()[:500] or None
    return out


def create(db: Session, user: User, settings: dict, branch_id: int, data: dict) -> Reservation:
    f = _fields(data, settings)
    if f["starts_at"] < _utcnow() - timedelta(minutes=15):
        raise HTTPException(status_code=400, detail="Bron vaqti o'tib ketgan")
    tables = _tables(db, user.company_id, branch_id, data.get("table_ids"), lock=True)
    end = f["starts_at"] + timedelta(minutes=f["duration_min"])
    _check_free(db, user.company_id, branch_id, tables, f["starts_at"], end)
    customer_id = data.get("customer_id")
    if customer_id:
        from app.models.customer import Customer
        if not db.query(Customer.id).filter(Customer.id == customer_id, Customer.company_id == user.company_id).first():
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    else:
        c = find_customer(db, user.company_id, f["phone"])
        customer_id = c.id if c else None
    now = _utcnow()
    r = Reservation(company_id=user.company_id, branch_id=branch_id, table_ids=[t.id for t in tables],
                    ends_at=end, customer_id=customer_id, status="booked", created_by=user.id,
                    created_at=now, updated_at=now, deposit_amount=ZERO, deposit_applied=ZERO, **f)
    db.add(r)
    db.flush()
    return r


def update(db: Session, user: User, settings: dict, r: Reservation, data: dict) -> Reservation:
    if r.status != "booked":
        raise HTTPException(status_code=409, detail="Faqat kutilayotgan bronni o'zgartirish mumkin")
    f = _fields(data, settings, current=r)
    start = f.get("starts_at", r.starts_at)
    dur = f.get("duration_min", r.duration_min)
    end = start + timedelta(minutes=dur)
    tables = _tables(db, r.company_id, r.branch_id,
                     data.get("table_ids") if data.get("table_ids") is not None else r.table_ids, lock=True)
    _check_free(db, r.company_id, r.branch_id, tables, start, end, exclude_id=r.id)
    for k, v in f.items():
        setattr(r, k, v)
    r.table_ids = [t.id for t in tables]
    r.ends_at = end
    if "phone" in f and not data.get("customer_id"):
        c = find_customer(db, r.company_id, r.phone)
        r.customer_id = c.id if c else None
    r.reminded_at = None if "starts_at" in f else r.reminded_at
    r.updated_at = _utcnow()
    db.flush()
    return r


def get(db: Session, company_id: int, reservation_id: int, lock: bool = False) -> Reservation:
    q = db.query(Reservation).filter(Reservation.id == reservation_id, Reservation.company_id == company_id)
    if lock:
        q = q.with_for_update()
    r = q.first()
    if r is None:
        raise HTTPException(status_code=404, detail="Bron topilmadi")
    return r


# ── depozit (kassa) ────────────────────────────────────────────────

def _post_money(db: Session, user: User, r: Reservation, direction: str, amount: Decimal, ptype: str,
                wallet_id: Optional[int], ref_type: str, desc: str) -> Optional[int]:
    from app.models.moliya import KassaMovement, Transaction, Wallet
    from app.services.sale_cash import _open_session_id
    from app.services.sale_helpers import resolve_cashier_wallet_id
    wallet = None
    if wallet_id:
        wallet = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == r.company_id,
                                         Wallet.is_active == True).with_for_update().first()  # noqa: E712
    if wallet is None:
        wid = resolve_cashier_wallet_id(db, user)
        wallet = db.query(Wallet).filter(Wallet.id == wid, Wallet.company_id == r.company_id).with_for_update().first() \
            if wid else None
    if wallet is None:
        raise HTTPException(status_code=409, detail="Kassa topilmadi: xodimga kassa biriktiring")
    db.add(Transaction(branch_id=r.branch_id, company_id=r.company_id, wallet_id=wallet.id,
                       type="income" if direction == "in" else "expense", amount=amount, payment_type=ptype,
                       currency_code="UZS", reference_type=ref_type, reference_id=r.id, description=desc))
    db.add(KassaMovement(wallet_id=wallet.id, company_id=r.company_id, session_id=_open_session_id(db, wallet.id),
                         direction=direction, payment_type=ptype, amount=amount, currency="UZS",
                         reference_type=ref_type, reference_id=r.id, description=desc, created_by=user.id))
    bal = Decimal(str(wallet.balance or 0))
    wallet.balance = bal + amount if direction == "in" else bal - amount
    db.flush()
    return wallet.id


def take_deposit(db: Session, user: User, r: Reservation, amount, ptype: str) -> Reservation:
    if r.status != "booked":
        raise HTTPException(status_code=409, detail="Depozit faqat kutilayotgan bronga olinadi")
    if r.deposit_status is not None:
        raise HTTPException(status_code=409, detail="Bu bronga depozit allaqachon olingan")
    amt = _money(amount)
    if amt <= 0:
        raise HTTPException(status_code=400, detail="Depozit summasi musbat bo'lishi kerak")
    if amt > Decimal("1000000000"):
        raise HTTPException(status_code=400, detail="Depozit summasi juda katta")
    if ptype not in PAY_TYPES:
        raise HTTPException(status_code=400, detail="To'lov turi noto'g'ri")
    wid = _post_money(db, user, r, "in", amt, ptype, None, DEPOSIT_REF, f"Bron depoziti #{r.id}: {r.name}")
    r.deposit_amount, r.deposit_type, r.deposit_wallet_id = amt, ptype, wid
    r.deposit_status, r.deposit_applied = "held", ZERO
    r.updated_at = _utcnow()
    db.flush()
    return r


def held_amount(r: Reservation) -> Decimal:
    if r.deposit_status != "held":
        return ZERO
    return Decimal(str(r.deposit_amount or 0)) - Decimal(str(r.deposit_applied or 0))


def refund_deposit(db: Session, user: User, r: Reservation, amount: Optional[Decimal] = None,
                   desc: Optional[str] = None) -> Decimal:
    left = held_amount(r)
    amt = left if amount is None else min(_money(amount), left)
    if amt <= 0:
        return ZERO
    _post_money(db, user, r, "out", amt, r.deposit_type or "cash", r.deposit_wallet_id, REFUND_REF,
                desc or f"Bron depoziti qaytarildi #{r.id}: {r.name}")
    if amt >= left:
        r.deposit_status = "refunded" if (r.deposit_applied or 0) == 0 else "applied"
    r.updated_at = _utcnow()
    db.flush()
    return amt


# ── holatlar ───────────────────────────────────────────────────────

def cancel(db: Session, user: User, r: Reservation, reason: Optional[str], refund: bool) -> Decimal:
    if r.status != "booked":
        raise HTTPException(status_code=409, detail="Faqat kutilayotgan bronni bekor qilish mumkin")
    back = refund_deposit(db, user, r) if refund else ZERO
    if not refund and r.deposit_status == "held":
        r.deposit_status = "retained"
    r.status = "cancelled"
    r.cancel_reason = (reason or "").strip()[:200] or None
    r.closed_at = r.updated_at = _utcnow()
    db.flush()
    return back


def no_show(db: Session, user: User, r: Reservation) -> None:
    if r.status != "booked":
        raise HTTPException(status_code=409, detail="Faqat kutilayotgan bron uchun")
    if r.starts_at > _utcnow():
        raise HTTPException(status_code=409, detail="Bron vaqti hali kelmagan")
    r.status = "no_show"
    if r.deposit_status == "held":
        r.deposit_status = "retained"          # depozit qaytarilmaydi, kassada kirim bo'lib qoladi
    r.closed_at = r.updated_at = _utcnow()
    db.flush()


def arrive(db: Session, user: User, settings: dict, r: Reservation, open_check: bool = True):
    """Mehmon keldi: holat `arrived`, birinchi stolga chek ochiladi va bronga bog'lanadi."""
    from app.services.restaurant_orders import open_order
    if r.status != "booked":
        raise HTTPException(status_code=409, detail="Bron kutilayotgan holatda emas")
    order = None
    if open_check:
        order = open_order(db, user, settings, branch_id=r.branch_id, order_type="dine_in",
                           table_id=int(r.table_ids[0]), guests=min(int(r.guests or 1), 100),
                           comment=f"Bron: {r.name}" + (f", {r.note}" if r.note else ""), customer_id=r.customer_id)
        r.order_id = order.id
    r.status = "arrived"
    r.arrived_at = r.updated_at = _utcnow()
    db.flush()
    return order


# ── chek bilan bog'lash (to'lov) ───────────────────────────────────

def for_order(db: Session, order, lock: bool = True) -> list:
    """Chekka (yoki unga birlashtirilgan cheklarga) bog'langan bronlar."""
    from app.models.restaurant_order import RestaurantOrder
    ids = [order.id] + [x[0] for x in db.query(RestaurantOrder.id).filter(RestaurantOrder.merged_into_id == order.id)]
    q = db.query(Reservation).filter(Reservation.company_id == order.company_id, Reservation.order_id.in_(ids))
    if lock:
        q = q.with_for_update()
    return q.order_by(Reservation.id).all()


def order_deposit(db: Session, order) -> Decimal:
    return sum((held_amount(r) for r in for_order(db, order, lock=False)), ZERO)


def apply_to_order(db: Session, user: User, order, total: Decimal) -> tuple:
    """To'lovda: ushlab turilgan depozitlar chek summasigacha qo'llanadi. Qaytaradi: (to'lov qatorlari, qo'llangan,
    ortiqcha). Ortiqcha depozit shu yerda naqd qaytariladi (qaytim sifatida beriladi)."""
    rows, applied, excess = [], ZERO, ZERO
    left = total
    for r in for_order(db, order):
        h = held_amount(r)
        if h <= 0:
            continue
        use = min(h, left)
        if use > 0:
            rows.append({"type": "deposit", "amount": use, "reference": r.deposit_type or "cash", "terminal_id": None})
            r.deposit_applied = Decimal(str(r.deposit_applied or 0)) + use
            left -= use
            applied += use
        rest = h - use
        if rest > 0:
            excess += refund_deposit(db, user, r, rest, desc=f"Depozit qoldig'i qaytarildi #{r.id} (chek #{order.daily_no})")
        r.deposit_status = "applied" if Decimal(str(r.deposit_applied or 0)) > 0 else r.deposit_status
    db.flush()
    return rows, applied, excess


def close_for_order(db: Session, order) -> None:
    now = _utcnow()
    for r in for_order(db, order, lock=False):
        if r.closed_at is None:
            r.closed_at = r.updated_at = now


# ── ko'rinishlar ───────────────────────────────────────────────────

def table_names(db: Session, company_id: int, ids) -> dict:
    ids = {int(x) for x in ids}
    if not ids:
        return {}
    return {t.id: t.name for t in db.query(RestaurantTable).filter(RestaurantTable.company_id == company_id,
                                                                   RestaurantTable.id.in_(list(ids)))}


def out(r: Reservation, names: dict, user_names: Optional[dict] = None) -> dict:
    return {
        "id": r.id, "branch_id": r.branch_id, "table_ids": r.table_ids,
        "table_names": [names.get(int(t), str(t)) for t in r.table_ids or []],
        "starts_at": iso(r.starts_at), "ends_at": iso(r.ends_at), "duration_min": r.duration_min,
        "guests": r.guests, "customer_id": r.customer_id, "name": r.name, "phone": r.phone, "note": r.note,
        "status": r.status, "deposit_amount": float(r.deposit_amount or 0), "deposit_type": r.deposit_type,
        "deposit_status": r.deposit_status, "deposit_applied": float(r.deposit_applied or 0),
        "deposit_held": float(held_amount(r)), "order_id": r.order_id, "cancel_reason": r.cancel_reason,
        "reminded_at": iso(r.reminded_at), "remind_channel": r.remind_channel,
        "arrived_at": iso(r.arrived_at), "closed_at": iso(r.closed_at),
        "created_by_name": (user_names or {}).get(r.created_by), "created_at": iso(r.created_at),
    }


def list_range(db: Session, company_id: int, branch_id: int, start: datetime, end: datetime,
               statuses=None) -> list:
    q = db.query(Reservation).filter(Reservation.company_id == company_id, Reservation.branch_id == branch_id,
                                     Reservation.starts_at < end, Reservation.ends_at > start)
    if statuses:
        q = q.filter(Reservation.status.in_(list(statuses)))
    return q.order_by(Reservation.starts_at, Reservation.id).all()


def floor_info(db: Session, company_id: int, branch_id: int, settings: dict, now: Optional[datetime] = None) -> dict:
    """Zal sxemasi uchun: {table_id: {reservation, reserved}} — keyingi 12 soatdagi eng yaqin kutilayotgan bron;
    `reserved` = bron vaqtidan `reservation_hold_min` oldin va davomida."""
    now = now or _utcnow()
    hold = timedelta(minutes=int(settings.get("reservation_hold_min", 60) or 0))
    rows = (db.query(Reservation).filter(Reservation.company_id == company_id, Reservation.branch_id == branch_id,
                                         Reservation.status == "booked", Reservation.ends_at > now,
                                         Reservation.starts_at < now + timedelta(hours=12))
            .order_by(Reservation.starts_at).all())
    res = {}
    for r in rows:
        for tid in r.table_ids or []:
            tid = int(tid)
            if tid in res:
                continue
            res[tid] = {
                "reserved": r.starts_at - hold <= now,
                "reservation": {"id": r.id, "name": r.name, "phone": r.phone, "guests": r.guests,
                                "starts_at": iso(r.starts_at), "ends_at": iso(r.ends_at),
                                "deposit_held": float(held_amount(r)), "note": r.note},
            }
    return res


# ── eslatmalar ─────────────────────────────────────────────────────

def reminder_text(r: Reservation, company_name: str, branch) -> str:
    local = r.starts_at.replace(tzinfo=timezone.utc).astimezone(_local_tz())
    txt = (f"Hurmatli {r.name}, {company_name} restoranida {local.strftime('%d.%m.%Y')} soat "
           f"{local.strftime('%H:%M')} ga {r.guests} kishilik stol band qilingan.")
    if branch is not None:
        txt += f" Manzil: {branch.name}."
        if getattr(branch, "phone", None):
            txt += f" Tel: {branch.phone}."
    return txt


def due_reminders(db: Session, now: Optional[datetime] = None) -> list:
    """Eslatma vaqti kelgan bronlar (hali eslatilmagan, boshlanishiga 15 daqiqadan ko'p qolgan)."""
    from app.models.company import Company
    from app.services.restaurant import restaurant_settings_of
    now = now or _utcnow()
    rows = (db.query(Reservation).filter(Reservation.status == "booked", Reservation.reminded_at.is_(None),
                                         Reservation.starts_at > now + timedelta(minutes=15),
                                         Reservation.starts_at <= now + timedelta(hours=48)).all())
    hours_by_company = {}
    out_rows = []
    for r in rows:
        if r.company_id not in hours_by_company:
            st = restaurant_settings_of(db.get(Company, r.company_id))
            hours_by_company[r.company_id] = int(st.get("reservation_remind_hours", 2) or 0)
        h = hours_by_company[r.company_id]
        if h > 0 and r.starts_at <= now + timedelta(hours=h):
            out_rows.append(r)
    return out_rows


def claim_reminder(db: Session, r: Reservation, now: datetime) -> bool:
    n = (db.query(Reservation).filter(Reservation.id == r.id, Reservation.reminded_at.is_(None))
         .update({Reservation.reminded_at: now}, synchronize_session=False))
    db.commit()
    return n == 1


async def send_reminders(now: Optional[datetime] = None) -> int:
    """Rejalashtiruvchi har daqiqada chaqiradi. Har bron bir marta (atomar egallash) eslatiladi."""
    from app.database import SessionLocal
    from app.models.branch import Branch
    from app.models.company import Company
    from app.models.customer import Customer
    from app.models.sms_log import SMSLog
    from app.services.restaurant import restaurant_settings_of
    now = now or _utcnow()
    db = SessionLocal()
    sent = 0
    try:
        for r in due_reminders(db, now):
            if not claim_reminder(db, r, now):
                continue
            company = db.get(Company, r.company_id)
            if company is None:
                continue
            text = reminder_text(r, company.name, db.get(Branch, r.branch_id))
            channel = None
            cust = db.get(Customer, r.customer_id) if r.customer_id else None
            if cust is not None and cust.tg_chat_id and company.tg_bot_token:
                from app.services.scheduler import send_tg_msg_async
                if await send_tg_msg_async(company.tg_bot_token, cust.tg_chat_id, text):
                    channel = "telegram"
            if channel is None and r.phone and restaurant_settings_of(company).get("reservation_sms_reminder"):
                from app.services.eskiz_service import eskiz_service
                res = await eskiz_service.send_sms(r.phone, text)
                db.add(SMSLog(company_id=r.company_id, phone=r.phone, message=text,
                              status="sent" if res.get("success") else "failed", eskiz_id=res.get("eskiz_id"),
                              sms_type="reservation", error=res.get("error")))
                if res.get("success"):
                    channel = "sms"
            db.query(Reservation).filter(Reservation.id == r.id).update(
                {Reservation.remind_channel: channel or "none"}, synchronize_session=False)
            db.commit()
            sent += 1 if channel else 0
    finally:
        db.close()
    return sent
