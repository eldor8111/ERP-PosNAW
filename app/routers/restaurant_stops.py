"""Stop-list API (R1.5).

GET    /restaurant/stop-list?branch_id          — qo'lda stoplar, hisoblagichlar, ingredient yetishmasligi,
                                                  hozir sotilmaydigan taomlar (buyurtma ekrani ham shundan oladi)
PUT    /restaurant/stop-list/{product_id}       — to'xtatish / hisoblagich ({branch_id, stopped, reason, until, remaining})
DELETE /restaurant/stop-list/{product_id}?branch_id — sotuvga qaytarish

Ko'rish: cheklar yoki oshxona ruxsati. O'zgartirish: oshxona ruxsati (oshpaz, menejer, direktor, admin).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user
from app.core.features import require_restaurant
from app.database import get_db
from app.models.product import Product
from app.models.user import User
from app.services import restaurant_orders as svc
from app.services import restaurant_stops as stops

router = APIRouter(prefix="/restaurant/stop-list", tags=["Stop-list"], dependencies=[Depends(require_restaurant)])


class StopIn(BaseModel):
    branch_id: Optional[int] = None
    stopped: bool = True
    reason: Optional[str] = None
    until: Optional[datetime] = None
    remaining: Optional[float] = None


def _perms(db: Session, user: User):
    settings = svc.settings_for(db, user.company_id)
    return svc.rest_perms(user, settings), settings


def _product(db: Session, user: User, product_id: int) -> Product:
    p = db.query(Product).filter(Product.id == product_id, Product.company_id == user.company_id,
                                 Product.is_deleted == False).first()  # noqa: E712
    if p is None:
        raise HTTPException(status_code=404, detail="Taom topilmadi")
    return p


@router.get("")
def get_stop_list(branch_id: Optional[int] = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    perms, settings = _perms(db, user)
    if not (perms.get("orders") or perms.get("kitchen")):
        raise HTTPException(status_code=403, detail="Stop-listni ko'rishga ruxsat yo'q")
    bid = svc.branch_for(db, user, ctx, branch_id)
    out = stops.status(db, user.company_id, bid, settings)
    out["branch_id"] = bid
    out["can_edit"] = bool(perms.get("kitchen"))
    return out


@router.put("/{product_id}")
def put_stop(product_id: int, payload: StopIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
             ctx: BranchContext = Depends(get_branch_context)):
    perms, _ = _perms(db, user)
    if not perms.get("kitchen"):
        raise HTTPException(status_code=403, detail="Stop-listni o'zgartirishga ruxsat yo'q")
    bid = svc.branch_for(db, user, ctx, payload.branch_id)
    p = _product(db, user, product_id)
    row = stops.upsert(db, user, user.company_id, bid, p, payload.model_dump())
    log_action(db=db, action="MENU_STOP" if row is not None and row.stopped else "MENU_STOP_UPDATE",
               entity_type="product", entity_id=p.id, user_id=user.id,
               new_values={"branch_id": bid, "stopped": bool(row and row.stopped), "reason": row.reason if row else None,
                           "until": row.until.isoformat() if row and row.until else None,
                           "remaining": float(row.remaining) if row and row.remaining is not None else None})
    db.commit()
    return {"ok": True, "product_id": p.id, "active": row is not None}


@router.delete("/{product_id}")
def delete_stop(product_id: int, branch_id: Optional[int] = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    perms, _ = _perms(db, user)
    if not perms.get("kitchen"):
        raise HTTPException(status_code=403, detail="Stop-listni o'zgartirishga ruxsat yo'q")
    bid = svc.branch_for(db, user, ctx, branch_id)
    p = _product(db, user, product_id)
    stops.upsert(db, user, user.company_id, bid, p, {"stopped": False, "remaining": None})
    log_action(db=db, action="MENU_UNSTOP", entity_type="product", entity_id=p.id, user_id=user.id,
               new_values={"branch_id": bid})
    db.commit()
    return {"ok": True}
