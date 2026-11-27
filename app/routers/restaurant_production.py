"""Yarim tayyor mahsulot ishlab chiqarish API (R7.2).

GET  /restaurant/production/semis?branch_id              — yarim tayyorlar: karta, oshxonadagi qoldiq, tannarx
GET  /restaurant/production/plan?branch_id&product_id&quantity — kerakli xom ashyo va yetishmovchilik (yozmaydi)
POST /restaurant/production                              — tayyorlash {branch_id, product_id, quantity, note, force}
GET  /restaurant/production?branch_id&date_from&date_to  — tarix
GET  /restaurant/production/{id}?branch_id               — yozuv va yechilgan xom ashyo
POST /restaurant/production/{id}/cancel?branch_id        — bekor qilish (rahbarlar)

Tayyorlash: oshxona ruxsati (oshpaz, menejer, direktor, admin) yoki omborchi.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user
from app.core.features import require_restaurant
from app.database import get_db
from app.models.user import User, UserRole
from app.services import restaurant_orders as svc
from app.services import restaurant_production as prod

router = APIRouter(prefix="/restaurant/production", tags=["Restoran: tayyorlash"],
                   dependencies=[Depends(require_restaurant)])

VIEW_ROLES = (UserRole.warehouse, UserRole.accountant)
CANCEL_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager)


class ProduceIn(BaseModel):
    branch_id: Optional[int] = None
    product_id: int
    quantity: float
    note: Optional[str] = None
    force: bool = False


def _ctx(db: Session, user: User):
    settings = svc.settings_for(db, user.company_id)
    return svc.rest_perms(user, settings), settings


def _can_produce(user: User, perms: dict) -> bool:
    return bool(perms.get("kitchen")) or user.role == UserRole.warehouse


def _need_view(user: User, perms: dict):
    if not (_can_produce(user, perms) or user.role in VIEW_ROLES):
        raise HTTPException(status_code=403, detail="Tayyorlash bo'limiga ruxsat yo'q")


def _need_produce(user: User, perms: dict):
    if not _can_produce(user, perms):
        raise HTTPException(status_code=403, detail="Yarim tayyor mahsulot tayyorlashga ruxsat yo'q")


@router.get("/semis")
def list_semis(branch_id: Optional[int] = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    perms, _ = _ctx(db, user)
    _need_view(user, perms)
    bid = svc.branch_for(db, user, ctx, branch_id)
    return {"branch_id": bid, "items": prod.semis(db, user.company_id, bid),
            "can_produce": _can_produce(user, perms), "can_cancel": user.role in CANCEL_ROLES}


@router.get("/plan")
def get_plan(product_id: int, quantity: float, branch_id: Optional[int] = None, db: Session = Depends(get_db),
             user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    perms, settings = _ctx(db, user)
    _need_view(user, perms)
    bid = svc.branch_for(db, user, ctx, branch_id)
    return prod.plan_out(prod.plan(db, user.company_id, bid, product_id, quantity, settings))


@router.post("", status_code=201)
def produce(payload: ProduceIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
            ctx: BranchContext = Depends(get_branch_context)):
    perms, settings = _ctx(db, user)
    _need_produce(user, perms)
    bid = svc.branch_for(db, user, ctx, payload.branch_id)
    order = prod.produce(db, user, bid, payload.product_id, payload.quantity, settings,
                         note=payload.note, force=payload.force)
    log_action(db=db, action="REST_PRODUCE", entity_type="production_order", entity_id=order.id, user_id=user.id,
               new_values={"branch_id": bid, "number": order.number, "product_id": order.product_id,
                           "quantity": float(order.produced_quantity), "total_cost": float(order.total_cost or 0),
                           "forced": bool(payload.force)})
    db.commit()
    return _detail(db, user, bid, order.id)


def _detail(db: Session, user: User, bid: int, order_id: int) -> dict:
    return prod.detail(db, prod.get_order(db, user.company_id, bid, order_id))


@router.get("")
def list_history(branch_id: Optional[int] = None, date_from: Optional[date] = None, date_to: Optional[date] = None,
                 product_id: Optional[int] = None, limit: int = Query(100, ge=1, le=500),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 ctx: BranchContext = Depends(get_branch_context)):
    from app.utils.report_utils import _date_range
    perms, _ = _ctx(db, user)
    _need_view(user, perms)
    bid = svc.branch_for(db, user, ctx, branch_id)
    start = end = None
    if date_from or date_to:
        start, end = _date_range(date_from, date_to)
    return {"branch_id": bid, "items": prod.history(db, user.company_id, bid, date_from=start, date_to=end,
                                                    product_id=product_id, limit=limit)}


@router.get("/{order_id}")
def get_one(order_id: int, branch_id: Optional[int] = None, db: Session = Depends(get_db),
            user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    perms, _ = _ctx(db, user)
    _need_view(user, perms)
    bid = svc.branch_for(db, user, ctx, branch_id)
    return _detail(db, user, bid, order_id)


@router.post("/{order_id}/cancel")
def cancel(order_id: int, branch_id: Optional[int] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    if user.role not in CANCEL_ROLES:
        raise HTTPException(status_code=403, detail="Tayyorlashni bekor qilish faqat rahbarlarga ruxsat")
    bid = svc.branch_for(db, user, ctx, branch_id)
    o = prod.cancel(db, user, prod.get_order(db, user.company_id, bid, order_id))
    log_action(db=db, action="REST_PRODUCE_CANCEL", entity_type="production_order", entity_id=o.id, user_id=user.id,
               new_values={"branch_id": bid, "number": o.number, "product_id": o.product_id,
                           "quantity": float(o.produced_quantity or 0)})
    db.commit()
    return _detail(db, user, bid, o.id)
