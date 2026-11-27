"""Hisobni bo'lish (R5.2).

Chek bir nechta alohida chekka ajratiladi: har bir qism o'z raqami bilan ochiq chek bo'lib qoladi va mavjud
to'lov orqali alohida to'lanadi (alohida sotuv, alohida fiskal chek). Shuning uchun qaytarish, hisobotlar va
smena hisobi o'zgarishsiz ishlaydi.

Usullar:
  * `parts`  — qatorlar (va mehmonlar) bo'yicha: [[{item_id, quantity}, ...], ...]; har bir ro'yxat — yangi chek,
               qolgani asl chekda qoladi. Qatorning bir qismini ham ajratish mumkin (2 ta oshdan 1 tasi).
  * `equal`  — teng bo'lish (N kishiga): har bir qator miqdori N ga bo'linadi (0.001 aniqlik), qoldiq asl chekda.

Qator bo'linsa oshxona holati, tannarx uchun yechilgan ingredientlar (stock_lines) ham mutanosib bo'linadi.
Foizli chegirma har bir qismga o'tadi, summali chegirma qismlar summasiga mutanosib taqsimlanadi.
Pre-chek chiqqan chek bo'linsa qismlar yana "ochiq" bo'ladi (pre-chek qayta chiqariladi).
"""
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.restaurant_order import RestaurantOrder, RestaurantOrderItem
from app.models.user import User

ZERO = Decimal("0")
MILLI = Decimal("0.001")
CENT = Decimal("0.01")
MAX_PARTS = 20


def _now():
    return datetime.now(timezone.utc)


def _scale_lines(lines: list, frac: Decimal) -> tuple:
    """stock_lines ni frac ulushga bo'ladi: (ajratilgan, qolgan). Yig'indi aynan saqlanadi."""
    moved, kept = [], []
    for ln in lines or []:
        q = Decimal(str(ln["quantity"]))
        part = (q * frac).quantize(MILLI, rounding=ROUND_HALF_UP)
        moved.append({**ln, "quantity": str(part)})
        kept.append({**ln, "quantity": str(q - part)})
    return moved, kept


def _take(item: RestaurantOrderItem, qty: Decimal, child: RestaurantOrder) -> None:
    """Qatordan qty miqdorni yangi chekka o'tkazadi (to'liq bo'lsa qatorning o'zi ko'chadi)."""
    cur = Decimal(str(item.quantity))
    if qty == cur:
        item.order = child
        return
    frac = qty / cur
    moved_lines, kept_lines = (_scale_lines(item.stock_lines, frac) if item.stock_deducted else (None, None))
    copy = RestaurantOrderItem(
        company_id=item.company_id, product_id=item.product_id, bom_id=item.bom_id, name=item.name, quantity=qty,
        unit_price=item.unit_price, modifiers=item.modifiers, modifiers_total=item.modifiers_total,
        course=item.course, guest_no=item.guest_no, station_id=item.station_id, status=item.status,
        comment=item.comment, created_by=item.created_by, created_at=item.created_at, sent_at=item.sent_at,
        cooking_at=item.cooking_at, ready_at=item.ready_at, served_at=item.served_at,
        stock_deducted=bool(item.stock_deducted), stock_lines=moved_lines,
    )
    item.quantity = cur - qty
    if item.stock_deducted:
        item.stock_lines = kept_lines
    child.items.append(copy)


def _plan_parts(order: RestaurantOrder, parts: list) -> list:
    live = {it.id: it for it in order.items if it.status != "cancelled"}
    used = {}
    plan = []
    for n, part in enumerate(parts, start=1):
        rows = []
        for ln in part or []:
            it = live.get(int(ln.get("item_id") or 0))
            if it is None:
                raise HTTPException(status_code=400, detail=f"{n}-qism: qator topilmadi yoki bekor qilingan")
            try:
                q = Decimal(str(ln.get("quantity") if ln.get("quantity") is not None else it.quantity))
            except Exception:
                raise HTTPException(status_code=400, detail=f"{n}-qism: miqdor noto'g'ri")
            q = q.quantize(MILLI, rounding=ROUND_HALF_UP)
            if not q.is_finite() or q <= 0:
                raise HTTPException(status_code=400, detail=f"{n}-qism: miqdor musbat bo'lsin")
            used[it.id] = used.get(it.id, ZERO) + q
            if used[it.id] > Decimal(str(it.quantity)):
                raise HTTPException(status_code=400, detail=f"'{it.name}' miqdoridan ko'p ajratildi")
            rows.append((it, q))
        if not rows:
            raise HTTPException(status_code=400, detail=f"{n}-qism bo'sh")
        plan.append(rows)
    left = sum((Decimal(str(it.quantity)) - used.get(it.id, ZERO) for it in live.values()), ZERO)
    if left <= 0:
        raise HTTPException(status_code=400, detail="Asl chekda kamida bitta taom qolsin")
    return plan


def _plan_equal(order: RestaurantOrder, n: int) -> list:
    live = [it for it in order.items if it.status != "cancelled"]
    plan = [[] for _ in range(n - 1)]
    for it in live:
        q = Decimal(str(it.quantity))
        per = (q / n).quantize(MILLI, rounding=ROUND_DOWN)
        if per <= 0:
            raise HTTPException(status_code=400, detail=f"'{it.name}' miqdorini {n} ga bo'lib bo'lmaydi")
        for rows in plan:
            rows.append((it, per))
    return plan


def split_order(db: Session, user: User, order: RestaurantOrder, settings: dict, *,
                parts: Optional[list] = None, equal: Optional[int] = None) -> list:
    from app.services.restaurant_orders import _next_daily_no, bump, ensure_editable, recalc, rest_perms
    if not rest_perms(user, settings).get("orders"):
        raise HTTPException(status_code=403, detail="Cheklar bilan ishlashga ruxsat yo'q")
    ensure_editable(order, settings)
    if not any(it.status != "cancelled" for it in order.items):
        raise HTTPException(status_code=400, detail="Chek bo'sh")
    if (parts is None) == (equal is None):
        raise HTTPException(status_code=400, detail="Qismlar yoki teng bo'lish sonidan bittasini yuboring")
    if equal is not None:
        n = int(equal)
        if not 2 <= n <= MAX_PARTS:
            raise HTTPException(status_code=400, detail=f"Teng bo'lish 2 dan {MAX_PARTS} gacha kishiga")
        plan = _plan_equal(order, n)
    else:
        if not parts or len(parts) > MAX_PARTS - 1:
            raise HTTPException(status_code=400, detail=f"1 dan {MAX_PARTS - 1} tagacha qism yuboring")
        plan = _plan_parts(order, parts)

    recalc(db, order, settings)
    fixed_discount = Decimal(str(order.discount_amount or 0)) if order.discount_pct is None else ZERO
    orig_sub = Decimal(str(order.subtotal or 0))
    now = _now()
    children = []
    for rows in plan:
        number, daily_no = _next_daily_no(db, order.company_id, order.branch_id)
        child = RestaurantOrder(
            company_id=order.company_id, branch_id=order.branch_id, number=number, daily_no=daily_no,
            order_type=order.order_type, table_id=order.table_id, hall_id=order.hall_id, guests=1,
            waiter_id=order.waiter_id, status="open", created_by=user.id, opened_at=now,
            discount_pct=order.discount_pct, discount_reason=order.discount_reason,
            comment=f"#{order.daily_no} dan bo'lingan", split_from_id=order.id,
        )
        db.add(child)
        db.flush()
        for it, q in rows:
            _take(it, q, child)
        children.append(child)
    db.flush()

    if equal is not None:
        order.guests = max(1, int(order.guests or 1) - (int(equal) - 1))
    else:
        order.guests = max(1, int(order.guests or 1) - len(children))
    # summali chegirma qismlar subtotaliga mutanosib
    for c in children:
        c.discount_amount = ZERO
        recalc(db, c, settings)
    if fixed_discount > 0 and orig_sub > 0:
        given = ZERO
        for c in children:
            share = (fixed_discount * Decimal(str(c.subtotal)) / orig_sub).quantize(CENT, rounding=ROUND_HALF_UP)
            c.discount_amount = share
            given += share
        order.discount_amount = fixed_discount - given
    for o in [order, *children]:
        recalc(db, o, settings)
        bump(o)
    log_action(db=db, action="REST_ORDER_SPLIT", entity_type="restaurant_order", entity_id=order.id, user_id=user.id,
               new_values={"mode": "equal" if equal is not None else "parts", "parts": len(children) + 1,
                           "created": [c.id for c in children], "totals": [float(o.total) for o in [order, *children]]})
    return children
