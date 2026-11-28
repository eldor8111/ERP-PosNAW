"""Restoran cheklari API (R3, R2.3): chek, qatorlar, oshxonaga yuborish, pre-chek, bekor qilish, chegirma,
stol holatlari, ko'chirish, birlashtirish, xodim PIN kodi.

Hamma endpoint `require_restaurant` ostida. O'zgartiruvchi so'rovlar `?version=` qabul qiladi: chek boshqa
qurilmada o'zgargan bo'lsa 409 `ORDER_CHANGED` (13-bo'lim, optimistik qulf).
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.core.features import require_restaurant
from app.database import get_db
from app.models.branch import Branch
from app.models.restaurant import Hall, KitchenStation, RestaurantTable
from app.models.restaurant_order import KitchenTicket, RestaurantOrder, RestaurantOrderItem
from app.models.user import User, UserRole, UserStatus
from app.services import restaurant_orders as svc

router = APIRouter(prefix="/restaurant", tags=["Restoran cheklari"], dependencies=[Depends(require_restaurant)])


class Approval(BaseModel):
    user_id: int
    pin: str


class OpenIn(BaseModel):
    order_type: str = "dine_in"
    table_id: Optional[int] = None
    branch_id: Optional[int] = None
    guests: int = 1
    comment: Optional[str] = None


class ItemRow(BaseModel):
    product_id: int
    quantity: float = 1
    course: int = 1
    guest_no: Optional[int] = None
    comment: Optional[str] = None
    modifiers: Optional[List[int]] = None       # R1.3: tanlangan qo'shimcha variantlari


class ItemsIn(BaseModel):
    items: List[ItemRow]


class ItemPatch(BaseModel):
    quantity: Optional[float] = None
    modifiers: Optional[List[int]] = None
    course: Optional[int] = None
    guest_no: Optional[int] = None
    comment: Optional[str] = None


class CancelIn(BaseModel):
    reason: Optional[str] = None
    note: Optional[str] = None
    approval: Optional[Approval] = None


class SendIn(BaseModel):
    course: Optional[int] = None


class StatusIn(BaseModel):
    status: str


class DiscountIn(BaseModel):
    pct: Optional[float] = None
    amount: Optional[float] = None
    reason: Optional[str] = None
    approval: Optional[Approval] = None


class ApprovalIn(BaseModel):
    approval: Optional[Approval] = None


class MoveIn(BaseModel):
    table_id: int


class MergeIn(BaseModel):
    source_order_id: int


class SplitLine(BaseModel):
    item_id: int
    quantity: Optional[float] = None


class SplitIn(BaseModel):
    parts: Optional[List[List[SplitLine]]] = None   # qatorlar / mehmonlar bo'yicha: har ro'yxat — yangi chek
    equal: Optional[int] = None                      # teng bo'lish: N kishiga


class WaiterIn(BaseModel):
    waiter_id: int


class OrderPatch(BaseModel):
    guests: Optional[int] = None
    comment: Optional[str] = None


class PayRow(BaseModel):
    type: str
    amount: float
    reference: Optional[str] = None
    terminal_id: Optional[int] = None


class PayIn(BaseModel):
    payments: List[PayRow]
    tips: float = 0


class RefundLine(BaseModel):
    item_id: int
    quantity: Optional[float] = None
    restock: bool = False


class RefundIn(BaseModel):
    lines: Optional[List[RefundLine]] = None      # bo'sh — to'liq qaytarish
    reason: Optional[str] = None
    note: Optional[str] = None
    payment_type: str = "cash"
    approval: Optional[Approval] = None


class PinIn(BaseModel):
    pin: str
    password: Optional[str] = None


# ───────────────────────── yordamchilar ─────────────────────────

def _iso(d):
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _f(v):
    return float(v) if v is not None else None


def _item_out(it: RestaurantOrderItem) -> dict:
    return {
        "id": it.id, "product_id": it.product_id, "name": it.name, "quantity": float(it.quantity),
        "unit_price": float(it.unit_price), "modifiers_total": float(it.modifiers_total or 0),
        "modifiers": it.modifiers or [],
        "amount": float(it.quantity * (it.unit_price + (it.modifiers_total or 0))) if it.status != "cancelled" else 0.0,
        "course": it.course, "guest_no": it.guest_no, "station_id": it.station_id, "status": it.status,
        "comment": it.comment, "sent_at": _iso(it.sent_at), "ready_at": _iso(it.ready_at), "served_at": _iso(it.served_at),
        "cancel_reason": it.cancel_reason, "write_off": bool(it.write_off),
        "refunded_qty": float(it.refunded_qty or 0),
    }


def _order_out(db: Session, o: RestaurantOrder, settings: dict) -> dict:
    table = db.get(RestaurantTable, o.table_id) if o.table_id else None
    hall = db.get(Hall, o.hall_id) if o.hall_id else None
    waiter = db.get(User, o.waiter_id) if o.waiter_id else None
    return {
        "id": o.id, "number": o.number, "daily_no": o.daily_no, "branch_id": o.branch_id, "order_type": o.order_type,
        "table_id": o.table_id, "table_name": table.name if table else None,
        "hall_id": o.hall_id, "hall_name": hall.name if hall else None,
        "guests": o.guests, "waiter_id": o.waiter_id, "waiter_name": waiter.name if waiter else None,
        "status": o.status, "subtotal": _f(o.subtotal), "discount_pct": _f(o.discount_pct),
        "discount_amount": _f(o.discount_amount), "discount_reason": o.discount_reason,
        "service_pct": _f(o.service_pct), "service_amount": _f(o.service_amount), "total": _f(o.total),
        "comment": o.comment, "version": o.version, "opened_at": _iso(o.opened_at),
        "prechecked_at": _iso(o.prechecked_at), "closed_at": _iso(o.closed_at),
        "cancel_reason": o.cancel_reason, "merged_into_id": o.merged_into_id, "split_from_id": o.split_from_id,
        "sale_id": o.sale_id, "payments": o.payments or [], "tips_amount": _f(o.tips_amount),
        "change_amount": _f(o.change_amount),
        "refunded_amount": _f(o.refunded_amount or 0), "refunds": o.refunds or [],
        "locked": o.status == "prechecked" and bool(settings.get("precheck_lock", True)),
        "client_uuid": o.client_uuid, "offline_no": o.offline_no,     # R5.0: desktop oflayn chek
        "deposit": _deposit_of(db, o),
        "items": [_item_out(it) for it in o.items],
    }


def _deposit_of(db: Session, o: RestaurantOrder) -> float:
    """R8.1: ochiq chekka bog'langan bronning ishlatilmagan depoziti (to'lovda avtomatik qo'llanadi)."""
    if o.status not in ("open", "prechecked"):
        return 0.0
    from app.services.restaurant_reservations import order_deposit
    return float(order_deposit(db, o))


def _ticket_out(t: KitchenTicket, station_names: dict) -> dict:
    return {"id": t.id, "order_id": t.order_id, "station_id": t.station_id,
            "station_name": station_names.get(t.station_id), "kind": t.kind, "lines": t.lines,
            "created_at": _iso(t.created_at), "printed_at": _iso(t.printed_at)}


def _station_names(db: Session, company_id: int) -> dict:
    return {s.id: s.name for s in db.query(KitchenStation).filter(KitchenStation.company_id == company_id)}


def _ctx_order(db: Session, user: User, ctx: BranchContext, order_id: int, version: Optional[int] = None,
               lock: bool = True):
    settings = svc.settings_for(db, user.company_id)
    o = svc.get_order(db, user.company_id, order_id, lock=lock)
    svc.ensure_access(user, o, svc.rest_perms(user, settings), ctx.allowed_branch_ids)
    svc.check_version(o, version)
    return o, settings


def _item(o: RestaurantOrder, item_id: int) -> RestaurantOrderItem:
    for it in o.items:
        if it.id == item_id:
            return it
    raise HTTPException(status_code=404, detail="Qator topilmadi")


def _approval(a) -> Optional[dict]:
    return a.model_dump() if a is not None else None


def _done(db: Session, o: RestaurantOrder, settings: dict) -> dict:
    db.commit()
    db.refresh(o)
    return _order_out(db, o, settings)


def _branch_in_scope(db: Session, user: User, ctx: BranchContext, branch_id: int) -> None:
    b = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == user.company_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    if ctx.allowed_branch_ids is not None and branch_id not in ctx.allowed_branch_ids:
        raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")


# ───────────────────────── cheklar ─────────────────────────

@router.get("/orders")
def list_orders(
    branch_id: Optional[int] = None,
    status: str = Query("open,prechecked"),
    mine: bool = False,
    closed_today: bool = False,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    settings = svc.settings_for(db, user.company_id)
    perms = svc.rest_perms(user, settings)
    if not perms.get("orders") and not perms.get("kitchen"):
        raise HTTPException(status_code=403, detail="Cheklar bilan ishlashga ruxsat yo'q")
    statuses = [s for s in status.split(",") if s]
    q = db.query(RestaurantOrder).filter(RestaurantOrder.company_id == user.company_id,
                                         RestaurantOrder.status.in_(statuses))
    bid = branch_id or ctx.branch_id
    if bid is not None:
        _branch_in_scope(db, user, ctx, bid)
        q = q.filter(RestaurantOrder.branch_id == bid)
    elif ctx.allowed_branch_ids is not None:
        q = q.filter(RestaurantOrder.branch_id.in_(ctx.allowed_branch_ids))
    if mine or not perms.get("all_tables"):
        q = q.filter(RestaurantOrder.waiter_id == user.id)
    if closed_today:
        # R5.4: bugun (Toshkent vaqti) yopilgan cheklar — qaytarish oynasi uchun
        from datetime import datetime as _dt, time as _time, timedelta as _td
        from app.services.document_numbers import tashkent_today
        start = _dt.combine(tashkent_today(), _time.min) - _td(hours=5)      # UTC (Toshkent UTC+5)
        q = q.filter(RestaurantOrder.closed_at >= start)
        rows = q.order_by(RestaurantOrder.closed_at.desc()).limit(limit).all()
        return [_order_out(db, o, settings) for o in rows]
    rows = q.order_by(RestaurantOrder.opened_at.desc()).limit(limit).all()
    return [_order_out(db, o, settings) for o in rows]


@router.post("/orders", status_code=201)
def create_order(payload: OpenIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 ctx: BranchContext = Depends(get_branch_context)):
    settings = svc.settings_for(db, user.company_id)
    if not svc.rest_perms(user, settings).get("orders"):
        raise HTTPException(status_code=403, detail="Cheklar bilan ishlashga ruxsat yo'q")
    branch_id = payload.branch_id
    if payload.table_id is not None:
        t = db.query(RestaurantTable).filter(RestaurantTable.id == payload.table_id,
                                             RestaurantTable.company_id == user.company_id).first()
        if t is None:
            raise HTTPException(status_code=404, detail="Stol topilmadi")
        branch_id = db.get(Hall, t.hall_id).branch_id
    branch_id = branch_id or ctx.branch_id or (next(iter(ctx.allowed_branch_ids)) if ctx.allowed_branch_ids and len(ctx.allowed_branch_ids) == 1 else None)
    if branch_id is None:
        raise HTTPException(status_code=400, detail="Filial tanlanmagan")
    _branch_in_scope(db, user, ctx, branch_id)
    o = svc.open_order(db, user, settings, branch_id=branch_id, order_type=payload.order_type,
                       table_id=payload.table_id, guests=payload.guests, comment=payload.comment)
    return _done(db, o, settings)


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
              ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, lock=False)
    return _order_out(db, o, settings)


@router.patch("/orders/{order_id}")
def patch_order(order_id: int, payload: OrderPatch, version: Optional[int] = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    if o.status not in ("open", "prechecked"):
        raise HTTPException(status_code=409, detail="Chek yopilgan")
    if payload.guests is not None:
        if not 1 <= payload.guests <= 100:
            raise HTTPException(status_code=400, detail="Mehmonlar soni 1 dan 100 gacha")
        o.guests = payload.guests
    if payload.comment is not None:
        o.comment = payload.comment.strip()[:500] or None
    svc.bump(o)
    return _done(db, o, settings)


@router.post("/orders/{order_id}/items")
def add_items(order_id: int, payload: ItemsIn, version: Optional[int] = None, db: Session = Depends(get_db),
              user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.add_items(db, user, o, settings, [r.model_dump() for r in payload.items])
    return _done(db, o, settings)


@router.patch("/orders/{order_id}/items/{item_id}")
def patch_item(order_id: int, item_id: int, payload: ItemPatch, version: Optional[int] = None,
               db: Session = Depends(get_db), user: User = Depends(get_current_user),
               ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.update_draft_item(db, o, settings, _item(o, item_id), payload.model_dump(exclude_unset=True))
    return _done(db, o, settings)


@router.post("/orders/{order_id}/items/{item_id}/cancel")
def cancel_item(order_id: int, item_id: int, payload: CancelIn, version: Optional[int] = None,
                db: Session = Depends(get_db), user: User = Depends(get_current_user),
                ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.cancel_item(db, user, o, settings, _item(o, item_id), payload.reason, payload.note, _approval(payload.approval))
    return _done(db, o, settings)


@router.post("/orders/{order_id}/items/{item_id}/status")
def item_status(order_id: int, item_id: int, payload: StatusIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    settings = svc.settings_for(db, user.company_id)
    o = svc.get_order(db, user.company_id, order_id, lock=True)
    if ctx.allowed_branch_ids is not None and o.branch_id not in ctx.allowed_branch_ids:
        raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
    svc.set_item_status(db, user, o, settings, _item(o, item_id), payload.status)
    return _done(db, o, settings)


@router.post("/orders/{order_id}/send")
def send(order_id: int, payload: SendIn, version: Optional[int] = None, db: Session = Depends(get_db),
         user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    tickets = svc.send_to_kitchen(db, user, o, settings, payload.course)
    out = _done(db, o, settings)
    names = _station_names(db, user.company_id)
    out["tickets"] = [_ticket_out(t, names) for t in tickets]
    return out


@router.get("/orders/{order_id}/tickets")
def order_tickets(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                  ctx: BranchContext = Depends(get_branch_context)):
    o, _ = _ctx_order(db, user, ctx, order_id, lock=False)
    names = _station_names(db, user.company_id)
    rows = db.query(KitchenTicket).filter(KitchenTicket.order_id == o.id).order_by(KitchenTicket.id).all()
    return [_ticket_out(t, names) for t in rows]


@router.post("/orders/{order_id}/discount")
def discount(order_id: int, payload: DiscountIn, version: Optional[int] = None, db: Session = Depends(get_db),
             user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.set_discount(db, user, o, settings, payload.pct, payload.amount, payload.reason, _approval(payload.approval))
    return _done(db, o, settings)


@router.post("/orders/{order_id}/precheck")
def precheck(order_id: int, version: Optional[int] = None, db: Session = Depends(get_db),
             user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.precheck(db, user, o, settings)
    return _done(db, o, settings)


@router.post("/orders/{order_id}/unlock")
def unlock(order_id: int, payload: ApprovalIn, version: Optional[int] = None, db: Session = Depends(get_db),
           user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.unlock(db, user, o, settings, _approval(payload.approval))
    return _done(db, o, settings)


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, payload: CancelIn, version: Optional[int] = None, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.cancel_order(db, user, o, settings, payload.reason, payload.note, _approval(payload.approval))
    return _done(db, o, settings)


@router.post("/orders/{order_id}/move")
def move(order_id: int, payload: MoveIn, version: Optional[int] = None, db: Session = Depends(get_db),
         user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.move_order(db, user, o, settings, payload.table_id)
    return _done(db, o, settings)


@router.post("/orders/{order_id}/merge")
def merge(order_id: int, payload: MergeIn, version: Optional[int] = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    src, _ = _ctx_order(db, user, ctx, payload.source_order_id)
    svc.merge_orders(db, user, o, src, settings)
    return _done(db, o, settings)


@router.post("/orders/{order_id}/split")
def split(order_id: int, payload: SplitIn, version: Optional[int] = None, db: Session = Depends(get_db),
          user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    """R5.2: hisobni bo'lish. Qaytaradi: asl chek va yangi cheklar (har biri alohida to'lanadi)."""
    from app.services.restaurant_split import split_order
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    parts = [[ln.model_dump() for ln in part] for part in payload.parts] if payload.parts is not None else None
    children = split_order(db, user, o, settings, parts=parts, equal=payload.equal)
    db.commit()
    db.refresh(o)
    for c in children:
        db.refresh(c)
    return {"order": _order_out(db, o, settings), "created": [_order_out(db, c, settings) for c in children]}


@router.post("/orders/{order_id}/waiter")
def change_waiter(order_id: int, payload: WaiterIn, version: Optional[int] = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    svc.transfer_waiter(db, user, o, settings, payload.waiter_id)
    return _done(db, o, settings)


# ───────────────────────── to'lov (R5) ─────────────────────────

@router.post("/orders/{order_id}/pay")
def pay(order_id: int, payload: PayIn, request: Request, version: Optional[int] = None, db: Session = Depends(get_db),
        user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    from app.services.restaurant_payment import pay_order
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    sale, change = pay_order(db, user, o, settings, [p.model_dump() for p in payload.payments], payload.tips,
                             ip=request.client.host if request.client else None)
    db.refresh(o)
    out = _order_out(db, o, settings)
    out["sale"] = {"id": sale.id, "number": sale.number}
    out["change"] = float(change)
    out["fiscal"] = _fiscal_payload(db, o)
    return out


def _fiscal_payload(db: Session, o: RestaurantOrder) -> dict:
    """Mahalliy fiskal modul (hippoLocal.fiscalizeAndPrint) uchun savat: qatorlar, chegirma taqsimoti, to'lovlar.
    Chegirma taom qatorlariga summasiga mutanosib taqsimlanadi (xizmat haqi qatoriga tushmaydi)."""
    from decimal import ROUND_HALF_UP, Decimal
    from app.models.product import Product
    from app.services.restaurant_payment import service_product
    from app.models.company import Company
    from app.services.hippo_fiscalize import _vat_percent      # R5.0: desktop fiskal moduli uchun QQS foizi
    default_vat = db.query(Company.fiscal_default_vat).filter(Company.id == o.company_id).scalar()
    live = [it for it in o.items if it.status != "cancelled"]
    gross = [Decimal(str(it.quantity)) * (Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0))) for it in live]
    total_gross = sum(gross, Decimal("0"))
    disc = Decimal(str(o.discount_amount or 0))
    cart, left = [], disc
    for idx, (it, g) in enumerate(zip(live, gross)):
        p = db.get(Product, it.product_id)
        d = (left if idx == len(live) - 1 else (disc * g / total_gross).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if total_gross > 0 else Decimal("0")
        left -= d
        cart.append({"name": it.name, "barcode": p.barcode if p else "", "mxik_code": getattr(p, "mxik_code", None) or "",
                     "package_code": getattr(p, "package_code", None),
                     "vat_rate_type": getattr(getattr(p, "vat_rate_type", None), "value", None),
                     "vat_percent": _vat_percent(p, default_vat) if p else None,
                     "unit_price": float(Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0))),
                     "quantity": float(it.quantity), "discount": float(d)})
    if o.service_amount and Decimal(str(o.service_amount)) > 0:
        sp = service_product(db, o.company_id)
        cart.append({"name": sp.name, "barcode": sp.barcode, "mxik_code": sp.mxik_code or "",
                     "package_code": sp.package_code,
                     "vat_rate_type": getattr(sp.vat_rate_type, "value", None),
                     "vat_percent": _vat_percent(sp, default_vat),
                     "unit_price": float(o.service_amount), "quantity": 1.0, "discount": 0.0})
    # R8.1: depozit qatori fiskal modulga mijoz to'lagan usulda (reference: cash / card / ...) beriladi
    pays = [({**p, "type": p.get("reference") or "cash"} if p.get("type") == "deposit" else p) for p in (o.payments or [])]
    return {"cart": cart, "payments": pays, "discount": 0, "sale_id": o.sale_id}


@router.post("/orders/{order_id}/refund")
def refund(order_id: int, payload: RefundIn, request: Request, version: Optional[int] = None,
           db: Session = Depends(get_db), user: User = Depends(get_current_user),
           ctx: BranchContext = Depends(get_branch_context)):
    """R5.4: to'langan chekni to'liq yoki qatorlar bo'yicha qaytarish (pul qaytadi, taom omborga qaytmaydi)."""
    from app.services.restaurant_refund import refund_order
    o, settings = _ctx_order(db, user, ctx, order_id, version)
    ret, plan = refund_order(
        db, user, o, settings, lines=[ln.model_dump() for ln in payload.lines] if payload.lines else None,
        reason=payload.reason, note=payload.note, payment_type=payload.payment_type,
        approval=_approval(payload.approval), ip=request.client.host if request.client else None,
    )
    db.refresh(o)
    out = _order_out(db, o, settings)
    out["refund"] = {"sale_id": ret.id, "number": ret.number, "amount": float(plan["amount"]),
                     "fiscal_cart": _refund_fiscal_cart(db, plan)}
    return out


def _refund_fiscal_cart(db: Session, plan: dict) -> list:
    """Fiskal qaytarish cheki (hippoLocal.registerReturn) uchun qatorlar; chegirma qatorlarga mutanosib."""
    from decimal import ROUND_HALF_UP, Decimal
    from app.models.product import Product
    rows = []
    for it, qty, _ in plan["picked"]:
        p = db.get(Product, it.product_id)
        price = Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0))
        rows.append([it.name, p, price, qty])
    gross = sum((r[2] * r[3] for r in rows), Decimal("0"))
    disc, left = Decimal(str(plan["discount"])), Decimal(str(plan["discount"]))
    cart = []
    for idx, (name, p, price, qty) in enumerate(rows):
        d = left if idx == len(rows) - 1 else ((disc * price * qty / gross).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                                               if gross > 0 else Decimal("0"))
        left -= d
        cart.append({"name": name, "barcode": p.barcode if p else "", "mxik_code": (p.mxik_code if p else "") or "",
                     "package_code": p.package_code if p else None,
                     "vat_rate_type": getattr(getattr(p, "vat_rate_type", None), "value", None),
                     "unit_price": float(price), "quantity": float(qty), "discount": float(max(d, Decimal("0")))})
    if plan["service_qty"] > 0:
        cart.append({"name": "Xizmat haqi", "barcode": "", "mxik_code": "", "package_code": None, "vat_rate_type": None,
                     "unit_price": float(plan["service_price"]), "quantity": float(plan["service_qty"]), "discount": 0.0})
    return cart


@router.get("/orders/{order_id}/fiscal")
def fiscal_payload(order_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                   ctx: BranchContext = Depends(get_branch_context)):
    o, _ = _ctx_order(db, user, ctx, order_id, lock=False)
    if o.status != "paid":
        raise HTTPException(status_code=409, detail="Chek hali to'lanmagan")
    return _fiscal_payload(db, o)


# ───────────────────────── stol holatlari ─────────────────────────

@router.get("/tables/status")
def tables_status(branch_id: Optional[int] = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user), ctx: BranchContext = Depends(get_branch_context)):
    """Zal sxemasi uchun: har bir stol holati — free | busy | ready | precheck (ustuvorlik o'ngdan)."""
    settings = svc.settings_for(db, user.company_id)
    perms = svc.rest_perms(user, settings)
    if not perms.get("orders"):
        raise HTTPException(status_code=403, detail="Cheklar bilan ishlashga ruxsat yo'q")
    bid = branch_id or ctx.branch_id
    if bid is None:
        raise HTTPException(status_code=400, detail="Filial tanlanmagan")
    _branch_in_scope(db, user, ctx, bid)
    orders = db.query(RestaurantOrder).filter(RestaurantOrder.company_id == user.company_id,
                                              RestaurantOrder.branch_id == bid,
                                              RestaurantOrder.status.in_(("open", "prechecked")),
                                              RestaurantOrder.table_id.isnot(None)).all()
    now = datetime.now(timezone.utc)
    rank = {"free": 0, "reserved": 0, "busy": 1, "ready": 2, "precheck": 3}
    out = {}
    waiters = {}
    for o in orders:
        st = "precheck" if o.status == "prechecked" else (
            "ready" if any(it.status == "ready" for it in o.items) else "busy")
        if o.waiter_id and o.waiter_id not in waiters:
            w = db.get(User, o.waiter_id)
            waiters[o.waiter_id] = w.name if w else None
        opened = o.opened_at.replace(tzinfo=timezone.utc) if o.opened_at and o.opened_at.tzinfo is None else o.opened_at
        rec = out.setdefault(o.table_id, {"table_id": o.table_id, "status": "free", "orders": []})
        if rank[st] > rank[rec["status"]]:
            rec["status"] = st
        rec["orders"].append({
            "id": o.id, "daily_no": o.daily_no, "status": o.status, "guests": o.guests, "total": float(o.total or 0),
            "waiter_id": o.waiter_id, "waiter_name": waiters.get(o.waiter_id),
            "minutes": int((now - opened).total_seconds() // 60) if opened else None,
            "mine": o.waiter_id == user.id,
        })
    # R8.1: bugungi eng yaqin bron; bo'sh stol bron vaqtiga yaqinlashganda `reserved`
    from app.services.restaurant_reservations import floor_info
    for tid, info in floor_info(db, user.company_id, bid, settings).items():
        rec = out.get(tid)
        if rec is None:
            rec = out[tid] = {"table_id": tid, "status": "reserved" if info["reserved"] else "free", "orders": []}
        rec["reservation"] = info["reservation"]
    return list(out.values())


# ───────────────────────── PIN va tasdiqlovchilar ─────────────────────────

@router.put("/me/pin")
def set_my_pin(payload: PinIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.core.security import verify_password
    if not payload.password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=403, detail="Parol noto'g'ri")
    svc.set_pin(user, payload.pin)
    from app.core.audit import log_action
    log_action(db=db, action="REST_PIN_SET", entity_type="user", entity_id=user.id, user_id=user.id)
    db.commit()
    return {"ok": True}


@router.put("/staff/{user_id}/pin")
def set_staff_pin(user_id: int, payload: PinIn, db: Session = Depends(get_db),
                  admin: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director))):
    u = db.query(User).filter(User.id == user_id, User.company_id == admin.company_id).first()
    if u is None:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    svc.set_pin(u, payload.pin)
    from app.core.audit import log_action
    log_action(db=db, action="REST_PIN_SET", entity_type="user", entity_id=u.id, user_id=admin.id)
    db.commit()
    return {"ok": True}


@router.get("/approvers")
def approvers(capability: str = Query("cancel_sent"), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    """Tasdiq oynasi uchun: PIN o'rnatgan va shu amalga ruxsati bor xodimlar."""
    if capability not in ("cancel_sent", "discount", "unlock_precheck"):
        raise HTTPException(status_code=400, detail="Amal noto'g'ri")
    settings = svc.settings_for(db, user.company_id)
    rows = db.query(User).filter(User.company_id == user.company_id, User.status == UserStatus.active,
                                 User.pin_hash.isnot(None)).order_by(User.name).all()
    out = []
    for u in rows:
        p = svc.rest_perms(u, settings)
        ok = p.get("discount_max", 0) > 0 if capability == "discount" else bool(p.get(capability))
        if ok:
            out.append({"id": u.id, "name": u.name, "discount_max": p.get("discount_max", 0)})
    return out


@router.get("/me/perms")
def my_perms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    settings = svc.settings_for(db, user.company_id)
    return {**svc.rest_perms(user, settings), "has_pin": bool(user.pin_hash), "user_id": user.id}
