"""Oshxona tiketlarini chop etish navbati (R4.1).

Tiketlar oshxonaga yuborishda va bekor qilishda `kitchen_tickets` ga yoziladi. Chop etuvchi qurilma
(brauzerdagi "Chop etish stansiyasi" sahifasi yoki keyinroq E-Code POS desktop) navbatni so'raydi va
tiketlarni `claim` bilan egallaydi: egallash atomar (`printed_at IS NULL` sharti bilan), shuning uchun bir sexni
ikki qurilma kuzatsa ham tiket bir marta chiqadi. Qog'oz tugasa yoki printer xato bersa — `reprint`.

GET  /restaurant/print/queue      — chop etilmagan tiketlar (filial, sex filtri; so'nggi 12 soat)
POST /restaurant/print/claim      — tiketlarni egallash, faqat egallanganlar qaytadi
POST /restaurant/print/{id}/reprint — qayta navbatga qo'yish
GET  /restaurant/print/recent     — so'nggi chop etilganlar (qayta chop etish uchun)
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user
from app.core.features import require_restaurant
from app.database import get_db
from app.models.restaurant import KitchenStation, RestaurantTable
from app.models.restaurant_order import KitchenTicket, RestaurantOrder
from app.models.user import User
from app.services import restaurant_orders as svc

router = APIRouter(prefix="/restaurant/print", tags=["Oshxona printeri"], dependencies=[Depends(require_restaurant)])

QUEUE_HOURS = 12


class ClaimIn(BaseModel):
    ticket_ids: List[int]


def _now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(d):
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _guard(db: Session, user: User):
    perms = svc.rest_perms(user, svc.settings_for(db, user.company_id))
    if not (perms.get("kitchen") or perms.get("orders")):
        raise HTTPException(status_code=403, detail="Chop etish navbatiga ruxsat yo'q")


def _branch(db: Session, user: User, ctx: BranchContext, branch_id: Optional[int]) -> int:
    return svc.branch_for(db, user, ctx, branch_id)


def _station_filter(q, db: Session, user: User, station: Optional[str]):
    if station in (None, "", "all"):
        return q
    if station == "none":
        return q.filter(KitchenTicket.station_id.is_(None))
    ids = []
    for part in station.split(","):
        try:
            sid = int(part)
        except ValueError:
            raise HTTPException(status_code=400, detail="Sex noto'g'ri")
        ids.append(sid)
    found = {s for (s,) in db.query(KitchenStation.id).filter(KitchenStation.id.in_(ids),
                                                              KitchenStation.company_id == user.company_id)}
    if found != set(ids):
        raise HTTPException(status_code=404, detail="Sex topilmadi")
    return q.filter(KitchenTicket.station_id.in_(ids))


def _out(db: Session, tickets: list) -> list:
    if not tickets:
        return []
    orders = {o.id: o for o in db.query(RestaurantOrder).filter(RestaurantOrder.id.in_({t.order_id for t in tickets}))}
    tables = {t.id: t.name for t in db.query(RestaurantTable).filter(
        RestaurantTable.id.in_({o.table_id for o in orders.values() if o.table_id} or {0}))}
    waiters = {u.id: u.name for u in db.query(User).filter(
        User.id.in_({o.waiter_id for o in orders.values() if o.waiter_id} or {0}))}
    stations = {s.id: s.name for s in db.query(KitchenStation).filter(
        KitchenStation.id.in_({t.station_id for t in tickets if t.station_id} or {0}))}
    out = []
    for t in tickets:
        o = orders.get(t.order_id)
        out.append({
            "id": t.id, "kind": t.kind, "station_id": t.station_id, "station_name": stations.get(t.station_id),
            "order_id": t.order_id, "daily_no": o.daily_no if o else None,
            "order_type": o.order_type if o else None, "table_name": tables.get(o.table_id) if o else None,
            "waiter_name": waiters.get(o.waiter_id) if o else None, "guests": o.guests if o else None,
            "lines": t.lines or [], "created_at": _iso(t.created_at), "printed_at": _iso(t.printed_at),
            "print_attempts": t.print_attempts or 0,
        })
    return out


@router.get("/queue")
def queue(branch_id: Optional[int] = None, station: Optional[str] = Query(None, description="id, 'id,id', 'none'"),
          db: Session = Depends(get_db), user: User = Depends(get_current_user),
          ctx: BranchContext = Depends(get_branch_context)):
    _guard(db, user)
    bid = _branch(db, user, ctx, branch_id)
    edge = _now_naive() - timedelta(hours=QUEUE_HOURS)
    q = db.query(KitchenTicket).filter(KitchenTicket.company_id == user.company_id, KitchenTicket.branch_id == bid,
                                       KitchenTicket.printed_at.is_(None), KitchenTicket.created_at >= edge)
    q = _station_filter(q, db, user, station)
    return _out(db, q.order_by(KitchenTicket.id).limit(100).all())


@router.post("/claim")
def claim(payload: ClaimIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
          ctx: BranchContext = Depends(get_branch_context)):
    """Atomar egallash: faqat hali hech kim egallamagan tiketlar shu so'rovga beriladi."""
    _guard(db, user)
    ids = list(dict.fromkeys(payload.ticket_ids or []))[:100]
    if not ids:
        return []
    now = _now_naive()
    q = db.query(KitchenTicket).filter(KitchenTicket.id.in_(ids), KitchenTicket.company_id == user.company_id,
                                       KitchenTicket.printed_at.is_(None))
    if ctx.allowed_branch_ids is not None:
        q = q.filter(KitchenTicket.branch_id.in_(ctx.allowed_branch_ids))
    candidates = [t.id for t in q.all()]
    claimed = []
    for tid in candidates:
        n = (db.query(KitchenTicket).filter(KitchenTicket.id == tid, KitchenTicket.printed_at.is_(None))
             .update({KitchenTicket.printed_at: now,
                      KitchenTicket.print_attempts: KitchenTicket.print_attempts + 1}, synchronize_session=False))
        if n:
            claimed.append(tid)
    db.commit()
    rows = db.query(KitchenTicket).filter(KitchenTicket.id.in_(claimed or [0])).order_by(KitchenTicket.id).all()
    return _out(db, rows)


@router.post("/{ticket_id}/reprint")
def reprint(ticket_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
            ctx: BranchContext = Depends(get_branch_context)):
    _guard(db, user)
    t = db.query(KitchenTicket).filter(KitchenTicket.id == ticket_id, KitchenTicket.company_id == user.company_id).first()
    if t is None or (ctx.allowed_branch_ids is not None and t.branch_id not in ctx.allowed_branch_ids):
        raise HTTPException(status_code=404, detail="Tiket topilmadi")
    t.printed_at = None
    log_action(db=db, action="KITCHEN_TICKET_REPRINT", entity_type="kitchen_ticket", entity_id=t.id, user_id=user.id,
               new_values={"order_id": t.order_id, "attempts": t.print_attempts or 0})
    db.commit()
    return {"ok": True}


@router.get("/recent")
def recent(branch_id: Optional[int] = None, station: Optional[str] = None, limit: int = Query(30, ge=1, le=100),
           db: Session = Depends(get_db), user: User = Depends(get_current_user),
           ctx: BranchContext = Depends(get_branch_context)):
    _guard(db, user)
    bid = _branch(db, user, ctx, branch_id)
    q = db.query(KitchenTicket).filter(KitchenTicket.company_id == user.company_id, KitchenTicket.branch_id == bid,
                                       KitchenTicket.printed_at.isnot(None))
    q = _station_filter(q, db, user, station)
    return _out(db, q.order_by(KitchenTicket.printed_at.desc()).limit(limit).all())
