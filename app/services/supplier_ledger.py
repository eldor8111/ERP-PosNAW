"""Ta'minotchi qarzi (kreditorlik) va ta'minotchi bilan pul harakatlari — yagona joy.

Qoidalar:
- Qarzning yagona manbai: Supplier.debt_balances {valyuta: summa}.
  Musbat — biz qarzdormiz, manfiy — avans (oldindan to'langan / ta'minotchi bizga qarzdor).
- Supplier.debt_balance — shu balanslarning joriy kurs bo'yicha UZS ekvivalenti (hosila maydon,
  saralash va eski hisobotlar uchun). Uni to'g'ridan-to'g'ri o'zgartirilmaydi.
- Qarz tovar QABUL QILINGANDA paydo bo'ladi, to'lov uni kamaytiradi.
- Har bir xaridning balansga qo'shgan hissasi PurchaseOrder.supplier_debt da saqlanadi —
  o'chirish/tahrirlash aynan o'sha summani qaytaradi.
- Kassa: wallet.balance faqat UZS da yuritiladi (sotuvdagi kabi); valyuta KassaMovement da.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

ZERO = Decimal("0")
EPS = Decimal("0.005")


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def currency_rate(db: Session, company_id: Optional[int], code: Optional[str]) -> Decimal:
    """Kompaniyaning valyuta kursi (UZS = 1). Boshqa kompaniya kursi olinmaydi."""
    code = (code or "UZS").strip().upper()
    if code == "UZS":
        return Decimal("1")
    from app.models.currency import Currency
    q = db.query(Currency).filter(Currency.code == code)
    q = q.filter(or_(Currency.company_id == company_id, Currency.company_id.is_(None)))
    obj = q.order_by(Currency.company_id.is_(None)).first()  # avval kompaniyaniki
    rate = _d(obj.rate) if obj and obj.rate else Decimal("1")
    return rate if rate > 0 else Decimal("1")


def balances(supplier) -> dict:
    """Valyuta bo'yicha balanslar (eski debt_balance/debt_currency dan ko'chirish bilan)."""
    result = {}
    for code, amt in dict(supplier.debt_balances or {}).items():
        key = str(code).strip().upper() or "UZS"
        result[key] = _d(result.get(key, 0)) + _d(amt)
    if not result and _d(supplier.debt_balance) != 0:
        key = (getattr(supplier, "debt_currency", None) or "UZS").strip().upper() or "UZS"
        result[key] = _d(supplier.debt_balance)
    return {k: _d(v) for k, v in result.items()}


def _save(db: Session, supplier, bal: dict) -> None:
    cleaned = {}
    for code, amt in bal.items():
        amt = _d(amt)
        if abs(amt) >= EPS:
            cleaned[code] = float(round(amt, 4))
    supplier.debt_balances = cleaned
    flag_modified(supplier, "debt_balances")
    total = sum((_d(v) * currency_rate(db, supplier.company_id, c) for c, v in cleaned.items()), ZERO)
    supplier.debt_balance = round(total, 2)
    supplier.debt_currency = "UZS"


def add(db: Session, supplier, currency: str, amount) -> None:
    """Qarzga qo'shish (manfiy — kamaytirish). amount — shu valyutada."""
    amount = _d(amount)
    if abs(amount) < Decimal("0.00005"):
        return
    code = (currency or "UZS").strip().upper() or "UZS"
    bal = balances(supplier)
    bal[code] = bal.get(code, ZERO) + amount
    _save(db, supplier, bal)


def apply_payment(db: Session, supplier, amount, currency: str) -> dict:
    """To'lovni qarzga taqsimlaydi va {valyuta: kamaygan summa} qaytaradi.

    Avval shu valyutadagi qarz, keyin boshqa valyutalardagi qarz (kurs bo'yicha) yopiladi;
    ortib qolgani to'lov valyutasida avans (manfiy balans) bo'lib qoladi — yo'qolmaydi.
    """
    amount = _d(amount)
    code = (currency or "UZS").strip().upper() or "UZS"
    pay_rate = currency_rate(db, supplier.company_id, code)
    bal = balances(supplier)
    alloc: dict = {}

    remaining = amount
    own = bal.get(code, ZERO)
    if own > 0:
        take = min(own, remaining)
        bal[code] = own - take
        alloc[code] = alloc.get(code, ZERO) + take
        remaining -= take

    if remaining > EPS:
        remaining_uzs = remaining * pay_rate
        for other, debt in list(bal.items()):
            if other == code or debt <= 0 or remaining_uzs <= EPS:
                continue
            rate = currency_rate(db, supplier.company_id, other)
            cover_uzs = min(remaining_uzs, debt * rate)
            cover = cover_uzs / rate
            bal[other] = debt - cover
            alloc[other] = alloc.get(other, ZERO) + cover
            remaining_uzs -= cover_uzs
        remaining = remaining_uzs / pay_rate

    if remaining > EPS:  # ortiqcha to'lov — avans
        bal[code] = bal.get(code, ZERO) - remaining
        alloc[code] = alloc.get(code, ZERO) + remaining

    _save(db, supplier, bal)
    return {c: str(round(v, 4)) for c, v in alloc.items()}


def reverse_allocation(db: Session, supplier, allocation: dict) -> None:
    """apply_payment natijasini aynan qaytaradi (to'lov o'chirilganda)."""
    bal = balances(supplier)
    for code, amt in (allocation or {}).items():
        code = str(code).upper()
        bal[code] = bal.get(code, ZERO) + _d(amt)
    _save(db, supplier, bal)


# ─── Kassa ───────────────────────────────────────────────────────────────────

def _company_wallet(db: Session, wallet_id: Optional[int], company_id: int):
    if not wallet_id:
        return None
    from app.models.moliya import Wallet
    wallet = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == company_id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Kassa (hamyon) topilmadi")
    return wallet


def resolve_branch(db: Session, user, warehouse_id: Optional[int] = None) -> Optional[int]:
    """Tranzaksiya filiali: foydalanuvchi filiali → ombor filiali → kompaniyaning birinchi filiali."""
    if getattr(user, "branch_id", None):
        return user.branch_id
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse
    if warehouse_id:
        wh = db.query(Warehouse).filter(Warehouse.id == warehouse_id, Warehouse.company_id == user.company_id).first()
        if wh and wh.branch_id:
            return wh.branch_id
    br = db.query(Branch).filter(Branch.company_id == user.company_id).order_by(Branch.id).first()
    return br.id if br else None


def record_cash(
    db: Session, *, user, direction: str, amount, currency: str, payment_type: str,
    wallet_id: Optional[int], reference_type: str, reference_id: int, description: str,
    meta: Optional[dict] = None, warehouse_id: Optional[int] = None, created_at: Optional[datetime] = None,
):
    """Ta'minotchi bilan pul harakati: Transaction + KassaMovement (+ UZS bo'lsa hamyon balansi).

    direction: "out" (biz to'ladik) yoki "in" (ta'minotchi pul qaytardi).
    """
    from app.models.moliya import Transaction, KassaMovement, KassaSession

    amount = _d(amount)
    code = (currency or "UZS").strip().upper() or "UZS"
    ptype = payment_type or "cash"
    wallet = _company_wallet(db, wallet_id, user.company_id)

    tx = Transaction(
        branch_id=resolve_branch(db, user, warehouse_id),
        company_id=user.company_id,
        type="expense" if direction == "out" else "income",
        amount=amount,
        wallet_id=wallet.id if wallet else None,
        currency_code=code,
        payment_type=ptype,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
        user_id=user.id,
        meta=meta,
    )
    if created_at is not None:
        tx.created_at = created_at
    db.add(tx)

    if wallet:
        if code == "UZS":
            sign = Decimal("-1") if direction == "out" else Decimal("1")
            wallet.balance = _d(wallet.balance) + sign * amount
        if ptype not in ("debt", "cashback"):
            session = db.query(KassaSession).filter(KassaSession.wallet_id == wallet.id, KassaSession.status == "open").first()
            db.add(KassaMovement(
                wallet_id=wallet.id, company_id=user.company_id,
                session_id=session.id if session else None,
                direction=direction, payment_type=ptype, amount=amount, currency=code,
                reference_type=reference_type, reference_id=reference_id,
                description=description, created_by=user.id,
            ))
    db.flush()
    return tx


def find_kassa_movement(db: Session, tx):
    """Tranzaksiyaga mos kassa harakati: bir xil havola, hamyon va summa, vaqti eng yaqini."""
    from app.models.moliya import KassaMovement
    if not tx.reference_type or tx.reference_id is None:
        return None
    q = db.query(KassaMovement).filter(
        KassaMovement.reference_type == tx.reference_type,
        KassaMovement.reference_id == tx.reference_id,
    )
    if tx.wallet_id:
        q = q.filter(KassaMovement.wallet_id == tx.wallet_id)
    candidates = [m for m in q.all() if abs(_d(m.amount) - _d(tx.amount)) < Decimal("0.01")]
    if not candidates:
        return None
    if tx.created_at:
        candidates.sort(key=lambda m: abs(((m.created_at or tx.created_at) - tx.created_at).total_seconds()))
    return candidates[0]


def reverse_cash(db: Session, tx) -> None:
    """record_cash ni bekor qiladi: hamyon (UZS), kassa harakati va tranzaksiya."""
    from app.models.moliya import Wallet
    # Yangi yozuvlarda hamyon faqat UZS da o'zgargan; eski (meta siz) ta'minotchi yozuvlarida
    # hamyon valyutadan qat'i nazar summaga kamaytirilgan — bekor qilish ham shunday bo'ladi.
    legacy = tx.meta is None and tx.reference_type in ("purchase_order", "supplier_payment", "return_to_supplier")
    if tx.wallet_id and ((tx.currency_code or "UZS").upper() == "UZS" or legacy):
        wallet = db.get(Wallet, tx.wallet_id)
        if wallet:
            sign = Decimal("1") if tx.type == "expense" else Decimal("-1")
            wallet.balance = _d(wallet.balance) + sign * _d(tx.amount)
    mv = find_kassa_movement(db, tx)
    if mv:
        db.delete(mv)
    db.delete(tx)


# ─── Ta'minotchi qarzini to'lash ─────────────────────────────────────────────

def pay_supplier(db: Session, supplier, *, user, amount, currency: str = "UZS", payment_type: str = "cash",
                 wallet_id: Optional[int] = None, reason: Optional[str] = None):
    """Qarz to'lovi — Xaridlar va Moliya sahifalari uchun yagona mantiq."""
    from app.core.audit import log_action

    amount = _d(amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="To'lov miqdori musbat bo'lishi kerak")
    code = (currency or "UZS").strip().upper() or "UZS"
    before = {k: float(v) for k, v in balances(supplier).items()}
    allocation = apply_payment(db, supplier, amount, code)

    desc = (reason or "Ta'minotchi qarzi to'lovi").strip()
    desc = f"{desc}: {supplier.name}" + (f" ({amount} {code})" if code != "UZS" else "")
    tx = record_cash(
        db, user=user, direction="out", amount=amount, currency=code, payment_type=payment_type,
        wallet_id=wallet_id, reference_type="supplier_payment", reference_id=supplier.id,
        description=desc, meta={"allocation": allocation},
    )
    log_action(db, action="PAY_DEBT", entity_type="supplier", entity_id=supplier.id, user_id=user.id,
               old_values={"debt_balances": before},
               new_values={"amount": str(amount), "currency": code, "transaction_id": tx.id,
                           "debt_balances": supplier.debt_balances})
    return tx
