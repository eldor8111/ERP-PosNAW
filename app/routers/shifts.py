"""
Shifts API: Manage cashier shifts.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel  # type: ignore
from decimal import Decimal
from datetime import datetime, timezone

from app.database import get_db  # type: ignore
from app.models.shift import Shift  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User  # type: ignore

router = APIRouter(prefix="/shifts", tags=["shifts"])


class ShiftOpen(BaseModel):
    branch_id: Optional[int] = None
    opening_cash: Decimal = Decimal("0")
    note: Optional[str] = None


class ShiftClose(BaseModel):
    closing_cash: Optional[Decimal] = None   # Kassir sanagan naqd pul
    wallet_id: Optional[int] = None          # Naqd tushadigan hamyon
    wallet_card_id: Optional[int] = None     # Plastik/Terminal tushadigan hamyon
    note: Optional[str] = None


ADMIN_ROLES = ("admin", "director")

@router.get("")
def list_shifts(
    branch_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Shift)
    if current_user.role.value != "super_admin":
        q = q.filter(Shift.company_id == current_user.company_id)
    # Non-admin: force filter to their own branch
    if current_user.role.value not in ADMIN_ROLES:
        if current_user.branch_id:
            q = q.filter(Shift.branch_id == current_user.branch_id)
    elif branch_id:
        q = q.filter(Shift.branch_id == branch_id)
    if status:
        q = q.filter(Shift.status == status)
    shifts = q.order_by(Shift.opened_at.desc()).all()
    return [
        {
            "id": s.id,
            "cashier_id": s.cashier_id,
            "cashier_name": s.cashier.name if s.cashier else None,
            "branch_id": s.branch_id,
            "opened_at": s.opened_at,
            "closed_at": s.closed_at,
            "opening_cash": s.opening_cash,
            "closing_cash": s.closing_cash,
            "status": s.status,
        }
        for s in shifts
    ]


@router.get("/current")
def get_current_shift(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get the currently active (open) shift for the authenticated user, including totals."""
    shift = db.query(Shift).filter(Shift.cashier_id == user.id, Shift.status == "open").first()
    if not shift:
        return None
    
    from app.models.sale import Sale, SalePayment
    from sqlalchemy import func
    
    # Calculate totals from sales during this shift per payment type
    payments = db.query(
        SalePayment.payment_type,
        func.sum(SalePayment.amount).label("total")
    ).join(Sale, SalePayment.sale_id == Sale.id).filter(
        Sale.cashier_id == user.id,
        Sale.created_at >= shift.opened_at,
        Sale.status != "cancelled"
    ).group_by(SalePayment.payment_type).all()

    balances = {}
    total_sales = Decimal("0")
    for p in payments:
        balances[p.payment_type] = str(p.total)
        total_sales += p.total

    if "cash" not in balances:
        balances["cash"] = "0"
    
    expected_cash = shift.opening_cash + Decimal(balances["cash"])
    
    return {
        "id": shift.id,
        "cashier_id": shift.cashier_id,
        "cashier_name": shift.cashier.name if shift.cashier else None,
        "branch_id": shift.branch_id,
        "opened_at": shift.opened_at,
        "closed_at": shift.closed_at,
        "opening_cash": str(shift.opening_cash),
        "expected_cash": str(expected_cash),
        "balances": balances,
        "total_sales": str(total_sales),
        "status": shift.status,
    }


@router.post("/open", status_code=201)
def open_shift(data: ShiftOpen, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Check if there's already an open shift for this cashier
    existing = db.query(Shift).filter(Shift.cashier_id == user.id, Shift.status == "open").first()
    if existing:
        raise HTTPException(status_code=400, detail="Kassir uchun faol smena allaqachon mavjud")
    # Auto-use user's branch if not explicitly provided
    branch_id = data.branch_id if data.branch_id is not None else user.branch_id
    shift = Shift(cashier_id=user.id, branch_id=branch_id, opening_cash=data.opening_cash, company_id=user.company_id)
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return {
        "id": shift.id,
        "cashier_id": shift.cashier_id,
        "branch_id": shift.branch_id,
        "opened_at": shift.opened_at,
        "status": shift.status,
    }


def _calc_shift_payment_balances(db: Session, shift: Shift):
    """SalePayment jadvalidan smena davomidagi to'lovlarni hisoblaydi."""
    from app.models.sale import Sale, SalePayment
    from sqlalchemy import func
    payments = db.query(
        SalePayment.payment_type,
        func.sum(SalePayment.amount).label("total")
    ).join(Sale, SalePayment.sale_id == Sale.id).filter(
        Sale.cashier_id == shift.cashier_id,
        Sale.created_at >= shift.opened_at,
        Sale.status != "cancelled"
    ).group_by(SalePayment.payment_type).all()
    balances = {p.payment_type: Decimal(str(p.total)) for p in payments}
    cash_total = balances.get("cash", Decimal("0"))
    return cash_total, balances


@router.post("/close")
def close_current_shift(data: ShiftClose = ShiftClose(), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Close the current user's active shift (no shift_id needed)."""
    shift = db.query(Shift).filter(Shift.cashier_id == user.id, Shift.status == "open").first()
    if not shift:
        raise HTTPException(status_code=404, detail="Faol smena topilmadi")

    cash_total, balances = _calc_shift_payment_balances(db, shift)

    shift.closed_at = datetime.now(timezone.utc)
    shift.closing_cash = data.closing_cash if data.closing_cash is not None else cash_total
    shift.status = "closed"

    from app.models.moliya import Wallet, Transaction, WalletBalance

    if data.wallet_id and cash_total > 0:
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            wallet.balance = float(wallet.balance) + float(cash_total)
            wb = db.query(WalletBalance).filter(WalletBalance.wallet_id == wallet.id, WalletBalance.payment_type == "cash").first()
            if not wb:
                wb = WalletBalance(wallet_id=wallet.id, payment_type="cash", balance=cash_total)
                db.add(wb)
            else:
                wb.balance = float(wb.balance) + float(cash_total)
            
            db.add(Transaction(
                branch_id=shift.branch_id, company_id=shift.company_id,
                type="income", amount=cash_total, payment_type="cash",
                wallet_id=wallet.id, reference_type="shift", reference_id=shift.id,
                description=f"Smena yopilishi - inkassatsiya (Naqd, {user.name})"
            ))

    if data.wallet_card_id:
        wallet_card = db.get(Wallet, data.wallet_card_id)
        if wallet_card:
            for p_type, amount in balances.items():
                if p_type == "cash" or amount <= 0:
                    continue
                wallet_card.balance = float(wallet_card.balance) + float(amount)
                wb = db.query(WalletBalance).filter(WalletBalance.wallet_id == wallet_card.id, WalletBalance.payment_type == p_type).first()
                if not wb:
                    wb = WalletBalance(wallet_id=wallet_card.id, payment_type=p_type, balance=amount)
                    db.add(wb)
                else:
                    wb.balance = float(wb.balance) + float(amount)

                db.add(Transaction(
                    branch_id=shift.branch_id, company_id=shift.company_id,
                    type="income", amount=amount, payment_type=p_type,
                    wallet_id=wallet_card.id, reference_type="shift", reference_id=shift.id,
                    description=f"Smena yopilishi - inkassatsiya ({p_type}, {user.name})"
                ))

    db.commit()
    db.refresh(shift)
    return {"id": shift.id, "status": shift.status, "closed_at": shift.closed_at}


@router.post("/{shift_id}/close")
def close_shift(shift_id: int, data: ShiftClose = ShiftClose(), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = db.get(Shift, shift_id)
    if not shift or (user.role.value != "super_admin" and shift.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Smena topilmadi")
    from app.models.user import UserRole
    if user.role not in (UserRole.super_admin, UserRole.admin, UserRole.director):
        if shift.cashier_id != user.id:
            raise HTTPException(status_code=403, detail="Boshqa kassirning smenasini yopa olmaysiz")
    if shift.status == "closed":
        raise HTTPException(status_code=400, detail="Smena allaqachon yopilgan")

    cash_total, balances = _calc_shift_payment_balances(db, shift)

    shift.closed_at = datetime.now(timezone.utc)
    shift.closing_cash = data.closing_cash if data.closing_cash is not None else cash_total
    shift.status = "closed"

    from app.models.moliya import Wallet, Transaction, WalletBalance

    if data.wallet_id and cash_total > 0:
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            wallet.balance = float(wallet.balance) + float(cash_total)
            wb = db.query(WalletBalance).filter(WalletBalance.wallet_id == wallet.id, WalletBalance.payment_type == "cash").first()
            if not wb:
                wb = WalletBalance(wallet_id=wallet.id, payment_type="cash", balance=cash_total)
                db.add(wb)
            else:
                wb.balance = float(wb.balance) + float(cash_total)

            db.add(Transaction(
                branch_id=shift.branch_id, company_id=shift.company_id,
                type="income", amount=cash_total, payment_type="cash",
                wallet_id=wallet.id, reference_type="shift", reference_id=shift.id,
                description=f"Smena yopilishi - inkassatsiya (Naqd, {user.name})"
            ))

    if data.wallet_card_id:
        wallet_card = db.get(Wallet, data.wallet_card_id)
        if wallet_card:
            for p_type, amount in balances.items():
                if p_type == "cash" or amount <= 0:
                    continue
                wallet_card.balance = float(wallet_card.balance) + float(amount)
                wb = db.query(WalletBalance).filter(WalletBalance.wallet_id == wallet_card.id, WalletBalance.payment_type == p_type).first()
                if not wb:
                    wb = WalletBalance(wallet_id=wallet_card.id, payment_type=p_type, balance=amount)
                    db.add(wb)
                else:
                    wb.balance = float(wb.balance) + float(amount)

                db.add(Transaction(
                    branch_id=shift.branch_id, company_id=shift.company_id,
                    type="income", amount=amount, payment_type=p_type,
                    wallet_id=wallet_card.id, reference_type="shift", reference_id=shift.id,
                    description=f"Smena yopilishi - inkassatsiya ({p_type}, {user.name})"
                ))

    db.commit()
    db.refresh(shift)
    return {"id": shift.id, "status": shift.status, "closed_at": shift.closed_at}


@router.get("/{shift_id}")
def get_shift(shift_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = db.get(Shift, shift_id)
    if not shift or (user.role.value != "super_admin" and shift.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Not found")
    return shift
