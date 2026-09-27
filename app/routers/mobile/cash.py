"""Dala xodimining qo'l kassasi: balans, bugungi harakatlar, kassaga topshirish."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.moliya import CashTransfer, KassaMovement
from app.models.user import User
from app.services.mobile_service import ensure_personal_wallet, handover_cash, idem_get, idem_put, receivable_wallets

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
    out = {
        "balance": float(w.balance or 0),
        "movements": [
            {"id": m.id, "direction": m.direction, "amount": float(m.amount), "payment_type": m.payment_type,
             "description": m.description, "created_at": m.created_at.isoformat() if m.created_at else None}
            for m in moves
        ],
        "pending_handovers": [{"id": t.id, "amount": float(t.amount), "receiver": t.receiver_wallet.name if t.receiver_wallet else None} for t in pending],
        "wallets": [{"id": x.id, "name": x.name} for x in receivable_wallets(db, current_user)],
    }
    db.commit()
    return out


class HandoverIn(BaseModel):
    wallet_id: int
    amount: Decimal = Field(..., gt=0)
    note: Optional[str] = Field(None, max_length=200)


@router.post("/handover")
def handover(data: HandoverIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
             idempotency_key: Optional[str] = Header(None)):
    prev = idem_get(db, current_user, idempotency_key)
    if prev is not None:
        return prev
    ct = handover_cash(db, current_user, data.wallet_id, data.amount, data.note)
    out = {"transfer_id": ct.id, "status": ct.status, "balance": float(ensure_personal_wallet(db, current_user).balance or 0)}
    idem_put(db, current_user, idempotency_key, "cash/handover", out)
    db.commit()
    return out
