"""Stol bron qilish API (R8.1).

GET  /restaurant/reservations?branch_id&date=YYYY-MM-DD[&days=N]  — kun (yoki N kun) bronlari, stollar bilan
GET  /restaurant/reservations/free-tables?branch_id&starts_at&duration_min[&exclude_id] — shu vaqtda bo'sh stollar
POST /restaurant/reservations                                     — yangi bron (+ ixtiyoriy depozit)
PUT  /restaurant/reservations/{id}                                — o'zgartirish (vaqt, stol, mehmon, mijoz)
POST /restaurant/reservations/{id}/deposit                        — depozit olish {amount, type}
POST /restaurant/reservations/{id}/arrive                         — mehmon keldi (chek ochiladi)
POST /restaurant/reservations/{id}/no-show                        — kelmadi (depozit qoladi)
POST /restaurant/reservations/{id}/cancel                         — bekor qilish {reason, refund_deposit}
POST /restaurant/reservations/{id}/refund-deposit                 — ishlatilmagan depozitni qaytarish

Bron bilan ishlash: cheklar ruxsati (`orders`). Depozit olish va qaytarish: to'lov ruxsati (`take_payment`).
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user
from app.core.features import require_restaurant, require_restaurant_feature
from app.database import get_db
from app.models.restaurant import Hall, RestaurantTable
from app.models.user import User
from app.services import restaurant_orders as svc
from app.services import restaurant_reservations as rsv

router = APIRouter(prefix="/restaurant/reservations", tags=["Restoran: bron"],
                   dependencies=[Depends(require_restaurant), Depends(require_restaurant_feature("reservations"))])


class ReservationIn(BaseModel):
    branch_id: Optional[int] = None
    table_ids: Optional[List[int]] = None
    starts_at: Optional[str] = None
    duration_min: Optional[int] = None
    guests: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    note: Optional[str] = None
    customer_id: Optional[int] = None
    deposit_amount: Optional[float] = None
    deposit_type: Optional[str] = None


class DepositIn(BaseModel):
    amount: float
    type: str = "cash"


class CancelIn(BaseModel):
    reason: Optional[str] = None
    refund_deposit: bool = True


class ArriveIn(BaseModel):
    open_check: bool = True


def _perms(db: Session, user: User):
    settings = svc.settings_for(db, user.company_id)
    perms = svc.rest_perms(user, settings)
    if not perms.get("orders"):
        raise HTTPException(status_code=403, detail="Bron bilan ishlashga ruxsat yo'q")
    return perms, settings


def _need_pay(perms: dict):
    if not perms.get("take_payment"):
        raise HTTPException(status_code=403, detail="Depozit olish yoki qaytarishga ruxsat yo'q")


def _res(db: Session, user: User, ctx: BranchContext, rid: int, lock: bool = True):
    r = rsv.get(db, user.company_id, rid, lock=lock)
    if ctx.allowed_branch_ids is not None and r.branch_id not in ctx.allowed_branch_ids:
        raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
    return r


def _one(db: Session, r) -> dict:
    from app.models.user import User as U
    names = rsv.table_names(db, r.company_id, r.table_ids or [])
    u = db.get(U, r.created_by) if r.created_by else None
    return rsv.out(r, names, {r.created_by: u.name} if u else None)


def _audit(db: Session, user: User, action: str, r, extra: Optional[dict] = None):
    vals = {"branch_id": r.branch_id, "status": r.status, "name": r.name, "starts_at": rsv.iso(r.starts_at),
            "table_ids": r.table_ids}
    if extra:
        vals.update(extra)
    log_action(db=db, action=action, entity_type="reservation", entity_id=r.id, user_id=user.id, new_values=vals)


@router.get("")
def list_reservations(branch_id: Optional[int] = None, day: Optional[date] = Query(None, alias="date"),
                      days: int = Query(1, ge=1, le=31), db: Session = Depends(get_db),
                      user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    perms, settings = _perms(db, user)
    bid = svc.branch_for(db, user, ctx, branch_id)
    from app.utils.report_utils import local_today
    day = day or local_today()
    start, _ = rsv.local_day_bounds(day)
    _, end = rsv.local_day_bounds(day + timedelta(days=days - 1))
    rows = rsv.list_range(db, user.company_id, bid, start, end)
    from app.models.user import User as U
    names = rsv.table_names(db, user.company_id, {t for r in rows for t in (r.table_ids or [])})
    uids = {r.created_by for r in rows if r.created_by}
    unames = {u.id: u.name for u in db.query(U).filter(U.id.in_(list(uids)))} if uids else {}
    tables = (db.query(RestaurantTable, Hall.name).join(Hall, Hall.id == RestaurantTable.hall_id)
              .filter(Hall.branch_id == bid, Hall.company_id == user.company_id, Hall.is_active == True,  # noqa: E712
                      RestaurantTable.is_active == True)  # noqa: E712
              .order_by(Hall.sort_order, Hall.id, RestaurantTable.id).all())
    return {
        "branch_id": bid, "date": day.isoformat(), "days": days,
        "default_duration_min": settings.get("reservation_duration_min", 120),
        "can_take_payment": bool(perms.get("take_payment")),
        "tables": [{"id": t.id, "name": t.name, "seats": t.seats, "hall_id": t.hall_id, "hall_name": hn}
                   for t, hn in tables],
        "items": [rsv.out(r, names, unames) for r in rows],
    }


@router.get("/free-tables")
def free_tables(starts_at: str, duration_min: Optional[int] = None, branch_id: Optional[int] = None,
                exclude_id: Optional[int] = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    _, settings = _perms(db, user)
    bid = svc.branch_for(db, user, ctx, branch_id)
    start = rsv.parse_dt(starts_at)
    dur = int(duration_min or settings.get("reservation_duration_min", 120))
    end = start + timedelta(minutes=max(15, min(dur, 720)))
    tables = (db.query(RestaurantTable.id).join(Hall, Hall.id == RestaurantTable.hall_id)
              .filter(Hall.branch_id == bid, Hall.company_id == user.company_id, RestaurantTable.is_active == True)  # noqa: E712
              .all())
    ids = [t[0] for t in tables]
    busy = set()
    for r in rsv.conflicts(db, user.company_id, bid, ids, start, end, exclude_id):
        busy |= {int(x) for x in r.table_ids or []}
    return {"free": [i for i in ids if i not in busy], "busy": sorted(busy)}


@router.post("", status_code=201)
def create_reservation(payload: ReservationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                       ctx: BranchContext = Depends(get_branch_context)):
    perms, settings = _perms(db, user)
    bid = svc.branch_for(db, user, ctx, payload.branch_id)
    data = payload.model_dump()
    deposit = data.pop("deposit_amount", None)
    dtype = data.pop("deposit_type", None) or "cash"
    if deposit:
        _need_pay(perms)
    r = rsv.create(db, user, settings, bid, data)
    if deposit:
        rsv.take_deposit(db, user, r, deposit, dtype)
    _audit(db, user, "RESERVATION_CREATE", r, {"guests": r.guests, "deposit": float(r.deposit_amount or 0)})
    db.commit()
    return _one(db, r)


@router.put("/{rid}")
def update_reservation(rid: int, payload: ReservationIn, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    _, settings = _perms(db, user)
    r = _res(db, user, ctx, rid)
    data = payload.model_dump(exclude_unset=True)
    data.pop("branch_id", None)
    data.pop("deposit_amount", None)
    data.pop("deposit_type", None)
    rsv.update(db, user, settings, r, data)
    _audit(db, user, "RESERVATION_UPDATE", r)
    db.commit()
    return _one(db, r)


@router.post("/{rid}/deposit")
def take_deposit(rid: int, payload: DepositIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 ctx: BranchContext = Depends(get_branch_context)):
    perms, _ = _perms(db, user)
    _need_pay(perms)
    r = _res(db, user, ctx, rid)
    rsv.take_deposit(db, user, r, payload.amount, payload.type)
    _audit(db, user, "RESERVATION_DEPOSIT", r, {"amount": float(r.deposit_amount), "type": r.deposit_type})
    db.commit()
    return _one(db, r)


@router.post("/{rid}/arrive")
def arrive(rid: int, payload: Optional[ArriveIn] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    _, settings = _perms(db, user)
    r = _res(db, user, ctx, rid)
    order = rsv.arrive(db, user, settings, r, open_check=(payload.open_check if payload else True))
    _audit(db, user, "RESERVATION_ARRIVED", r, {"order_id": order.id if order else None})
    db.commit()
    return _one(db, r)


@router.post("/{rid}/no-show")
def no_show(rid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
            ctx: BranchContext = Depends(get_branch_context)):
    _perms(db, user)
    r = _res(db, user, ctx, rid)
    rsv.no_show(db, user, r)
    _audit(db, user, "RESERVATION_NO_SHOW", r, {"deposit_retained": float(r.deposit_amount or 0)
                                                if r.deposit_status == "retained" else 0})
    db.commit()
    return _one(db, r)


@router.post("/{rid}/cancel")
def cancel(rid: int, payload: Optional[CancelIn] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    perms, _ = _perms(db, user)
    payload = payload or CancelIn()
    r = _res(db, user, ctx, rid)
    if payload.refund_deposit and rsv.held_amount(r) > 0:
        _need_pay(perms)
    back = rsv.cancel(db, user, r, payload.reason, payload.refund_deposit)
    _audit(db, user, "RESERVATION_CANCEL", r, {"reason": r.cancel_reason, "refunded": float(back)})
    db.commit()
    out = _one(db, r)
    out["refunded"] = float(back)
    return out


@router.post("/{rid}/refund-deposit")
def refund_deposit(rid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                   ctx: BranchContext = Depends(get_branch_context)):
    perms, _ = _perms(db, user)
    _need_pay(perms)
    r = _res(db, user, ctx, rid)
    if r.status == "booked":
        raise HTTPException(status_code=409, detail="Kutilayotgan bronni avval bekor qiling")
    back = rsv.refund_deposit(db, user, r)
    if back <= 0:
        raise HTTPException(status_code=409, detail="Qaytariladigan depozit yo'q")
    _audit(db, user, "RESERVATION_DEPOSIT_REFUND", r, {"refunded": float(back)})
    db.commit()
    out = _one(db, r)
    out["refunded"] = float(back)
    return out
