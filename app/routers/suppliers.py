from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore
from pydantic import BaseModel
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy.orm.attributes import flag_modified  # type: ignore

from app.core.audit import log_action  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.database import get_db  # type: ignore
from app.models.supplier import Supplier  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.schemas.supplier import SupplierCreate, SupplierOut, SupplierUpdate  # type: ignore
from app.utils.translit import name_search_filter  # type: ignore

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)


class SupplierDebtPayment(BaseModel):
    amount: float
    reason: str = "Qarz to'lovi"
    wallet_id: Optional[int] = None
    payment_type: Optional[str] = "cash"
    currency: Optional[str] = "UZS"



@router.get("", response_model=List[SupplierOut])
def list_suppliers(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.is_active == True)
    q = q.filter(Supplier.company_id == current_user.company_id)
    if search:
        q = q.filter(name_search_filter(Supplier.name, search))
    return q.offset(skip).limit(limit).all()


@router.post("", response_model=SupplierOut)
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    try:
        supplier_data = data.model_dump()
        supplier_data["company_id"] = current_user.company_id
        if supplier_data.get("debt_balances") is None:
            supplier_data["debt_balances"] = {}
        supplier = Supplier(**supplier_data)
        db.add(supplier)
        db.flush()
        log_action(
            db,
            action="CREATE",
            entity_type="supplier",
            entity_id=supplier.id,
            user_id=current_user.id,
            new_values={"name": supplier.name},
        )
        db.commit()
        db.refresh(supplier)
        return supplier
    except Exception:
        db.rollback()
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Ta'minotchi saqlashda xato")


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    old = {"name": supplier.name}
    for field, value in data.model_dump(exclude_none=True).items():
        if field == "debt_balances" and value is None:
            value = {}
        setattr(supplier, field, value)
    if "debt_balances" in data.model_dump(exclude_none=True):
        flag_modified(supplier, "debt_balances")
    log_action(
        db,
        action="UPDATE",
        entity_type="supplier",
        entity_id=supplier.id,
        user_id=current_user.id,
        old_values=old,
        new_values={"name": supplier.name},
    )
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
    """Excel fayldan ta'minotchilarni yuklash yoki yangilash."""
    FIELD_MAP = {
        "Nomi":                 ("name",          str),
        "INN":                  ("inn",           str),
        "Telefon":              ("phone",         str),
        "Email":                ("email",         str),
        "Manzil":               ("address",       str),
        "To'lov muddati (kun)": ("payment_terms", int),
        "Qarz":                 ("debt_balance",  Decimal),
    }

    created = 0
    updated = 0
    errors = []

    dup_q_base = db.query(Supplier).filter(Supplier.company_id == current_user.company_id)

    for idx, row in enumerate(rows):
        row_num = row.get("__row_index", idx + 2)
        name = str(row.get("Nomi") or "").strip()
        inn = str(row.get("INN") or "").strip() or None

        if not name:
            errors.append({"row": row_num, "error": "Ta'minotchi nomi majburiy"})
            continue

        existing = None
        if inn:
            existing = dup_q_base.filter(Supplier.inn == inn).first()
        if not existing:
            existing = dup_q_base.filter(Supplier.name == name).first()

        if existing:
            if not allow_update:
                errors.append({
                    "row": row_num, "name": name,
                    "error": f"'{name}' allaqachon mavjud — o'tkazib yuborildi"
                })
                continue
            
            for row_key, (field, cast) in FIELD_MAP.items():
                raw = row.get(row_key)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    val = str(raw).strip()
                    if cast == Decimal:
                        val = Decimal(val)
                    elif cast == int:
                        val = int(val)
                    setattr(existing, field, val)
                except Exception:
                    errors.append({"row": row_num, "name": name, "error": f"'{row_key}' qiymati xato: {raw}"})
                    continue

            updated += 1
            continue

        kwargs = {"company_id": current_user.company_id}
        for row_key, (field, cast) in FIELD_MAP.items():
            raw = row.get(row_key)
            if raw is not None and str(raw).strip() != "":
                try:
                    val = str(raw).strip()
                    if cast == Decimal:
                        val = Decimal(val)
                    elif cast == int:
                        val = int(val)
                    kwargs[field] = val
                except:
                    pass

        # check specific constraints if needed
        if "name" not in kwargs:
            kwargs["name"] = name

        sup = Supplier(**kwargs)
        db.add(sup)
        db.flush()
        created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": len(errors), "errors": errors}

@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Soft-delete: is_active = False"""
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    supplier.is_active = False
    log_action(
        db,
        action="DELETE",
        entity_type="supplier",
        entity_id=supplier.id,
        user_id=current_user.id,
        old_values={"name": supplier.name},
    )
    db.commit()


@router.post("/{supplier_id}/pay-debt", response_model=SupplierOut)
def pay_supplier_debt(
    supplier_id: int,
    data: SupplierDebtPayment,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Ta'minotchi qarzini to'lash — debt_balance ni kamaytiradi"""
    q = db.query(Supplier).filter(
        Supplier.id == supplier_id,
        Supplier.company_id == current_user.company_id,
        Supplier.is_active == True,
    )
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="To'lov miqdori musbat bo'lishi kerak")
    
    currency = data.currency or "UZS"

    # Ensure debt_balances is initialised before any reads
    if not supplier.debt_balances:
        supplier.debt_balances = {}

    # --- LEGACY MIGRATION ---
    if not supplier.debt_balances and float(supplier.debt_balance or 0) > 0:
        legacy_currency = (supplier.debt_currency or "UZS").strip().upper() or "UZS"
        supplier.debt_balances = {legacy_currency: float(supplier.debt_balance)}

    # Update the currency-specific balance in debt_balances JSON
    from decimal import Decimal
    from sqlalchemy.orm.attributes import flag_modified
    from app.models.currency import Currency as CurrencyModel

    def get_rate(cur: str) -> Decimal:
        """Valyuta kursini qaytaradi (UZS=1)"""
        if cur == "UZS":
            return Decimal("1")
        obj = db.query(CurrencyModel).filter(CurrencyModel.code == cur).first()
        return Decimal(str(obj.rate)) if obj else Decimal("1")

    payment_currency = currency          # to'lov valyutasi
    payment_amount   = Decimal(str(data.amount))
    payment_rate     = get_rate(payment_currency)
    payment_in_uzs   = payment_amount * payment_rate  # to'lov UZS ekvivalenti

    remaining_uzs = payment_in_uzs  # hali qoplash kerak bo'lgan UZS

    # 1) Avval to'lov valyutasidagi qarzdan ayiramiz
    if payment_currency in supplier.debt_balances and float(supplier.debt_balances[payment_currency]) > 0:
        debt_in_pay_cur = Decimal(str(supplier.debt_balances[payment_currency]))
        deducted = min(debt_in_pay_cur, payment_amount)
        supplier.debt_balances[payment_currency] = float(debt_in_pay_cur - deducted)
        remaining_uzs -= deducted * payment_rate

    # 2) Qolgan summa bo'lsa, boshqa valyutalardagi qarzlardan kurs bo'yicha ayiramiz
    if remaining_uzs > Decimal("0.001"):
        for debt_cur, debt_val in list(supplier.debt_balances.items()):
            if remaining_uzs <= Decimal("0.001"):
                break
            if debt_cur == payment_currency:
                continue
            debt_amount = Decimal(str(debt_val))
            if debt_amount <= 0:
                continue
            debt_rate = get_rate(debt_cur)
            # Bu valyutadagi qarz UZS ekvivalenti
            debt_in_uzs = debt_amount * debt_rate
            if debt_in_uzs <= Decimal("0.001"):
                continue
            # Necha UZS qoplanadi bu qarzdan
            uzs_to_cover = min(remaining_uzs, debt_in_uzs)
            # UZS dan ushbu valyutaga o'tkazamiz
            amount_in_debt_cur = uzs_to_cover / debt_rate
            supplier.debt_balances[debt_cur] = float(
                max(Decimal("0"), debt_amount - amount_in_debt_cur)
            )
            remaining_uzs -= uzs_to_cover

    flag_modified(supplier, "debt_balances")

    # Update aggregate debt_balance (always in UZS)
    exchange_rate = payment_rate
    amount_in_uzs = payment_in_uzs
    supplier.debt_balance = max(Decimal("0"), Decimal(str(supplier.debt_balance or 0)) - amount_in_uzs)



    from app.models.moliya import Transaction, Wallet, KassaMovement
    from app.models.branch import Branch as _Branch

    # Wallet balansini yangilash (agar wallet tanlangan bo'lsa)
    if data.wallet_id:
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            wallet.balance = float(wallet.balance) - float(data.amount)

    # branch_id ni xavfsiz olish
    tx_branch_id = current_user.branch_id
    if not tx_branch_id and current_user.company_id:
        br = db.query(_Branch).filter(_Branch.company_id == current_user.company_id).first()
        tx_branch_id = br.id if br else None

    tx_desc = data.reason or ""
    if currency != "UZS":
        tx_desc = tx_desc + f" ({data.amount} {currency})"
        
    # Tranzaksiya DOIM yoziladi (wallet_id bo'lmasa ham)
    tx = Transaction(
        company_id=current_user.company_id,
        branch_id=tx_branch_id or 0,
        wallet_id=data.wallet_id,
        type="expense",
        amount=data.amount,
        currency_code=currency,
        payment_type=data.payment_type,
        reference_type="supplier_payment",
        reference_id=supplier_id,
        description=tx_desc.strip(),
        user_id=current_user.id
    )
    db.add(tx)

    # KassaMovement — ta'minotchi to'lovi (chiqim)
    if data.wallet_id:
        db.add(KassaMovement(
            wallet_id=data.wallet_id,
            company_id=current_user.company_id,
            direction="out",
            payment_type=data.payment_type or "cash",
            amount=data.amount,
            reference_type="supplier_payment",
            reference_id=supplier_id,
            description=f"Ta'minotchi to'lovi: {supplier.name} — {data.reason}",
            created_by=current_user.id,
        ))

    log_action(
        db,
        action="PAY_DEBT",
        entity_type="supplier",
        entity_id=supplier.id,
        user_id=current_user.id,
        new_values={"amount": data.amount, "reason": data.reason},
    )
    db.commit()
    db.refresh(supplier)
    return supplier


@router.get("/{supplier_id}/stats")
def get_supplier_stats(supplier_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*ALLOWED))):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")

    from app.models.purchase_order import PurchaseOrder, POStatus

    all_pos = db.query(PurchaseOrder).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.company_id == current_user.company_id
    ).all()
    
    active_pos = [p for p in all_pos if p.status != POStatus.cancelled]
    
    balances = dict(supplier.debt_balances or {})
    if not balances and float(supplier.debt_balance or 0) > 0:
        balances["UZS"] = float(supplier.debt_balance)

    return {
        "id": supplier.id,
        "name": supplier.name,
        "phone": supplier.phone,
        "inn": supplier.inn,
        "address": supplier.address,
        "payment_terms": supplier.payment_terms,
        "debt_balance": float(supplier.debt_balance or 0),
        "debt_balances": balances,
        "total_purchases_count": len(active_pos),
        "total_purchases_amount": sum(float(p.total_amount) for p in active_pos),
        "total_paid_amount": sum(float(p.paid_amount) for p in active_pos),
    }


@router.get("/{supplier_id}/history")
def get_supplier_history(supplier_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*ALLOWED))):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")

    from app.models.purchase_order import PurchaseOrder
    from app.models.moliya import Transaction

    # 1) Barcha xaridlar
    purchases = db.query(PurchaseOrder).filter(
        PurchaseOrder.supplier_id == supplier_id,
        PurchaseOrder.company_id == current_user.company_id
    ).order_by(PurchaseOrder.created_at.desc()).all()

    # 2) Barcha to'lovlar (supplier_payment va purchase_order reference bilan bo'lgan chiqimlar)
    payments = db.query(Transaction).filter(
        Transaction.reference_type.in_(["supplier_payment", "purchase_order"]),
        Transaction.reference_id == supplier_id,
        Transaction.company_id == current_user.company_id,
        Transaction.type == "expense"
    ).order_by(Transaction.created_at.desc()).all()

    history = []

    for p in purchases:
        total = float(p.total_amount or 0)
        paid = float(p.paid_amount or 0)
        debt_added = max(0.0, total - paid)
        history.append({
            "id": p.id,
            "op_type": "purchase",
            "date": p.created_at.isoformat(),
            "amount": total,
            "paid": paid,
            "debt": debt_added,
            "currency": getattr(p, "currency", "UZS") or "UZS",
            "payment_type": "",
            "cashier": getattr(p.creator, "name", "") if p.creator else "",
            "sale_number": getattr(p, "number", ""),
            "description": f"Xarid #{getattr(p, 'number', '')}",
            "type": "purchase",
        })

    for pay in payments:
        history.append({
            "id": pay.id,
            "op_type": "payment",
            "date": pay.created_at.isoformat(),
            "amount": float(pay.amount or 0),
            "paid": float(pay.amount or 0),
            "debt": 0,
            "currency": pay.currency_code or "UZS",
            "payment_type": pay.payment_type or "cash",
            "cashier": getattr(pay.user, "name", "") if pay.user else "",
            "sale_number": "",
            "description": pay.description or "To'lov",
            "type": "payment",
        })

    return sorted(history, key=lambda x: x["date"], reverse=True)
