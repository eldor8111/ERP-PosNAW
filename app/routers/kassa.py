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
    Expense, Transaction, PAYMENT_TYPES, CashTransfer
)

router = APIRouter(prefix="/kassa", tags=["Kassa"])

# ─── Schemas ─────────────────────────────────────────────────────────────────

class WalletCreate(BaseModel):
    name: str
    type: str = "cash"
    currency: str = "UZS"
    branch_id: Optional[int] = None
    opening_balance: float = 0

class WalletUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None

class OpenKassaIn(BaseModel):
    opening_balance: float = 0
    currency: str = "UZS"
    note: Optional[str] = None

class CloseKassaIn(BaseModel):
    # Example format: {"cash": {"UZS": 50000, "USD": 100}, "card": {"UZS": 120000}}
    actual_amounts: dict  
    note: Optional[str] = None

class TransferOutIn(BaseModel):
    receiver_wallet_id: int
    amount: float
    currency: str = "UZS"
    payment_type: str = "cash"
    note: Optional[str] = None

class TransferStatusIn(BaseModel):
    transfer_id: int

class InvestIn(BaseModel):
    amount: float
    payment_type: str = "cash"
    currency: str = "UZS"
    description: Optional[str] = None

class WithdrawIn(BaseModel):
    amount: float
    payment_type: str = "cash"
    currency: str = "UZS"
    description: Optional[str] = None

class ExpenseCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ExpenseCreate(BaseModel):
    wallet_id: int
    category_id: int
    amount: float
    payment_type: str = "cash"
    currency: str = "UZS"
    description: Optional[str] = None

class ExpenseUpdate(BaseModel):
    category_id: Optional[int] = None
    amount: Optional[float] = None
    payment_type: Optional[str] = None
    currency: Optional[str] = None
    description: Optional[str] = None

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_kassa_balances(wallet_id: int, db: Session) -> dict:
    """Har bir payment_type uchun valyutalar bo'yicha balans hisoblash."""
    result = {}
    for ptype in PAYMENT_TYPES:
        # Har bir payment_type uchun barcha valyutalarni olish
        movements = db.query(KassaMovement.currency, func.sum(KassaMovement.amount)).filter(
            KassaMovement.wallet_id == wallet_id,
            KassaMovement.payment_type == ptype
        ).group_by(KassaMovement.currency).all()
        
        currency_balances = []
        for currency, total in movements:
            income = db.query(func.sum(KassaMovement.amount)).filter(
                KassaMovement.wallet_id == wallet_id,
                KassaMovement.payment_type == ptype,
                KassaMovement.direction == "in",
                KassaMovement.currency == currency
            ).scalar() or 0
            
            expense = db.query(func.sum(KassaMovement.amount)).filter(
                KassaMovement.wallet_id == wallet_id,
                KassaMovement.payment_type == ptype,
                KassaMovement.direction == "out",
                KassaMovement.currency == currency
            ).scalar() or 0
            
            balance = float(income) - float(expense)
            if balance != 0:
                currency_balances.append({"currency": currency, "value": balance})
        
        result[ptype] = currency_balances
    
    # Total hisoblash (barcha valyutalar bo'yicha alohida)
    total = {}
    for ptype in PAYMENT_TYPES:
        for item in result[ptype]:
            curr = item["currency"]
            total[curr] = total.get(curr, 0) + item["value"]
    
    result["total"] = [{"currency": k, "value": v} for k, v in total.items() if v != 0]
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


# ─── Foydalanuvchi ↔ Kassa ───────────────────────────────────────────────────

@router.get("/user-wallets")
def get_user_wallets(
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Berilgan foydalanuvchiga biriktirilgan kassalar ro'yxati (Admin)"""
    _sa_text = __import__('sqlalchemy').text
    rows = db.execute(
        _sa_text("SELECT wallet_id, is_default FROM user_wallets WHERE user_id=:uid"),
        {"uid": user_id}
    ).fetchall()
    if not rows:
        return []
    wallet_ids = [int(r[0]) for r in rows]
    defaults = {int(r[0]): bool(r[1]) for r in rows}
    wallets = db.query(Wallet).filter(
        Wallet.id.in_(wallet_ids),
        Wallet.company_id == current_user.company_id
    ).all()
    return [
        {"id": w.id, "name": w.name, "type": w.type,
         "is_default": defaults.get(w.id, False),
         "balance_total": get_kassa_balances(w.id, db).get("total", [])}
        for w in wallets
    ]


class AssignWalletIn(BaseModel):
    user_id: int
    wallet_id: int
    is_default: bool = False


@router.post("/assign-wallet")
def assign_wallet(data: AssignWalletIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Foydalanuvchiga kassa biriktirish (Admin)"""
    _sa_text = __import__('sqlalchemy').text
    # Wallet company tekshiruvi
    w = db.query(Wallet).filter(Wallet.id == data.wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    db.execute(
        _sa_text("""INSERT INTO user_wallets(user_id, wallet_id, is_default)
                    VALUES(:uid, :wid, :def)
                    ON CONFLICT(user_id, wallet_id) DO UPDATE SET is_default=EXCLUDED.is_default"""),
        {"uid": data.user_id, "wid": data.wallet_id, "def": data.is_default}
    )
    db.commit()
    return {"ok": True}


@router.delete("/assign-wallet")
def remove_wallet(user_id: int, wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Foydalanuvchidan kassani olib tashlash"""
    _sa_text = __import__('sqlalchemy').text
    db.execute(
        _sa_text("DELETE FROM user_wallets WHERE user_id=:uid AND wallet_id=:wid"),
        {"uid": user_id, "wid": wallet_id}
    )
    db.commit()
    return {"ok": True}


# ─── Xarajat kategoriyalari (FIXED PATHS — oldin yoziladi!) ──────────────────

@router.get("/categories")
def list_expense_categories(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    cats = db.query(ExpenseCategory).filter(
        (ExpenseCategory.company_id == current_user.company_id) | (ExpenseCategory.company_id == None)
    ).order_by(ExpenseCategory.name).all()
    return [{"id": c.id, "name": c.name, "description": c.description} for c in cats]


@router.post("/categories")
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


@router.post("/do-expense")
def create_expense(data: ExpenseCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == data.wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if data.amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")
    from app.models.branch import Branch as _Branch
    branch = db.query(_Branch).filter(_Branch.company_id == current_user.company_id).first()
    branch_id = current_user.branch_id or (branch.id if branch else 0)
    exp = Expense(branch_id=branch_id, category_id=data.category_id, amount=data.amount,
        company_id=current_user.company_id, wallet_id=data.wallet_id,
        description=data.description, approved_by=current_user.id)
    db.add(exp)
    db.flush()
    session = db.query(KassaSession).filter(KassaSession.wallet_id == data.wallet_id, KassaSession.status == "open").first()
    cat = db.get(ExpenseCategory, data.category_id)
    mv = KassaMovement(wallet_id=data.wallet_id, company_id=current_user.company_id,
        session_id=session.id if session else None, direction="out",
        payment_type=data.payment_type, amount=data.amount, currency=data.currency,
        reference_type="expense",
        reference_id=exp.id, description=data.description or (cat.name if cat else "Xarajat"),
        created_by=current_user.id)
    db.add(mv)
    tx = Transaction(company_id=current_user.company_id, branch_id=branch_id,
        wallet_id=data.wallet_id, type="expense", amount=data.amount,
        payment_type=data.payment_type, reference_type="expense",
        reference_id=exp.id, description=data.description or (cat.name if cat else "Xarajat"))
    db.add(tx)
    w.balance = float(w.balance or 0) - data.amount
    db.commit()
    return {"ok": True, "expense_id": exp.id}


@router.put("/expense/{expense_id}")
def update_expense(expense_id: int, data: ExpenseUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    exp = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not exp:
        raise HTTPException(404, "Xarajat topilmadi")

    w = db.query(Wallet).filter(Wallet.id == exp.wallet_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")

    # Revert old amount from wallet balance
    w.balance = float(w.balance or 0) + float(exp.amount)

    # Update Expense fields
    if data.category_id is not None:
        exp.category_id = data.category_id
    if data.amount is not None:
        if data.amount <= 0:
            raise HTTPException(400, "Summa musbat bo'lishi kerak")
        exp.amount = data.amount
    if data.description is not None:
        exp.description = data.description

    # Find category name for description fallback
    cat_name = "Xarajat"
    if exp.category_id:
        cat = db.get(ExpenseCategory, exp.category_id)
        if cat:
            cat_name = cat.name

    desc = exp.description or cat_name

    # Apply new amount to wallet balance
    w.balance = float(w.balance or 0) - float(exp.amount)

    # Update related KassaMovement
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense", KassaMovement.reference_id == exp.id).first()
    if mv:
        if data.amount is not None:
            mv.amount = exp.amount
        if data.payment_type is not None:
            mv.payment_type = data.payment_type
        if data.currency is not None:
            mv.currency = data.currency
        mv.description = desc

    # Update related Transaction
    tx = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == exp.id).first()
    if tx:
        if data.amount is not None:
            tx.amount = exp.amount
        if data.payment_type is not None:
            tx.payment_type = data.payment_type
        tx.description = desc

    db.commit()
    return {"ok": True, "message": "Xarajat yangilandi"}


@router.delete("/expense/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    exp = db.query(Expense).filter(Expense.id == expense_id, Expense.company_id == current_user.company_id).first()
    if not exp:
        raise HTTPException(404, "Xarajat topilmadi")

    w = db.query(Wallet).filter(Wallet.id == exp.wallet_id).first()
    if w:
        # Revert expense amount to wallet balance
        w.balance = float(w.balance or 0) + float(exp.amount)

    # Delete related KassaMovement
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense", KassaMovement.reference_id == exp.id).first()
    if mv:
        db.delete(mv)

    # Delete related Transaction
    tx = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == exp.id).first()
    if tx:
        db.delete(tx)

    db.delete(exp)
    db.commit()
    return {"ok": True, "message": "Xarajat o'chirildi"}


# ─── Kassa O'tkazmalari (Transfers) ──────────────────────────────────────────

@router.post("/{wallet_id}/transfer/out")
def transfer_out(
    wallet_id: int, 
    data: TransferOutIn, 
    db: Session = Depends(get_db), 
    current_user=Depends(get_current_user)
):
    """Qat'iy 2-bosqichli transfer: Pul yuborish (Pending)"""
    sender = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    receiver = db.query(Wallet).filter(Wallet.id == data.receiver_wallet_id, Wallet.company_id == current_user.company_id).first()
    
    if not sender or not receiver:
        raise HTTPException(404, "Kassa topilmadi")
    if not sender.is_open:
        raise HTTPException(400, "Yuboruvchi kassa yopiq")
        
    session = db.query(KassaSession).filter(KassaSession.wallet_id == sender.id, KassaSession.status == "open").first()
    
    # 1. Yuboruvchidan pul yechiladi (KassaMovement)
    mv_out = KassaMovement(
        wallet_id=sender.id,
        company_id=current_user.company_id,
        session_id=session.id if session else None,
        direction="out",
        payment_type=data.payment_type,
        amount=data.amount,
        currency=data.currency,
        reference_type="transfer_out",
        description=f"Transfer to {receiver.name}: {data.note or ''}",
        created_by=current_user.id,
    )
    db.add(mv_out)
    
    if data.currency == "UZS":
        sender.balance = float(sender.balance or 0) - data.amount
        
    # 2. Qabul qiluvchiga pul qo'shiladi (KassaMovement)
    receiver_session = db.query(KassaSession).filter(KassaSession.wallet_id == receiver.id, KassaSession.status == "open").first()
    
    mv_in = KassaMovement(
        wallet_id=receiver.id,
        company_id=current_user.company_id,
        session_id=receiver_session.id if receiver_session else None,
        direction="in",
        payment_type=data.payment_type,
        amount=data.amount,
        currency=data.currency,
        reference_type="transfer_in",
        description=f"Transfer from {sender.name}: {data.note or ''}",
        created_by=current_user.id,
    )
    db.add(mv_in)
    
    if data.currency == "UZS":
        receiver.balance = float(receiver.balance or 0) + data.amount

    # 3. CashTransfer tarixi yozuvi
    ct = CashTransfer(
        company_id=current_user.company_id,
        sender_wallet_id=sender.id,
        receiver_wallet_id=receiver.id,
        amount=data.amount,
        currency=data.currency,
        payment_type=data.payment_type,
        status="completed", # Avtomatik qabul qilingan hisoblanadi
        sent_by=current_user.id,
        received_by=current_user.id,
        received_at=datetime.now(timezone.utc),
        note=data.note
    )
    db.add(ct)
    
    # reference_id ni bog'lash
    db.flush()
    mv_out.reference_id = ct.id
    mv_in.reference_id = ct.id
    
    db.commit()
    db.refresh(ct)
    return {"ok": True, "transfer_id": ct.id}

@router.post("/transfer/in")
def transfer_in(
    data: TransferStatusIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Transfer qabul qilish"""
    ct = db.query(CashTransfer).filter(CashTransfer.id == data.transfer_id, CashTransfer.company_id == current_user.company_id).first()
    if not ct or ct.status != "pending":
        raise HTTPException(400, "Transfer topilmadi yoki allaqachon bajarilgan")
        
    receiver = db.query(Wallet).filter(Wallet.id == ct.receiver_wallet_id).first()
    if not receiver or not receiver.is_open:
        raise HTTPException(400, "Qabul qiluvchi kassa yopiq")
        
    session = db.query(KassaSession).filter(KassaSession.wallet_id == receiver.id, KassaSession.status == "open").first()
    
    # 1. Transfer holatini o'zgartirish
    ct.status = "completed"
    ct.received_by = current_user.id
    ct.received_at = datetime.now(timezone.utc)
    
    # 2. Qabul qiluvchiga KassaMovement
    mv = KassaMovement(
        wallet_id=receiver.id,
        company_id=current_user.company_id,
        session_id=session.id if session else None,
        direction="in",
        payment_type=ct.payment_type,
        amount=ct.amount,
        currency=ct.currency,
        reference_type="transfer_in",
        reference_id=ct.id,
        description=f"Transfer from {ct.sender_wallet.name}: {ct.note or ''}",
        created_by=current_user.id,
    )
    db.add(mv)
    
    if ct.currency == "UZS":
        receiver.balance = float(receiver.balance or 0) + float(ct.amount)
        
    db.commit()
    return {"ok": True}

@router.post("/transfer/reject")
def transfer_reject(
    data: TransferStatusIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Transferni bekor qilish va pulni yuboruvchiga qaytarish"""
    ct = db.query(CashTransfer).filter(CashTransfer.id == data.transfer_id, CashTransfer.company_id == current_user.company_id).first()
    if not ct or ct.status != "pending":
        raise HTTPException(400, "Transfer topilmadi yoki allaqachon bajarilgan")
        
    sender = db.query(Wallet).filter(Wallet.id == ct.sender_wallet_id).first()
    session = db.query(KassaSession).filter(KassaSession.wallet_id == sender.id, KassaSession.status == "open").first()
    
    ct.status = "rejected"
    ct.received_by = current_user.id
    ct.received_at = datetime.now(timezone.utc)
    
    # Pulni orqaga qaytarish (refund)
    mv = KassaMovement(
        wallet_id=sender.id,
        company_id=current_user.company_id,
        session_id=session.id if session else None,
        direction="in",
        payment_type=ct.payment_type,
        amount=ct.amount,
        currency=ct.currency,
        reference_type="transfer_rejected",
        reference_id=ct.id,
        description=f"Transfer bekor qilindi, qaytarildi",
        created_by=current_user.id,
    )
    db.add(mv)
    
    if ct.currency == "UZS":
        sender.balance = float(sender.balance or 0) + float(ct.amount)
        
    db.commit()
    return {"ok": True}


# ─── X-Report (Oraliq Hisobot) ───────────────────────────────────────────────

@router.get("/{wallet_id}/x-report")
def get_x_report(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Kassani yopmasdan kutilayotgan qoldiqni ko'rish (faqat menejer uchun)"""
    # Eslatma: Rol tekshiruvlarini qo'shish tavsiya etiladi (masalan: user.role == 'manager')
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    if not w.is_open:
        raise HTTPException(400, "Kassa yopiq")
        
    session = db.query(KassaSession).filter(KassaSession.wallet_id == wallet_id, KassaSession.status == "open").first()
    calculated = get_kassa_balances(wallet_id, db)
    
    return {
        "wallet_name": w.name,
        "opened_at": session.opened_at if session else None,
        "calculated_balances": calculated
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
            currency=data.currency,
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
            currency=data.currency,
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

    calculated = get_kassa_balances(wallet_id, db)
    now = datetime.now(timezone.utc)

    session = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet_id,
        KassaSession.status == "open"
    ).first()

    # actual_amounts — foydalanuvchi haqiqatda sanab bergan summa (Blind Close).
    # { "cash": {"UZS": 1000, "USD": 50}, "card": {"UZS": 5000} }
    diff_summary = {}

    for ptype in PAYMENT_TYPES:
        ptype_diffs = {}
        calc_list = calculated.get(ptype, [])
        calc_map = {item["currency"]: float(item["value"]) for item in calc_list} if isinstance(calc_list, list) else {}
        
        act_map = data.actual_amounts.get(ptype, {})
        if not isinstance(act_map, dict):
            # Backward compatibility agar eski client oddiy raqam yuborsa
            act_map = {"UZS": float(act_map)} if act_map else {}

        all_currencies = set(calc_map.keys()).union(act_map.keys())
        
        for curr in all_currencies:
            c_val = calc_map.get(curr, 0.0)
            a_val = float(act_map.get(curr, 0.0))
            diff = c_val - a_val   # diff > 0 -> kam topildi -> out harakati

            # 1. Kassir sanab bergan pulni "inkasso" sifatida kassa balansidan chiqarish
            if a_val > 0:
                mv_inkasso = KassaMovement(
                    wallet_id=wallet_id,
                    company_id=current_user.company_id,
                    session_id=session.id if session else None,
                    direction="out",
                    payment_type=ptype,
                    amount=a_val,
                    currency=curr,
                    reference_type="closing_inkasso",
                    description=f"Yopilish (inkasso, {curr}): {a_val}",
                    created_by=current_user.id,
                )
                db.add(mv_inkasso)
                if curr == "UZS":
                    w.balance = float(w.balance or 0) - a_val

            # 2. Farqni (kamomad yoki ortiqcha) adjustment sifatida yozish
            if abs(diff) >= 0.01:
                ptype_diffs[curr] = diff
                direction = "out" if diff > 0 else "in"
                
                mv_adj = KassaMovement(
                    wallet_id=wallet_id,
                    company_id=current_user.company_id,
                    session_id=session.id if session else None,
                    direction=direction,
                    payment_type=ptype,
                    amount=abs(diff),
                    currency=curr,
                    reference_type="closing_adjustment",
                    description=f"Yopilish farqi ({ptype}, {curr}): kutilgan={c_val}, haqiqiy={a_val}",
                    created_by=current_user.id,
                )
                db.add(mv_adj)
                
                if curr == "UZS":
                    w.balance = float(w.balance or 0) + (-diff) # Agar kamomad bo'lsa (diff>0) ayiramiz, aks holda qo'shamiz
        
        if ptype_diffs:
            diff_summary[ptype] = ptype_diffs

    # Sessionni yopish
    if session:
        session.closed_at = now
        session.closed_by = current_user.id
        session.status = "closed"
        session.closing_summary = {
            "calculated": calculated,
            "actual": data.actual_amounts,
            "note": data.note,
        }

    w.is_open = False
    w.closed_at = now
    w.closed_by = current_user.id

    db.commit()

    final_balances = get_kassa_balances(wallet_id, db)
    return {
        "ok": True,
        "closed_at": now,
        "calculated_balances": calculated,
        "actual_amounts": data.actual_amounts,
        "final_balances": final_balances,
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
        currency=data.currency,
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
    # Balansni valyuta bo'yicha tekshirish
    payment_type_balances = balances.get(data.payment_type, [])
    currency_balance = 0
    for item in payment_type_balances:
        if item["currency"] == data.currency:
            currency_balance = item["value"]
            break
    if currency_balance < data.amount:
        raise HTTPException(400, f"{data.payment_type} ({data.currency}) bo'yicha balans yetarli emas")

    session = db.query(KassaSession).filter(KassaSession.wallet_id == wallet_id, KassaSession.status == "open").first()

    mv = KassaMovement(
        wallet_id=wallet_id,
        company_id=current_user.company_id,
        session_id=session.id if session else None,
        direction="out",
        payment_type=data.payment_type,
        amount=data.amount,
        currency=data.currency,
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
                "currency": m.currency,
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


# (Expense endpoints moved above — before /{wallet_id} routes)


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
