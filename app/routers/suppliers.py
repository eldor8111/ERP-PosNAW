import logging
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload  # type: ignore
from sqlalchemy.exc import SQLAlchemyError  # type: ignore

from app.core.audit import log_action  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.database import get_db  # type: ignore
from app.models.supplier import Supplier  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.schemas.supplier import SupplierCreate, SupplierDebtAdjust, SupplierOut, SupplierUpdate  # type: ignore
from app.services import supplier_ledger as ledger  # type: ignore
from app.utils.translit import name_search_filter  # type: ignore
from app.utils.import_errors import row_db_error  # type: ignore

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])
logger = logging.getLogger(__name__)

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)
# Qarzni qo'lda tuzatish — faqat rahbariyat va buxgalter
DEBT_ADJUST_ROLES = (UserRole.admin, UserRole.director, UserRole.accountant)

ZERO = Decimal("0")


class SupplierDebtPayment(BaseModel):
    amount: Decimal
    reason: str = "Qarz to'lovi"
    wallet_id: Optional[int] = None
    payment_type: Optional[str] = "cash"
    currency: Optional[str] = "UZS"


def _get_supplier(db: Session, supplier_id: int, user: User, active_only: bool = False) -> Supplier:
    q = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.company_id == user.company_id)
    if active_only:
        q = q.filter(Supplier.is_active == True)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    return supplier


def _company_rates(db: Session, company_id: int) -> dict:
    from app.models.currency import Currency as CurrencyModel
    rows = db.query(CurrencyModel).filter(
        CurrencyModel.company_id == company_id, CurrencyModel.is_active == True,
    ).all()
    rates = {c.code.upper(): float(c.rate) for c in rows if c.rate}
    rates["UZS"] = 1.0
    return rates


def _float_balances(supplier: Supplier) -> dict:
    return {k: float(round(v, 4)) for k, v in ledger.balances(supplier).items()}


@router.get("", response_model=List[SupplierOut])
def list_suppliers(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.is_active == True, Supplier.company_id == current_user.company_id)
    if search:
        q = q.filter(name_search_filter(Supplier.name, search))
    return q.order_by(Supplier.name).offset(skip).limit(limit).all()


@router.get("/summary")
def suppliers_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Barcha faol ta'minotchilar bo'yicha jami qarz va avans (ro'yxat limitidan qat'i nazar)."""
    suppliers = db.query(Supplier).filter(
        Supplier.is_active == True, Supplier.company_id == current_user.company_id,
    ).all()
    rates = _company_rates(db, current_user.company_id)
    debts, avans = defaultdict(float), defaultdict(float)
    debt_uzs = avans_uzs = 0.0
    debtors = 0
    for s in suppliers:
        has_debt = False
        for cur, amt in ledger.balances(s).items():
            amt = float(amt)
            rate = rates.get(cur, 1.0)
            if amt > 0:
                debts[cur] += amt
                debt_uzs += amt * rate
                has_debt = True
            elif amt < 0:
                avans[cur] += -amt
                avans_uzs += -amt * rate
        debtors += 1 if has_debt else 0
    return {
        "count": len(suppliers),
        "debtors_count": debtors,
        "debt_by_currency": {k: round(v, 2) for k, v in debts.items()},
        "avans_by_currency": {k: round(v, 2) for k, v in avans.items()},
        "debt_uzs": round(debt_uzs, 2),
        "avans_uzs": round(avans_uzs, 2),
        "rates": rates,
    }


@router.post("", response_model=SupplierOut)
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    payload = data.model_dump(exclude={"debt_balance", "debt_currency", "debt_balances"})
    supplier = Supplier(**payload, company_id=current_user.company_id,
                        debt_balance=ZERO, debt_currency="UZS", debt_balances={})
    db.add(supplier)
    db.flush()

    # Boshlang'ich qarz (ixtiyoriy) — valyutalar bo'yicha
    initial = defaultdict(lambda: ZERO)
    if data.debt_balances:
        for code, amt in data.debt_balances.items():
            try:
                initial[str(code).strip().upper() or "UZS"] += Decimal(str(amt or 0))
            except InvalidOperation:
                raise HTTPException(status_code=400, detail=f"Qarz summasi noto'g'ri: {amt}")
    elif data.debt_balance:
        initial[(data.debt_currency or "UZS").strip().upper() or "UZS"] += Decimal(str(data.debt_balance))
    for code, amt in initial.items():
        ledger.add(db, supplier, code, amt)

    log_action(db, action="CREATE", entity_type="supplier", entity_id=supplier.id, user_id=current_user.id,
               new_values={"name": supplier.name, "initial_debt": {k: str(v) for k, v in initial.items() if v}})
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    return _get_supplier(db, supplier_id, current_user)


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Rekvizitlarni tahrirlash. Qarz bu yerda o'zgarmaydi — /adjust-debt orqali."""
    supplier = _get_supplier(db, supplier_id, current_user)
    old, new = {}, {}
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "name" and not (value or "").strip():
            raise HTTPException(status_code=400, detail="Ta'minotchi nomi bo'sh bo'lishi mumkin emas")
        if field in ("name", "payment_terms", "is_active") and value is None:
            continue
        if field == "is_active" and value is False and any(abs(v) >= 0.01 for v in _float_balances(supplier).values()):
            raise HTTPException(status_code=400, detail="Ta'minotchida ochiq qarz/avans bor — avval hisob-kitobni yoping")
        before = getattr(supplier, field)
        if before != value:
            old[field] = str(before) if before is not None else None
            new[field] = str(value) if value is not None else None
            setattr(supplier, field, value)
    if new:
        log_action(db, action="UPDATE", entity_type="supplier", entity_id=supplier.id,
                   user_id=current_user.id, old_values=old, new_values=new)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.post("/{supplier_id}/adjust-debt", response_model=SupplierOut)
def adjust_supplier_debt(
    supplier_id: int,
    data: SupplierDebtAdjust,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*DEBT_ADJUST_ROLES)),
):
    """Qarzni qo'lda tuzatish — faqat farq (delta) qo'shiladi, sababi bilan jurnalga yoziladi.
    Butun balansni qayta yozmaydi, shuning uchun parallel xarid/to'lovlar yo'qolmaydi."""
    supplier = _get_supplier(db, supplier_id, current_user)
    reason = (data.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Tuzatish sababini kiriting")
    changes = [c for c in data.changes if c.delta]
    if not changes:
        raise HTTPException(status_code=400, detail="O'zgarish kiritilmagan")
    before = _float_balances(supplier)
    for c in changes:
        ledger.add(db, supplier, c.currency, c.delta)
    log_action(db, action="ADJUST_DEBT", entity_type="supplier", entity_id=supplier.id, user_id=current_user.id,
               old_values={"debt_balances": before},
               new_values={"debt_balances": supplier.debt_balances, "reason": reason,
                           "changes": [{"currency": c.currency.upper(), "delta": str(c.delta)} for c in changes]})
    db.commit()
    db.refresh(supplier)
    return supplier


@router.post("/bulk-import")
def bulk_import_suppliers(
    rows: list[dict],
    allow_update: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Excel fayldan ta'minotchilarni yuklash yoki yangilash. "Qarz" — UZS dagi joriy qarz."""
    FIELD_MAP = {
        "Nomi":                 ("name",          str),
        "INN":                  ("inn",           str),
        "Telefon":              ("phone",         str),
        "Email":                ("email",         str),
        "Manzil":               ("address",       str),
        "To'lov muddati (kun)": ("payment_terms", int),
    }

    def _parse(row, row_num, name):
        values, debt, bad = {}, None, []
        for row_key, (field, cast) in FIELD_MAP.items():
            raw = row.get(row_key)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                values[field] = cast(str(raw).strip()) if cast is int else str(raw).strip()
            except ValueError:
                bad.append(row_key)
        raw_debt = row.get("Qarz")
        if raw_debt is not None and str(raw_debt).strip() != "":
            try:
                debt = Decimal(str(raw_debt).strip().replace(" ", "").replace(",", "."))
            except InvalidOperation:
                bad.append("Qarz")
        for key in bad:
            errors.append({"row": row_num, "name": name, "error": f"'{key}' qiymati xato: {row.get(key)}"})
        return values, debt

    created = updated = 0
    errors = []
    dup_q_base = db.query(Supplier).filter(Supplier.company_id == current_user.company_id)

    for idx, row in enumerate(rows):
        row_num = row.get("__row_index", idx + 2)
        try:
            with db.begin_nested():
                name = str(row.get("Nomi") or "").strip()
                inn = str(row.get("INN") or "").strip() or None
                if not name:
                    errors.append({"row": row_num, "error": "Ta'minotchi nomi majburiy"})
                    continue

                existing = dup_q_base.filter(Supplier.inn == inn).first() if inn else None
                if not existing:
                    existing = dup_q_base.filter(Supplier.name == name).first()

                if existing and not allow_update:
                    errors.append({"row": row_num, "name": name, "error": f"'{name}' allaqachon mavjud — o'tkazib yuborildi"})
                    continue

                values, debt = _parse(row, row_num, name)
                if existing:
                    for field, val in values.items():
                        setattr(existing, field, val)
                    if debt is not None:
                        # Faylda joriy UZS qarz — farqi qo'shiladi
                        current = ledger.balances(existing).get("UZS", ZERO)
                        ledger.add(db, existing, "UZS", debt - current)
                    db.flush()
                    updated += 1
                    continue

                values.setdefault("name", name)
                sup = Supplier(**values, company_id=current_user.company_id,
                               debt_balance=ZERO, debt_currency="UZS", debt_balances={})
                db.add(sup)
                db.flush()
                if debt:
                    ledger.add(db, sup, "UZS", debt)
                db.flush()
                created += 1

        except SQLAlchemyError as exc:
            logger.warning("Bulk import row %s failed: %s", row_num, exc)
            errors.append({"row": row_num, "name": str(row.get("Nomi") or ""), "error": row_db_error(exc)})

    log_action(db, action="BULK_IMPORT", entity_type="supplier", user_id=current_user.id,
               new_values={"created": created, "updated": updated, "errors": len(errors)})
    db.commit()
    return {"created": created, "updated": updated, "skipped": len(errors), "errors": errors}


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Soft-delete: is_active = False. Qarzi yoki avansi bor ta'minotchi o'chirilmaydi
    (aks holda kreditorlik hisobotlardan yo'qolib qolardi)."""
    supplier = _get_supplier(db, supplier_id, current_user)
    open_balances = {k: v for k, v in _float_balances(supplier).items() if abs(v) >= 0.01}
    if open_balances:
        text = ", ".join(f"{v:,.2f} {k}" for k, v in open_balances.items())
        raise HTTPException(status_code=400, detail=f"Ta'minotchida ochiq qarz/avans bor ({text}) — avval hisob-kitobni yoping")
    supplier.is_active = False
    log_action(db, action="DELETE", entity_type="supplier", entity_id=supplier.id,
               user_id=current_user.id, old_values={"name": supplier.name})
    db.commit()


@router.post("/{supplier_id}/pay-debt", response_model=SupplierOut)
def pay_supplier_debt(
    supplier_id: int,
    data: SupplierDebtPayment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Ta'minotchi qarzini to'lash (Moliya sahifasidagi to'lov bilan bir xil mantiq)."""
    supplier = _get_supplier(db, supplier_id, current_user, active_only=True)
    ledger.pay_supplier(
        db, supplier, user=current_user, amount=data.amount, currency=data.currency or "UZS",
        payment_type=data.payment_type or "cash", wallet_id=data.wallet_id, reason=data.reason,
    )
    db.commit()
    db.refresh(supplier)
    return supplier


# ─── Statistika va tarix ─────────────────────────────────────────────────────

def _supplier_money(db: Session, supplier: Supplier, company_id: int):
    """Ta'minotchiga tegishli xaridlar, to'lov/qaytim tranzaksiyalari va qaytarish hujjatlari."""
    from app.models.moliya import Transaction
    from app.models.purchase_order import PurchaseOrder
    from app.services.supplier_return_service import return_logs

    purchases = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.items), joinedload(PurchaseOrder.creator))
        .filter(PurchaseOrder.supplier_id == supplier.id, PurchaseOrder.company_id == company_id)
        .order_by(PurchaseOrder.created_at.desc())
        .all()
    )
    po_ids = [p.id for p in purchases]
    po_payments = []
    if po_ids:
        po_payments = db.query(Transaction).filter(
            Transaction.company_id == company_id,
            Transaction.reference_type == "purchase_order",
            Transaction.reference_id.in_(po_ids),
        ).all()
    sup_txs = db.query(Transaction).filter(
        Transaction.company_id == company_id,
        Transaction.reference_type.in_(["supplier_payment", "return_to_supplier"]),
        Transaction.reference_id == supplier.id,
    ).all()
    return purchases, po_payments, sup_txs, return_logs(db, supplier.id)


def _tx_uzs(db: Session, tx, company_id: int) -> Decimal:
    if tx.meta and tx.meta.get("po_paid_uzs") is not None:
        return Decimal(str(tx.meta["po_paid_uzs"]))
    return Decimal(str(tx.amount or 0)) * ledger.currency_rate(db, company_id, tx.currency_code)


@router.get("/{supplier_id}/stats")
def get_supplier_stats(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    from app.models.purchase_order import POStatus

    supplier = _get_supplier(db, supplier_id, current_user)
    cid = current_user.company_id
    purchases, po_payments, sup_txs, returns = _supplier_money(db, supplier, cid)

    active = [p for p in purchases if p.status != POStatus.cancelled]
    received_uzs = ZERO
    for p in purchases:  # bekor qilinganning qabul qilingan qismi ham haqiqiy
        total = Decimal(str(p.total_amount or 0))
        ratio = Decimal(str(p.discount_amount or 0)) / total if total > 0 else ZERO
        received = sum((Decimal(str(i.qty_received or 0)) * Decimal(str(i.unit_cost or 0)) for i in p.items), ZERO)
        received_uzs += received * (1 - ratio)
    ordered_uzs = sum((Decimal(str(p.total_amount or 0)) - Decimal(str(p.discount_amount or 0)) for p in active), ZERO)

    paid_uzs = sum((_tx_uzs(db, t, cid) for t in po_payments), ZERO)
    paid_uzs += sum((_tx_uzs(db, t, cid) for t in sup_txs if t.reference_type == "supplier_payment"), ZERO)
    refunds_uzs = sum((_tx_uzs(db, t, cid) for t in sup_txs if t.reference_type == "return_to_supplier" and t.type == "income"), ZERO)
    returns_uzs = sum((Decimal(str(r["value"])) for r in returns), ZERO)

    return {
        "id": supplier.id,
        "name": supplier.name,
        "phone": supplier.phone,
        "inn": supplier.inn,
        "address": supplier.address,
        "payment_terms": supplier.payment_terms,
        "debt_balance": float(supplier.debt_balance or 0),
        "debt_balances": _float_balances(supplier),  # manfiy — avans
        "rates": _company_rates(db, cid),
        "total_purchases_count": len(active),
        # Qabul qilingan tovar qiymati (chegirma bilan) — qarz shundan hisoblanadi
        "total_purchases_amount": float(round(received_uzs, 2)),
        "total_ordered_amount": float(round(ordered_uzs, 2)),
        "total_paid_amount": float(round(paid_uzs - refunds_uzs, 2)),
        "total_returns_amount": float(round(returns_uzs, 2)),
    }


@router.get("/{supplier_id}/history")
def get_supplier_history(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    from app.services.purchase_order_service import display_amounts

    supplier = _get_supplier(db, supplier_id, current_user)
    cid = current_user.company_id
    purchases, po_payments, sup_txs, returns = _supplier_money(db, supplier, cid)
    po_numbers = {p.id: p.number for p in purchases}

    user_ids = {t.user_id for t in po_payments + sup_txs if t.user_id} | {r["user_id"] for r in returns if r["user_id"]}
    names = {}
    if user_ids:
        names = {u.id: u.name for u in db.query(User).filter(User.id.in_(user_ids)).all()}

    history = []
    for p in purchases:
        a = display_amounts(db, p)
        total = Decimal(str(p.total_amount or 0))
        ratio = Decimal(str(p.discount_amount or 0)) / total if total > 0 else ZERO
        received_uzs = sum((Decimal(str(i.qty_received or 0)) * Decimal(str(i.unit_cost or 0)) for i in p.items), ZERO) * (1 - ratio)
        net_uzs = total - Decimal(str(p.discount_amount or 0))
        status = p.status.value if hasattr(p.status, "value") else str(p.status)
        history.append({
            "id": p.id,
            "op_type": "purchase",
            "status": status,
            "date": p.created_at.isoformat() if p.created_at else "",
            "amount": float(a["total_cur"]),
            "amount_uzs": float(round(net_uzs, 2)),
            "received": float(round(received_uzs / a["rate"], 2)),
            "received_uzs": float(round(received_uzs, 2)),
            "paid": float(a["paid_cur"]),
            "paid_uzs": float(p.paid_amount or 0),
            "debt": float(a["debt_cur"]),
            "currency": a["currency"],
            "payment_type": "",
            "cashier": p.creator.name if p.creator else "",
            "sale_number": p.number,
            "description": f"Xarid #{p.number}",
            "type": "purchase",
            "deletable": False,
        })

    for tx in po_payments + sup_txs:
        is_refund = tx.reference_type == "return_to_supplier"
        cur = (tx.currency_code or "UZS").upper()
        number = po_numbers.get(tx.reference_id, "") if tx.reference_type == "purchase_order" else ""
        history.append({
            "id": tx.id,
            "op_type": "refund" if is_refund else "payment",
            "date": tx.created_at.isoformat() if tx.created_at else "",
            "amount": float(tx.amount or 0),
            "amount_uzs": float(round(_tx_uzs(db, tx, cid), 2)) if cur != "UZS" else None,
            "paid": float(tx.amount or 0),
            "debt": 0,
            "currency": cur,
            "payment_type": tx.payment_type or "cash",
            "cashier": names.get(tx.user_id, ""),
            "sale_number": number,
            "description": tx.description or ("Qaytim" if is_refund else "To'lov"),
            "type": "refund" if is_refund else "payment",
            "deletable": True,
        })

    for r in returns:
        history.append({
            "id": r["id"],
            "op_type": "return",
            "date": r["date"],
            "amount": r["value"],
            "amount_uzs": None,
            "paid": 0,
            "debt": 0,
            "currency": "UZS",
            "payment_type": "",
            "cashier": names.get(r["user_id"], ""),
            "sale_number": "",
            "description": r["description"],
            "type": "return",
            "deletable": False,
        })

    return sorted(history, key=lambda x: x.get("date") or "", reverse=True)
