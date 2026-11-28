"""Oshxona ekrani — KDS (R4.2).

GET  /restaurant/kds            — oshxonadagi faol taomlar chek bo'yicha kartochka (sex filtri bilan)
POST /restaurant/kds/status     — bir nechta qatorni bir yo'la `cooking` / `ready` / `served` qilish

Ruxsat: `kitchen` (oshpaz, barmen) yoki `orders` (ko'rish). Holatni oshxona holatiga (`cooking`, `ready`) faqat
`kitchen` ruxsati borlar o'tkazadi, `served` ni ofitsiant ham (mavjud `set_item_status` qoidasi).
Yangilanish so'rov (polling) orqali; WebSocket keyingi bosqichda.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user
from app.core.features import require_restaurant, require_restaurant_feature
from app.database import get_db
from app.models.bom import BOM
from app.models.branch import Branch
from app.models.restaurant import KitchenStation, RestaurantTable
from app.models.restaurant_order import RestaurantOrder, RestaurantOrderItem
from app.models.user import User
from app.services import restaurant_orders as svc

router = APIRouter(prefix="/restaurant/kds", tags=["Oshxona ekrani"],
                   dependencies=[Depends(require_restaurant), Depends(require_restaurant_feature("kds"))])

ACTIVE = ("sent", "cooking", "ready")
CANCEL_SHOW_MINUTES = 15


class KdsStatusIn(BaseModel):
    item_ids: List[int]
    status: str


def _iso(d):
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _branch(db: Session, user: User, ctx: BranchContext, branch_id: Optional[int]) -> int:
    bid = branch_id or ctx.branch_id or (next(iter(ctx.allowed_branch_ids))
                                         if ctx.allowed_branch_ids and len(ctx.allowed_branch_ids) == 1 else None)
    if bid is None:
        raise HTTPException(status_code=400, detail="Filial tanlanmagan")
    if not db.query(Branch.id).filter(Branch.id == bid, Branch.company_id == user.company_id).first():
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    if ctx.allowed_branch_ids is not None and bid not in ctx.allowed_branch_ids:
        raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
    return bid


@router.get("")
def kds_board(
    branch_id: Optional[int] = None,
    station: Optional[str] = Query(None, description="sex id, 'none' (sexsiz) yoki bo'sh — hammasi"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    settings = svc.settings_for(db, user.company_id)
    perms = svc.rest_perms(user, settings)
    if not (perms.get("kitchen") or perms.get("orders")):
        raise HTTPException(status_code=403, detail="Oshxona ekraniga ruxsat yo'q")
    bid = _branch(db, user, ctx, branch_id)
    station_id = None
    if station not in (None, "", "all", "none"):
        try:
            station_id = int(station)
        except ValueError:
            raise HTTPException(status_code=400, detail="Sex noto'g'ri")
        if not db.query(KitchenStation.id).filter(KitchenStation.id == station_id,
                                                  KitchenStation.company_id == user.company_id).first():
            raise HTTPException(status_code=404, detail="Sex topilmadi")

    now = datetime.now(timezone.utc)
    cancel_edge = (now - timedelta(minutes=CANCEL_SHOW_MINUTES)).replace(tzinfo=None)
    orders = (db.query(RestaurantOrder).options(selectinload(RestaurantOrder.items))
              .filter(RestaurantOrder.company_id == user.company_id, RestaurantOrder.branch_id == bid,
                      RestaurantOrder.status.in_(("open", "prechecked")))
              .all())

    def station_ok(it):
        if station == "none":
            return it.station_id is None
        if station_id is not None:
            return it.station_id == station_id
        return True

    bom_ids = {it.bom_id for o in orders for it in o.items if it.bom_id}
    norms = {b.id: b.cooking_time_min for b in db.query(BOM).filter(BOM.id.in_(bom_ids or {0}))}
    table_ids = {o.table_id for o in orders if o.table_id}
    tables = {t.id: t.name for t in db.query(RestaurantTable).filter(RestaurantTable.id.in_(table_ids or {0}))}
    waiter_ids = {o.waiter_id for o in orders if o.waiter_id}
    waiters = {u.id: u.name for u in db.query(User).filter(User.id.in_(waiter_ids or {0}))}

    cards, totals = [], {}
    for o in orders:
        rows = []
        for it in o.items:
            if not station_ok(it):
                continue
            recent_cancel = (it.status == "cancelled" and it.sent_at is not None and it.cancelled_at is not None
                             and it.cancelled_at.replace(tzinfo=None) >= cancel_edge)
            if it.status not in ACTIVE and not recent_cancel:
                continue
            rows.append({
                "id": it.id, "name": it.name, "quantity": float(it.quantity), "comment": it.comment,
                "modifiers": [m.get("name") for m in (it.modifiers or [])],
                "course": it.course, "guest_no": it.guest_no, "status": it.status, "station_id": it.station_id,
                "norm_min": norms.get(it.bom_id), "sent_at": _iso(it.sent_at), "cooking_at": _iso(it.cooking_at),
                "ready_at": _iso(it.ready_at), "cancel_reason": it.cancel_reason if it.status == "cancelled" else None,
            })
            if it.status in ("sent", "cooking"):
                totals[it.name] = totals.get(it.name, 0.0) + float(it.quantity)
        if not rows:
            continue
        first = min((r["sent_at"] for r in rows if r["sent_at"]), default=None)
        cards.append({"order_id": o.id, "daily_no": o.daily_no, "order_type": o.order_type,
                      "table_name": tables.get(o.table_id), "waiter_name": waiters.get(o.waiter_id),
                      "guests": o.guests, "comment": o.comment, "first_sent_at": first, "version": o.version,
                      "items": sorted(rows, key=lambda r: (r["course"], r["sent_at"] or "", r["id"]))})
    cards.sort(key=lambda c: c["first_sent_at"] or "")
    return {
        "server_time": now.isoformat(),
        "cards": cards,
        "totals": [{"name": k, "quantity": v} for k, v in sorted(totals.items(), key=lambda kv: -kv[1])],
    }


@router.post("/status")
def kds_status(payload: KdsStatusIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
               ctx: BranchContext = Depends(get_branch_context)):
    """Bir nechta qatorni bir yo'la o'tkazadi (masalan, kartochkaning hamma taomi tayyor). Holati allaqachon shu
    yoki undan keyingi bo'lgan qatorlar o'tkazib yuboriladi (ikki oshpaz bir vaqtda bossa xato bo'lmaydi)."""
    if payload.status not in ("cooking", "ready", "served"):
        raise HTTPException(status_code=400, detail="Holat noto'g'ri")
    ids = list(dict.fromkeys(payload.item_ids or []))
    if not ids or len(ids) > 100:
        raise HTTPException(status_code=400, detail="1 dan 100 tagacha qator yuboring")
    settings = svc.settings_for(db, user.company_id)
    items = (db.query(RestaurantOrderItem).filter(RestaurantOrderItem.id.in_(ids),
                                                  RestaurantOrderItem.company_id == user.company_id).all())
    if len(items) != len(ids):
        raise HTTPException(status_code=404, detail="Qator topilmadi")
    order_cache = {}
    order_rank = {"sent": 0, "cooking": 1, "ready": 2, "served": 3}
    changed = 0
    for it in sorted(items, key=lambda x: x.id):
        o = order_cache.get(it.order_id)
        if o is None:
            o = svc.get_order(db, user.company_id, it.order_id, lock=True)
            if ctx.allowed_branch_ids is not None and o.branch_id not in ctx.allowed_branch_ids:
                raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
            order_cache[it.order_id] = o
        if it.status == "cancelled" or order_rank.get(it.status, -1) >= order_rank[payload.status]:
            continue
        svc.set_item_status(db, user, o, settings, it, payload.status)
        changed += 1
    db.commit()
    return {"ok": True, "changed": changed}
