"""Hisobotlar uchun umumiy yordamchilar: vaqt oralig'i, sotuv/qaytarish
filtrlari, filial va valyuta ifodalari.

Ma'lumot saqlash qoidalari (barcha hisobotlar shunga tayanadi):
- Sale.total_amount, Sale.discount_amount — asosiy valyutada (UZS).
  Sotuv valyutasidagi qiymat = total_amount / Sale.exchange_rate.
- SaleItem.subtotal / unit_price / discount — mahsulotning o'z valyutasida
  (SaleItem.currency_code); UZS qiymati = subtotal * SaleItem.exchange_rate.
- SaleItem.cost_price — UZS (FIFO partiya tannarxi).
- Sotuv hujjati raqami "S...", qaytarish hujjati raqami "R..." bilan boshlanadi.
  Qaytarilgan asl sotuv "partial_refund"/"refunded" statusini oladi, lekin u
  haqiqiy sotuv bo'lib qoladi — qaytarilgan summa "R" hujjatida alohida turadi.
  Shuning uchun asl sotuv + (−qaytarish hujjati) = sof natija.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, case, func, not_, or_
from sqlalchemy.orm import Session

from app.models.sale import Sale, SaleItem, SaleStatus

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Tashkent")
except Exception:  # tzdata topilmasa — Toshkentda yozgi vaqt yo'q, UTC+5
    LOCAL_TZ = timezone(timedelta(hours=5))


# ─── Vaqt oralig'i ───────────────────────────────────────────────────────────
# Chegaralar Toshkent vaqti bilan tz-aware beriladi. Postgres ularni saqlangan
# vaqt bilan sessiya zonasi orqali solishtiradi, shuning uchun kun 00:00 da
# boshlanadi (avval UTC yarim tuni, ya'ni Toshkent 05:00 edi).

def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def local_day_start(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=LOCAL_TZ)


def _today_range():
    """Bugungi kun (Toshkent vaqti) boshlanishi va tugashi."""
    today = local_today()
    return local_day_start(today), local_day_start(today + timedelta(days=1))


def _date_range(date_from: Optional[date], date_to: Optional[date]):
    start = local_day_start(date_from) if date_from else datetime(2000, 1, 1, tzinfo=LOCAL_TZ)
    end = local_day_start(date_to + timedelta(days=1)) if date_to else datetime(2100, 1, 1, tzinfo=LOCAL_TZ)
    return start, end


# ─── Sotuv / qaytarish hujjatlari ────────────────────────────────────────────

SALE_DOC_STATUSES = (SaleStatus.completed, SaleStatus.partial_refund, SaleStatus.refunded)


def is_return_doc():
    """Qaytarish hujjati (R... raqamli Sale)."""
    return Sale.number.like("R%")


def sale_doc_filter():
    """Haqiqiy sotuvlar — keyinchalik qisman/to'liq qaytarilganlari ham."""
    return and_(not_(is_return_doc()), Sale.status.in_(SALE_DOC_STATUSES))


def return_doc_filter():
    return and_(is_return_doc(), Sale.status == SaleStatus.refunded)


def sale_or_return_filter():
    return or_(sale_doc_filter(), return_doc_filter())


def doc_sign():
    """Sotuv +1, qaytarish hujjati −1."""
    return case((is_return_doc(), -1), else_=1)


# ─── Valyuta ifodalari ───────────────────────────────────────────────────────

def sale_rate():
    return func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)


def item_rate():
    return func.coalesce(func.nullif(SaleItem.exchange_rate, 0), 1)


def item_revenue_uzs():
    """Sotuv qatorining UZS dagi tushumi (qator chegirmasi ayirilgan)."""
    return SaleItem.subtotal * item_rate()


def item_cost_uzs():
    return SaleItem.cost_price * SaleItem.quantity


def currency_code_map(db: Session, company_id: int) -> dict:
    """{currency_id: code} — Sale.currency_id ni kodga aylantirish uchun."""
    from app.models.currency import Currency
    rows = (
        db.query(Currency.id, Currency.code)
        .filter(or_(Currency.company_id == company_id, Currency.company_id.is_(None)))
        .all()
    )
    return {r.id: (r.code or "UZS").upper() for r in rows}


def currency_rate_map(db: Session, company_id: int) -> dict:
    """{code: joriy kurs} — qarzlarni UZS ekvivalentida saralash uchun."""
    from app.models.currency import Currency
    rows = (
        db.query(Currency.code, Currency.rate)
        .filter(or_(Currency.company_id == company_id, Currency.company_id.is_(None)))
        .all()
    )
    rates = {"UZS": 1.0}
    for code, rate in rows:
        if code and rate:
            rates.setdefault(code.upper(), float(rate))
    return rates


# ─── Davr xulosasi (Telegram/AI hisobotlari uchun) ───────────────────────────

def sales_summary(db: Session, company_id: int, start: datetime, end: Optional[datetime] = None) -> dict:
    """Davr bo'yicha sotuv xulosasi, hammasi UZS da.

    count/gross — sotuv hujjatlari (qisman/to'liq qaytarilganlari ham),
    returns — qaytarish hujjatlari, net = gross − returns.
    paid_* va paid_amount sotuv valyutasida saqlanadi, shuning uchun kursga ko'paytiriladi.
    """
    base = [Sale.company_id == company_id, Sale.created_at >= start]
    if end is not None:
        base.append(Sale.created_at < end)
    rate = sale_rate()
    outstanding = Sale.total_amount - Sale.paid_amount * rate
    sales = db.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.coalesce(func.sum(func.coalesce(Sale.paid_cash, 0) * rate), 0),
        func.coalesce(func.sum(func.coalesce(Sale.paid_card, 0) * rate), 0),
        func.coalesce(func.sum(Sale.discount_amount), 0),
        func.coalesce(func.sum(case((outstanding > 0.01, outstanding), else_=0)), 0),
    ).filter(*base, sale_doc_filter()).one()
    returns = db.query(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.total_amount), 0),
    ).filter(*base, return_doc_filter()).one()

    gross = float(sales[1] or 0)
    returns_total = float(returns[1] or 0)
    return {
        "count": int(sales[0] or 0),
        "gross": gross,
        "cash": float(sales[2] or 0),
        "card": float(sales[3] or 0),
        "discount": float(sales[4] or 0),
        "debt": float(sales[5] or 0),
        "returns_count": int(returns[0] or 0),
        "returns": returns_total,
        "net": gross - returns_total,
    }


def day_sales_summary(db: Session, company_id: int, day: date) -> dict:
    start, end = _date_range(day, day)
    return sales_summary(db, company_id, start, end)


# ─── Filial ──────────────────────────────────────────────────────────────────

def branch_warehouse_ids(db: Session, company_id: int, branch_id: Optional[int]) -> Optional[list]:
    """Filial omborlari ID lari. branch_id berilmasa None (filtr qo'llanmaydi)."""
    if not branch_id:
        return None
    from app.models.warehouse import Warehouse
    rows = (
        db.query(Warehouse.id)
        .filter(Warehouse.branch_id == branch_id, Warehouse.company_id == company_id)
        .all()
    )
    return [r[0] for r in rows]


# ─── Qarz balanslari ─────────────────────────────────────────────────────────

def normalize_balances(balances, debt_balance, debt_currency) -> dict:
    """Mijoz/ta'minotchi qarzini valyuta bo'yicha dict ga keltiradi.

    Asosiy manba — debt_balances JSON (Mijozlar va Moliya sahifalari ham shuni
    ishlatadi); u bo'sh bo'lsa eski debt_balance/debt_currency olinadi.
    """
    result: dict = {}
    for code, amt in dict(balances or {}).items():
        try:
            value = float(amt or 0)
        except (TypeError, ValueError):
            continue
        key = str(code).strip().upper() or "UZS"
        result[key] = result.get(key, 0.0) + value
    if not result and float(debt_balance or 0) > 0:
        key = (debt_currency or "UZS").strip().upper() or "UZS"
        result = {key: float(debt_balance)}
    return result


def load_debtors(db: Session, model, company_id: int) -> list:
    """Qarzdor mijoz/ta'minotchilar: [(obyekt, {valyuta: musbat qarz})]."""
    from sqlalchemy import String, cast

    rows = (
        db.query(model)
        .filter(
            model.company_id == company_id,
            or_(
                model.debt_balance > 0,
                cast(model.debt_balances, String).notin_(["{}", "null"]),
            ),
        )
        .all()
    )
    result = []
    for obj in rows:
        balances = normalize_balances(obj.debt_balances, obj.debt_balance, getattr(obj, "debt_currency", None))
        positive = {code: round(amt, 2) for code, amt in balances.items() if amt > 0.009}
        if positive:
            result.append((obj, positive))
    return result
