"""Valyuta kurslari — korxonaga bog'liq yagona joy (T2.7).

Qoidalar:
- Kurs har doim so'ralayotgan korxonaniki: avval `company_id = X` qatori, bo'lmasa global
  (`company_id IS NULL`) qatori. Boshqa korxona kursi hech qachon olinmaydi.
- UZS kursi har doim 1; kurs topilmasa yoki `rate <= 0` bo'lsa 1.
- `company_id = None` (super_admin) uchun faqat global qatorlar ko'riladi.
- `Wallet.balance` faqat UZS da yuritiladi; boshqa valyutadagi summa UZS ga `to_uzs` / `amount_uzs_sql`
  bilan o'tkazib jamlanadi.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

ONE = Decimal("1")


def norm_code(code: Optional[str]) -> str:
    """Valyuta kodini katta harfga keltiradi; bo'sh bo'lsa 'UZS'."""
    return (code or "UZS").strip().upper() or "UZS"


def _scope(company_id: Optional[int]):
    from app.models.currency import Currency
    if company_id is None:
        return Currency.company_id.is_(None)
    return or_(Currency.company_id == company_id, Currency.company_id.is_(None))


def get_rate(db: Session, company_id: Optional[int], code: Optional[str]) -> Decimal:
    """Korxonaning valyuta kursi (UZS = 1). Korxona qatori, keyin global (NULL) qator."""
    code = norm_code(code)
    if code == "UZS":
        return ONE
    from app.models.currency import Currency
    obj = (
        db.query(Currency)
        .filter(Currency.code == code, _scope(company_id))
        .order_by(Currency.company_id.is_(None), Currency.id)  # avval korxonaniki, so'ng eng eski qator
        .first()
    )
    rate = Decimal(str(obj.rate)) if obj is not None and obj.rate else ONE
    return rate if rate > 0 else ONE


def rate_map(db: Session, company_id: Optional[int]) -> dict:
    """{KOD: Decimal kurs} — korxona qatori global qatorni bosadi (deterministik). UZS=1 doim bor."""
    from app.models.currency import Currency
    rows = (
        db.query(Currency.code, Currency.rate, Currency.company_id)
        .filter(_scope(company_id))
        .order_by(Currency.company_id.isnot(None), Currency.id.desc())  # global avval, korxona oxirida (ustun)
        .all()
    )
    rates = {}
    for code, rate, _cid in rows:
        if not code or not rate or Decimal(str(rate)) <= 0:
            continue
        # tartib: global qatorlar avval, korxona qatorlari keyin (ustun); har guruhda eng eski id oxirida -> yutadi
        rates[code.strip().upper()] = Decimal(str(rate))
    rates["UZS"] = ONE
    return rates


def to_uzs(amount, code: Optional[str], rates: dict) -> Decimal:
    """Summani UZS ekvivalentiga o'tkazadi. `rates` — `rate_map` natijasi (kod topilmasa 1)."""
    code = norm_code(code)
    amt = Decimal(str(amount or 0))
    if code == "UZS":
        return amt
    rate = rates.get(code)
    rate = Decimal(str(rate)) if rate else ONE
    return amt * rate


def amount_uzs_sql(amount_col, currency_col, rates: dict):
    """SQLAlchemy ifodasi: `amount_col` ni `currency_col` kursi bo'yicha UZS ga o'tkazadi.

    NULL/'UZS'/kursi noma'lum valyuta -> summaning o'zi (kurs 1).
    """
    from sqlalchemy import func
    whens = []
    for code, rate in (rates or {}).items():
        code = str(code).strip().upper()
        if code == "UZS":
            continue
        r = Decimal(str(rate))
        if r > 0 and r != ONE:
            whens.append((func.upper(currency_col) == code, amount_col * float(r)))
    if not whens:
        return amount_col
    return case(*whens, else_=amount_col)


def require_active_currency(db: Session, company_id: Optional[int], code: Optional[str]) -> str:
    """Valyuta korxonada mavjud va faol ekanini tekshiradi; kodni qaytaradi. UZS har doim ruxsat.

    Noma'lum/nofaol valyuta -> 400.
    """
    code = norm_code(code)
    if code == "UZS":
        return code
    from app.models.currency import Currency
    obj = (
        db.query(Currency.id)
        .filter(Currency.code == code, _scope(company_id), Currency.is_active.isnot(False))
        .first()
    )
    if obj is None:
        raise HTTPException(status_code=400, detail=f"Noma'lum yoki nofaol valyuta: {code}")
    return code
