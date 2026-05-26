from datetime import datetime, timezone, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.moliya import (
    Wallet, KassaSession, KassaMovement, ExpenseCategory,
    Expense, Transaction, PAYMENT_TYPES
)

router = APIRouter(prefix="/kassa", tags=["Kassa"])

# ─── Schemas ─────────────────────────────────────────────────────────────────

class WalletCreate(BaseModel):
    name: str
    type: str = "cash"
    branch_id: Optional[int] = None
    opening_balance: float = 0

class WalletUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class OpenKassaIn(BaseModel):
    opening_balance: float = 0
    note: Optional[str] = None

class CloseKassaIn(BaseModel):
    actual_amounts: dict  # {cash: 0, card: 0, ...}
    note: Optional[str] = None

class InvestIn(BaseModel):
    amount: float
    payment_type: str = "cash"
    description: Optional[str] = None

class WithdrawIn(BaseModel):
    amount: float
    payment_type: str = "cash"
    description: Optional[str] = None

class ExpenseCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ExpenseCreate(BaseModel):
    wallet_id: int
    category_id: int
    amount: float
    payment_type: str = "cash"
    description: Optional[str] = None

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_kassa_balances(wallet_id: int, db: Session) -> dict:
    """Har bir payment_type uchun balans hisoblash."""
    result = {}
    for ptype in PAYMENT_TYPES:
        income = db.query(func.sum(KassaMovement.amount)).filter(
            KassaMovement.wallet_id == wallet_id,
            KassaMovement.payment_type == ptype,
            KassaMovement.direction == "in"
        ).scalar() or 0

        expense = db.query(func.sum(KassaMovement.amount)).filter(
            KassaMovement.wallet_id == wallet_id,
            KassaMovement.payment_type == ptype,
            KassaMovement.direction == "out"
        ).scalar() or 0

        result[ptype] = float(income) - float(expense)
    result["total"] = sum(result.values())
    return result


def wallet_out(wallet, db, current_user):
    balances = get_kassa_balances(wallet.id, db)
    open_session = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet.id,
        KassaSession.status == "open"
    ).first()
    return {
        "id": wallet.id,
        "name": wallet.name,
        "type": wallet.type,
        "is_active": wallet.is_active,
        "is_open": wallet.is_open,
        "company_id": wallet.company_id,
        "branch_id": wallet.branch_id,
        "opening_balance": float(wallet.opening_balance or 0),
        "opened_at": wallet.opened_at,
        "closed_at": wallet.closed_at,
        "created_at": wallet.created_at,
        "balances": balances,
        "session_id": open_session.id if open_session else None,
    }


# ─── Kassalar CRUD ────────────────────────────────────────────────────────────

@router.get("")
def list_wallets(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    wallets = db.query(Wallet).filter(
        Wallet.company_id == current_user.company_id,
        Wallet.is_active == True
    ).order_by(Wallet.id).all()
    return [wallet_out(w, db, current_user) for w in wallets]


@router.post("")
def create_wallet(data: WalletCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = Wallet(
        name=data.name,
        type=data.type,
        company_id=current_user.company_id,
        branch_id=data.branch_id,
        balance=data.opening_balance,
        opening_balance=data.opening_balance,
        is_active=True,
        is_open=False,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    # Boshlang'ich pul kiritish harakati
    if data.opening_balance > 0:
        mv = KassaMovement(
            wallet_id=w.id,
            company_id=current_user.company_id,
            direction="in",
            payment_type="cash",
            amount=data.opening_balance,
            reference_type="opening",
            description="Boshlang'ich balans",
            created_by=current_user.id,
        )
        db.add(mv)
        db.commit()
    return wallet_out(w, db, current_user)


@router.get("/{wallet_id}")
def get_wallet(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(
        Wallet.id == wallet_id,
        Wallet.company_id == current_user.company_id
    ).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    return wallet_out(w, db, current_user)


@router.patch("/{wallet_id}")
def update_wallet(wallet_id: int, data: WalletUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if data.name is not None:
        w.name = data.name
    if data.is_active is not None:
        w.is_active = data.is_active
    db.commit()
    return wallet_out(w, db, current_user)


@router.delete("/{wallet_id}")
def delete_wallet(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    w.is_active = False
    db.commit()
    return {"ok": True}


# ─── Kassa ochish/yopish ─────────────────────────────────────────────────────

@router.post("/{wallet_id}/open")
def open_kassa(wallet_id: int, data: OpenKassaIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if w.is_open:
        raise HTTPException(400, "Kassa allaqachon ochiq")

    now = datetime.now(timezone.utc)
    w.is_open = True
    w.opened_at = now
    w.opened_by = current_user.id
    w.closed_at = None

    session = KassaSession(
        wallet_id=w.id,
        company_id=current_user.company_id,
        opened_by=current_user.id,
        opening_balance=data.opening_balance,
        note=data.note,
        status="open",
    )
    db.add(session)
    db.flush()

    if data.opening_balance > 0:
        mv = KassaMovement(
            wallet_id=w.id,
            company_id=current_user.company_id,
            session_id=session.id,
            direction="in",
            payment_type="cash",
            amount=data.opening_balance,
            reference_type="opening",
            description=f"Kassa ochilishi — boshlang'ich balans",
            created_by=current_user.id,
        )
        db.add(mv)

    db.commit()
    return {"ok": True, "session_id": session.id, "opened_at": now}


@router.post("/{wallet_id}/close")
def close_kassa(wallet_id: int, data: CloseKassaIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if not w.is_open:
        raise HTTPException(400, "Kassa allaqachon yopiq")

    balances = get_kassa_balances(wallet_id, db)
    now = datetime.now(timezone.utc)

    session = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet_id,
        KassaSession.status == "open"
    ).first()

    if session:
        session.closed_at = now
        session.closed_by = current_user.id
        session.status = "closed"
        session.closing_summary = {
            "calculated": balances,
            "actual": data.actual_amounts,
            "note": data.note,
        }

    w.is_open = False
    w.closed_at = now
    w.closed_by = current_user.id

    db.commit()
    return {
        "ok": True,
        "closed_at": now,
        "calculated_balances": balances,
        "actual_amounts": data.actual_amounts,
        "session_id": session.id if session else None,
    }


# ─── Investitsiya / Chiqarish ─────────────────────────────────────────────────

@router.post("/{wallet_id}/invest")
def invest(wallet_id: int, data: InvestIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if data.amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")

    session = db.query(KassaSession).filter(KassaSession.wallet_id == wallet_id, KassaSession.status == "open").first()

    mv = KassaMovement(
        wallet_id=wallet_id,
        company_id=current_user.company_id,
        session_id=session.id if session else None,
        direction="in",
        payment_type=data.payment_type,
        amount=data.amount,
        reference_type="invest",
        description=data.description or "Investitsiya",
        created_by=current_user.id,
    )
    db.add(mv)
    w.balance = float(w.balance or 0) + data.amount
    db.commit()
    return {"ok": True}


@router.post("/{wallet_id}/withdraw")
def withdraw(wallet_id: int, data: WithdrawIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if data.amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")

    balances = get_kassa_balances(wallet_id, db)
    if balances.get(data.payment_type, 0) < data.amount:
        raise HTTPException(400, f"{data.payment_type} bo'yicha balans yetarli emas")

    session = db.query(KassaSession).filter(KassaSession.wallet_id == wallet_id, KassaSession.status == "open").first()

    mv = KassaMovement(
        wallet_id=wallet_id,
        company_id=current_user.company_id,
        session_id=session.id if session else None,
        direction="out",
        payment_type=data.payment_type,
        amount=data.amount,
        reference_type="withdraw",
        description=data.description or "Chiqarish",
        created_by=current_user.id,
    )
    db.add(mv)
    w.balance = float(w.balance or 0) - data.amount
    db.commit()
    return {"ok": True}


# ─── Kassa tarixi ─────────────────────────────────────────────────────────────

@router.get("/{wallet_id}/history")
def kassa_history(
    wallet_id: int,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    direction: Optional[str] = Query(None),  # in | out
    payment_type: Optional[str] = Query(None),
    reference_type: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Company isolation
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")

    q = db.query(KassaMovement).filter(
        KassaMovement.wallet_id == wallet_id,
        KassaMovement.company_id == current_user.company_id,
    )
    if date_from:
        q = q.filter(KassaMovement.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        from datetime import time as dt_time
        q = q.filter(KassaMovement.created_at <= datetime.combine(date_to, dt_time(23, 59, 59)))
    if direction:
        q = q.filter(KassaMovement.direction == direction)
    if payment_type:
        q = q.filter(KassaMovement.payment_type == payment_type)
    if reference_type:
        q = q.filter(KassaMovement.reference_type == reference_type)

    total = q.count()
    items = q.order_by(KassaMovement.created_at.desc()).offset(skip).limit(limit).all()

    # Summary
    total_in = db.query(func.sum(KassaMovement.amount)).filter(
        KassaMovement.wallet_id == wallet_id,
        KassaMovement.company_id == current_user.company_id,
        KassaMovement.direction == "in"
    ).scalar() or 0
    total_out = db.query(func.sum(KassaMovement.amount)).filter(
        KassaMovement.wallet_id == wallet_id,
        KassaMovement.company_id == current_user.company_id,
        KassaMovement.direction == "out"
    ).scalar() or 0

    return {
        "total": total,
        "summary": {
            "total_in": float(total_in),
            "total_out": float(total_out),
            "balance": float(total_in) - float(total_out),
        },
        "items": [
            {
                "id": m.id,
                "direction": m.direction,
                "payment_type": m.payment_type,
                "amount": float(m.amount),
                "reference_type": m.reference_type,
                "reference_id": m.reference_id,
                "description": m.description,
                "created_at": m.created_at,
            }
            for m in items
        ],
    }


@router.get("/{wallet_id}/summary")
def kassa_summary(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    return get_kassa_balances(wallet_id, db)


# ─── Sessiyalar tarixi ────────────────────────────────────────────────────────

@router.get("/{wallet_id}/sessions")
def kassa_sessions(wallet_id: int, skip: int = 0, limit: int = 20, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    sessions = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet_id,
        KassaSession.company_id == current_user.company_id,
    ).order_by(KassaSession.opened_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": s.id,
            "status": s.status,
            "opened_at": s.opened_at,
            "closed_at": s.closed_at,
            "opening_balance": float(s.opening_balance or 0),
            "closing_summary": s.closing_summary,
            "note": s.note,
        }
        for s in sessions
    ]


# ─── Xarajat kategoriyalari ───────────────────────────────────────────────────

@router.get("/expense-categories/list")
def list_expense_categories(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cats = db.query(ExpenseCategory).filter(
        (ExpenseCategory.company_id == current_user.company_id) | (ExpenseCategory.company_id == None)
    ).order_by(ExpenseCategory.name).all()
    return [{"id": c.id, "name": c.name, "description": c.description} for c in cats]


@router.post("/expense-categories/list")
def create_expense_category(data: ExpenseCategoryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cat = ExpenseCategory(
        name=data.name,
        description=data.description,
        company_id=current_user.company_id,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "description": cat.description}


# ─── Xarajat qilish ───────────────────────────────────────────────────────────

@router.post("/expense")
def create_expense(data: ExpenseCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # Wallet company isolation
    w = db.query(Wallet).filter(Wallet.id == data.wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if data.amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")

    balances = get_kassa_balances(data.wallet_id, db)
    if balances.get(data.payment_type, 0) < data.amount:
        raise HTTPException(400, f"{data.payment_type} bo'yicha balans yetarli emas")

    # Branch olish
    from app.models.branch import Branch as _Branch
    branch = db.query(_Branch).filter(_Branch.company_id == current_user.company_id).first()
    branch_id = current_user.branch_id or (branch.id if branch else 0)

    # Expense yozuvi
    exp = Expense(
        branch_id=branch_id,
        category_id=data.category_id,
        amount=data.amount,
        company_id=current_user.company_id,
        wallet_id=data.wallet_id,
        description=data.description,
        approved_by=current_user.id,
    )
    db.add(exp)
    db.flush()

    # Kassa harakati
    session = db.query(KassaSession).filter(KassaSession.wallet_id == data.wallet_id, KassaSession.status == "open").first()
    cat = db.get(ExpenseCategory, data.category_id)
    mv = KassaMovement(
        wallet_id=data.wallet_id,
        company_id=current_user.company_id,
        session_id=session.id if session else None,
        direction="out",
        payment_type=data.payment_type,
        amount=data.amount,
        reference_type="expense",
        reference_id=exp.id,
        description=data.description or (cat.name if cat else "Xarajat"),
        created_by=current_user.id,
    )
    db.add(mv)

    # Transaction (ChiqimTolovlar sahifasi uchun)
    tx = Transaction(
        company_id=current_user.company_id,
        branch_id=branch_id,
        wallet_id=data.wallet_id,
        type="expense",
        amount=data.amount,
        payment_type=data.payment_type,
        reference_type="expense",
        reference_id=exp.id,
        description=data.description or (cat.name if cat else "Xarajat"),
    )
    db.add(tx)

    w.balance = float(w.balance or 0) - data.amount
    db.commit()
    return {"ok": True, "expense_id": exp.id}


@router.get("/{wallet_id}/expenses")
def list_expenses(
    wallet_id: int,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = 0, limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    q = db.query(Expense).filter(Expense.wallet_id == wallet_id, Expense.company_id == current_user.company_id)
    if date_from:
        q = q.filter(Expense.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        from datetime import time as dt_time
        q = q.filter(Expense.created_at <= datetime.combine(date_to, dt_time(23, 59, 59)))
    total = q.count()
    items = q.order_by(Expense.created_at.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "category": e.category.name if e.category else None,
                "description": e.description,
                "created_at": e.created_at,
            }
            for e in items
        ],
    }
