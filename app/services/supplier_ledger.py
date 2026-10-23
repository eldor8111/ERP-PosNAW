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
    """Kompaniyaning valyuta kursi (UZS = 1). Boshqa kompaniya kursi olinmaydi.
    T2.7: yagona mantiq `currency_service.get_rate` da (shu yerda alias)."""
    from app.services.currency_service import get_rate
    return get_rate(db, company_id, code)


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
    # Yagona yordamchiga yo'naltirildi (korxona bo'yicha tekshiruv + qator qulfi).
    # Avvalgi xatti-harakat saqlanadi: nofaol kassa ham qabul qilinadi.
    from app.services.wallet_access import get_company_wallet
    return get_company_wallet(db, wallet_id, company_id, for_update=True, require_active=False)


def _warehouse_branch_id(db: Session, user, warehouse_id: Optional[int]) -> Optional[int]:
    """Ombor filiali — faqat `user.company_id` doirasidagi ombor va filial (begona korxona e'tiborga olinmaydi)."""
    if not warehouse_id:
        return None
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse
    row = (
        db.query(Warehouse.branch_id)
        .join(Branch, Branch.id == Warehouse.branch_id)
        .filter(
            Warehouse.id == warehouse_id,
            Warehouse.company_id == user.company_id,
            Branch.company_id == user.company_id,
            Branch.is_active == True,  # noqa: E712  (T1.12: yopilgan filialga yozilmaydi)
        )
        .first()
    )
    return row[0] if row else None


def resolve_branch(
    db: Session, user, warehouse_id: Optional[int] = None, *, prefer_warehouse: bool = False,
) -> Optional[int]:
    """Tranzaksiya filiali.

    Standart (`prefer_warehouse=False`): foydalanuvchi filiali (T1.2: joriy korxona bo'yicha) →
    ombor filiali → korxonaning asosiy filiali (T0.7/T1.4).
    `prefer_warehouse=True` (T1.16, xarid to'lovi va ta'minotchidan qaytim): ombor filiali
    (Warehouse.company_id == user.company_id) → foydalanuvchi filiali → korxonaning asosiy filiali,
    ya'ni xarajat tovar kirgan ombor filialiga yoziladi."""
    from fastapi import HTTPException
    from app.core.branch_context import effective_branch_id
    from app.services.branch_attribution import NO_ACTIVE_BRANCH, NO_BRANCH, resolve_money_branch_id
    # T2.2: yagona `resolve_money_branch_id` (ombor filiali -> foydalanuvchi filiali -> asosiy filial);
    # standart tartibda foydalanuvchi filiali omborni bosib o'tadi
    if not prefer_warehouse:
        eff = effective_branch_id(db, user)
        if eff:
            return eff
    try:
        return resolve_money_branch_id(db, user, warehouse_id=warehouse_id)
    except HTTPException as exc:
        if exc.status_code == 400 and exc.detail in (NO_BRANCH, NO_ACTIVE_BRANCH):
            return None
        raise


def record_cash(
    db: Session, *, user, direction: str, amount, currency: str, payment_type: str,
    wallet_id: Optional[int], reference_type: str, reference_id: int, description: str,
    meta: Optional[dict] = None, warehouse_id: Optional[int] = None, created_at: Optional[datetime] = None,
    prefer_warehouse: bool = False,
):
    """Ta'minotchi bilan pul harakati: Transaction + KassaMovement (+ UZS bo'lsa hamyon balansi).

    direction: "out" (biz to'ladik) yoki "in" (ta'minotchi pul qaytardi).
    """
    from app.core.branch_context import effective_branch_id
    from app.models.moliya import Transaction, KassaMovement, KassaSession
    from app.services.branch_helpers import fallback_active_branch_id_or_400

    amount = _d(amount)
    code = (currency or "UZS").strip().upper() or "UZS"
    ptype = payment_type or "cash"
    wallet = _company_wallet(db, wallet_id, user.company_id)

    tx = Transaction(
        # T1.2: joriy filial korxona bo'yicha; topilmasa T0.7 markaziy aniqlash (400 fallback).
        # T1.16: prefer_warehouse=True bo'lsa xarajat avval ombor filialiga yoziladi
        branch_id=(
            (_warehouse_branch_id(db, user, warehouse_id) if prefer_warehouse else None)
            or effective_branch_id(db, user)
            or fallback_active_branch_id_or_400(db, user, warehouse_id=warehouse_id)
        ),
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


# ─── Hisobot: kreditorlik filial kesimida (T2.6) ─────────────────────────────

def debt_by_branch(db: Session, company_id: int, branch_id: Optional[int] = None, branch_ids=None) -> dict:
    """Ta'minotchi qarzi (kreditorlik) filial kesimida: `PurchaseOrder.supplier_debt` (>0) xarid OMBORI
    filiali bo'yicha jamlanadi (`Warehouse.branch_id`). Jurnal yuritilmaydi — qarz hamon korxona darajasida.

    Supplier darajasidagi umumiy to'lovlar xaridlarga taqsimlanmagani uchun `unallocated_payments` =
    `Supplier.debt_balances` jami - `sum(PO.supplier_debt)` (valyuta bo'yicha, ishorali: manfiy — xaridga
    bog'lanmagan to'lov) ham qaytadi, shunda jami haqiqiy balans bilan mos tushadi.

    `branch_id`: aniq filial; `-1` — filialsiz ombor; `branch_ids` — ruxsat etilgan filiallar to'plami.
    Qaytaradi: {"by_branch", "unassigned", "suppliers": [{supplier, branch_id, debts, debt_uzs}],
    "unallocated_payments", "unallocated_payments_uzs"}.
    """
    from collections import defaultdict
    from sqlalchemy import func
    from app.models.branch import Branch
    from app.models.purchase_order import POStatus, PurchaseOrder
    from app.models.supplier import Supplier
    from app.models.warehouse import Warehouse
    from app.services.currency_service import rate_map, to_uzs

    rates = rate_map(db, company_id)
    cur_expr = func.coalesce(PurchaseOrder.supplier_debt_currency, PurchaseOrder.currency, "UZS")
    po_rows = (
        db.query(PurchaseOrder.supplier_id, Warehouse.branch_id, cur_expr, func.sum(PurchaseOrder.supplier_debt))
        .join(Warehouse, Warehouse.id == PurchaseOrder.warehouse_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(
            PurchaseOrder.company_id == company_id, Supplier.company_id == company_id,
            Supplier.is_active == True,  # noqa: E712
            PurchaseOrder.supplier_debt > 0, PurchaseOrder.status != POStatus.cancelled,
        )
        .group_by(PurchaseOrder.supplier_id, Warehouse.branch_id, cur_expr)
        .all()
    )
    po_total: dict = defaultdict(lambda: ZERO)
    recs: dict = {}
    for sid, br, cur, total in po_rows:
        code = (str(cur or "UZS")).strip().upper() or "UZS"
        po_total[code] += _d(total)
        rec = recs.setdefault((sid, br), {"supplier_id": sid, "branch_id": br, "debts": {}})
        rec["debts"][code] = rec["debts"].get(code, ZERO) + _d(total)

    # Aralash valyutali xaridlar: asosiy valyutadan boshqa valyutalardagi musbat qarz hissalari
    extra_rows = (
        db.query(PurchaseOrder.supplier_id, Warehouse.branch_id, PurchaseOrder.supplier_debt_extra)
        .join(Warehouse, Warehouse.id == PurchaseOrder.warehouse_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(
            PurchaseOrder.company_id == company_id, Supplier.company_id == company_id,
            Supplier.is_active == True,  # noqa: E712
            PurchaseOrder.supplier_debt_extra.isnot(None), PurchaseOrder.status != POStatus.cancelled,
        )
        .all()
    )
    for sid, br, extra in extra_rows:
        for code, amt in dict(extra or {}).items():
            amt = _d(amt)
            if amt <= 0:
                continue
            code = (str(code)).strip().upper() or "UZS"
            po_total[code] += amt
            rec = recs.setdefault((sid, br), {"supplier_id": sid, "branch_id": br, "debts": {}})
            rec["debts"][code] = rec["debts"].get(code, ZERO) + amt

    # Umumiy balans (faol ta'minotchilar) va xaridlarga bog'lanmagan qism
    bal_total: dict = defaultdict(lambda: ZERO)
    suppliers = {s.id: s for s in db.query(Supplier).filter(Supplier.company_id == company_id, Supplier.is_active == True).all()}  # noqa: E712
    for s in suppliers.values():
        for code, amt in balances(s).items():
            bal_total[code] += amt
    unallocated = {c: bal_total.get(c, ZERO) - po_total.get(c, ZERO) for c in set(bal_total) | set(po_total)}
    unallocated = {c: v for c, v in unallocated.items() if abs(v) >= EPS}

    def _keep(b) -> bool:
        if branch_id == -1:
            return b is None
        if branch_id:
            return b == branch_id
        if branch_ids is not None:
            return b in branch_ids
        return True

    rows = []
    for rec in recs.values():
        if not _keep(rec["branch_id"]) or rec["supplier_id"] not in suppliers:
            continue
        rec["supplier"] = suppliers[rec["supplier_id"]]
        rec["debt_uzs"] = float(round(sum((to_uzs(v, c, rates) for c, v in rec["debts"].items()), ZERO), 2))
        rec["debts"] = {c: float(round(v, 2)) for c, v in rec["debts"].items()}
        rows.append(rec)
    rows.sort(key=lambda r: r["debt_uzs"], reverse=True)

    names = {b.id: b.name for b in db.query(Branch.id, Branch.name).filter(Branch.company_id == company_id).all()}

    def _agg(rs, b, name) -> dict:
        total: dict = {}
        uzs = ZERO
        for r in rs:
            for code, amt in r["debts"].items():
                total[code] = total.get(code, ZERO) + _d(amt)
                uzs += to_uzs(amt, code, rates)
        return {"branch_id": b, "branch_name": name,
                "total_debt": {c: float(round(v, 2)) for c, v in total.items()},
                "debt_uzs": float(round(uzs, 2)), "supplier_count": len({r["supplier_id"] for r in rs})}

    grouped: dict = defaultdict(list)
    for r in rows:
        grouped[r["branch_id"]].append(r)
    by_branch = [_agg(rs, b, names.get(b) or f"Filial #{b}") for b, rs in grouped.items() if b is not None]
    by_branch.sort(key=lambda x: x["debt_uzs"], reverse=True)
    return {
        "by_branch": by_branch,
        "unassigned": _agg(grouped.get(None, []), None, None),
        "suppliers": rows,
        "unallocated_payments": {c: float(round(v, 2)) for c, v in unallocated.items()},
        "unallocated_payments_uzs": float(round(sum((to_uzs(v, c, rates) for c, v in unallocated.items()), ZERO), 2)),
    }
