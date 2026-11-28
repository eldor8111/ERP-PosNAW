"""R5.0: E-Code POS Restoran (desktop) oflayn API.

GET  /restaurant/offline/bootstrap?branch_id — oflayn ishlash uchun barcha ma'lumot (menyu, zallar, qo'shimchalar,
                                               stop-list, ochiq cheklar, rekvizitlar, ruxsatlar)
POST /restaurant/offline/sync                — bitta oflayn amal ({branch_id, device, op}); idempotent (`op.op_id`)

Ruxsat: cheklar bilan ishlash (`orders`); to'lov bo'lsa `take_payment` (pay_order tekshiradi).
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user
from app.core.features import require_restaurant
from app.database import get_db
from app.models.user import User
from app.services import restaurant_offline as off
from app.services import restaurant_orders as svc

router = APIRouter(prefix="/restaurant/offline", tags=["Restoran: oflayn (desktop)"],
                   dependencies=[Depends(require_restaurant)])


class OfflineItem(BaseModel):
    product_id: int
    quantity: float = 1
    unit_price: Optional[float] = None
    modifiers: Optional[List[int]] = None
    comment: Optional[str] = None
    course: int = 1
    guest_no: Optional[int] = None
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None


class OfflinePayRow(BaseModel):
    type: str
    amount: float
    reference: Optional[str] = None


class OfflinePayment(BaseModel):
    payments: List[OfflinePayRow] = []
    tips: float = 0
    paid_at: Optional[datetime] = None
    fiscal: Optional[dict] = None


class OfflineSendItem(BaseModel):
    id: int
    sent_at: Optional[datetime] = None


class OfflineCancel(BaseModel):
    reason: Optional[str] = None


class OfflineOp(BaseModel):
    op_id: str = Field(..., min_length=8, max_length=64)
    order_uuid: Optional[str] = Field(None, max_length=40)
    server_id: Optional[int] = None
    offline_no: Optional[str] = Field(None, max_length=20)
    order_type: str = "dine_in"
    table_id: Optional[int] = None
    guests: Optional[int] = None
    comment: Optional[str] = None
    opened_at: Optional[datetime] = None
    items: List[OfflineItem] = []
    send_items: List[OfflineSendItem] = []
    precheck_at: Optional[datetime] = None
    payment: Optional[OfflinePayment] = None
    cancel: Optional[OfflineCancel] = None


class SyncIn(BaseModel):
    branch_id: Optional[int] = None
    device: Optional[str] = None
    op: OfflineOp


def _ctx(db: Session, user: User):
    settings = svc.settings_for(db, user.company_id)
    if not svc.rest_perms(user, settings).get("orders"):
        raise HTTPException(status_code=403, detail="Cheklar bilan ishlashga ruxsat yo'q")
    return settings


@router.get("/bootstrap")
def get_bootstrap(branch_id: Optional[int] = None, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                  ctx: BranchContext = Depends(get_branch_context)):
    settings = _ctx(db, user)
    bid = svc.branch_for(db, user, ctx, branch_id)
    return off.bootstrap(db, user, bid, settings)


@router.post("/sync")
def sync(payload: SyncIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
         ctx: BranchContext = Depends(get_branch_context)):
    settings = _ctx(db, user)
    bid = svc.branch_for(db, user, ctx, payload.branch_id)
    # Xato bo'lsa commit qilinmaydi (so'rov sessiyasi yopilganda bekor bo'ladi); to'lov create_sale ichida commit
    # qilinadi — javob qurilmaga yetmasa qayta yuborilgan amal "to'lov avval yozilgan" deb qaytadi.
    result = off.apply_op(db, user, settings, bid, payload.op.model_dump(), device=payload.device)
    db.commit()
    return result
