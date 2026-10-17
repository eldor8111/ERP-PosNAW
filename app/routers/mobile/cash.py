"""Dala xodimining qo'l kassasi: balans, bugungi harakatlar, kassaga topshirish."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.branch_context import effective_branch_id
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.moliya import CashTransfer, KassaMovement
from app.models.user import User
from app.services.mobile_service import (
    cancel_handover, ensure_personal_wallet, handover_cash, idem_get, idem_put, personal_cash_balance,
    receivable_wallets,
)

router = APIRouter(prefix="/mobile/cash", tags=["mobile-cash"])


@router.get("")
def my_cash(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    w = ensure_personal_wallet(db, current_user)
    since = datetime.now(timezone.utc) - timedelta(days=2)
    moves = db.query(KassaMovement).filter(
        KassaMovement.wallet_id == w.id, KassaMovement.created_at >= since,
    ).order_by(KassaMovement.id.desc()).limit(50).all()
    pending = db.query(CashTransfer).filter(
        CashTransfer.sender_wallet_id == w.id, CashTransfer.status == "pending",
    ).all()
    # T3.14: qabul qiluvchi kassalar filial nomi va ochiq/yopiq holati bilan
    rwallets = receivable_wallets(db, current_user)
    out = {
        # Qo'ldagi NAQD pul (karta tushumi hisobga olinmaydi)
        "balance": float(personal_cash_balance(db, w)),
        # Xodimning o'z filiali: ilova boshqa filial kassasiga topshirishda tasdiq so'rashi uchun
        "own_branch_id": effective_branch_id(db, current_user),
        "movements": [
            {"id": m.id, "direction": m.direction, "amount": float(m.amount), "payment_type": m.payment_type,
             "description": m.description, "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in moves
        ],
        "pending_handovers": [{"id": t.id, "amount": float(t.amount), "receiver": t.receiver_wallet.name if t.receiver_wallet else None} for t in pending],
        "wallets": [
            {"id": x.id, "name": x.name, "branch_id": x.branch_id,
             "branch_name": x.branch.name if x.branch else None, "is_open": bool(x.is_open)}
            for x in rwallets
        ],
    }
    db.commit()
    return out


class HandoverIn(BaseModel):
    wallet_id: int
    amount: Decimal = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=200)
    confirm_other_branch: bool = False  # T3.14: boshqa filial kassasiga topshirishni tasdiqlash


@router.post("/handover")
def handover(data: HandoverIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
             idempotency_key: Optional[str] = Header(None)):
    prev = idem_get(db, current_user, idempotency_key)
    if prev is not None:
        return prev
    ct = handover_cash(db, current_user, data.wallet_id, data.amount, data.note,
                       confirm_other_branch=data.confirm_other_branch)
    out = {"transfer_id": ct.id, "status": ct.status,
           "balance": float(personal_cash_balance(db, ensure_personal_wallet(db, current_user)))}
    idem_put(db, current_user, idempotency_key, "cash/handover", out)
    db.commit()
    return out


@router.post("/handover/{transfer_id}/cancel")
def cancel_my_handover(transfer_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """O'z `pending` topshirig'ini bekor qilish — summa qo'l kassasiga qaytadi (T3.14)."""
    cancel_handover(db, current_user, transfer_id)
    out = {"transfer_id": transfer_id, "status": "rejected",
           "balance": float(personal_cash_balance(db, ensure_personal_wallet(db, current_user)))}
    db.commit()
    return out
