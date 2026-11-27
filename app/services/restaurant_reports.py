"""Restoran hisobotlari (12-bo'lim: 1, 2, 4, 8): kunlik ko'rsatkichlar, taomlar, ofitsiantlar,
bekor qilishlar va chegirmalar.

Davr Toshkent sanasi bo'yicha (UTC+5). Tushum — to'langan cheklar (`closed_at` davrda) jami minus
shu cheklardan qaytarilgan summa. Taom tannarxi — to'lovda sotuv qatoriga yozilgan haqiqiy tannarx.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, selectinload

from app.models.restaurant_order import RestaurantOrder, RestaurantOrderItem
from app.models.sale import SaleItem
from app.models.user import User

ZERO = Decimal("0")
MAX_DAYS = 92


def _utc_bounds(d_from: date, d_to: date):
    start = datetime.combine(d_from, time.min) - timedelta(hours=5)
    end = datetime.combine(d_to + timedelta(days=1), time.min) - timedelta(hours=5)
    return start, end


def _m(v) -> float:
    return float(Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _pct(a: Decimal, b: Decimal) -> Optional[float]:
    if not b:
        return None
    return float((a / b * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def build_report(db: Session, company_id: int, branch_id: Optional[int], d_from: date, d_to: date) -> dict:
    if d_to < d_from:
        raise HTTPException(status_code=400, detail="Davr noto'g'ri: boshlanish tugashdan keyin")
    if (d_to - d_from).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=400, detail=f"Davr {MAX_DAYS} kundan oshmasin")
    start, end = _utc_bounds(d_from, d_to)

    def scoped(q):
        q = q.filter(RestaurantOrder.company_id == company_id)
        return q.filter(RestaurantOrder.branch_id == branch_id) if branch_id else q

    paid = (scoped(db.query(RestaurantOrder)).options(selectinload(RestaurantOrder.items))
            .filter(RestaurantOrder.status == "paid", RestaurantOrder.closed_at >= start,
                    RestaurantOrder.closed_at < end).all())

    # ── ko'rsatkichlar ──
    gross = sum((Decimal(str(o.total or 0)) for o in paid), ZERO)
    refunded = sum((Decimal(str(o.refunded_amount or 0)) for o in paid), ZERO)
    net = gross - refunded
    checks = len(paid)
    guests = sum((int(o.guests or 0) for o in paid if o.order_type == "dine_in"), 0)
    pay_types = defaultdict(Decimal)
    by_type = defaultdict(lambda: {"checks": 0, "revenue": ZERO})
    for o in paid:
        for p in o.payments or []:
            pay_types[p.get("type") or "other"] += Decimal(str(p.get("amount") or 0))
        bt = by_type[o.order_type]
        bt["checks"] += 1
        bt["revenue"] += Decimal(str(o.total or 0)) - Decimal(str(o.refunded_amount or 0))

    # ── taomlar ── (sotuv qatoridagi haqiqiy tannarx: sale_id + product_id bo'yicha)
    sale_ids = [o.sale_id for o in paid if o.sale_id]
    unit_cost = {}
    if sale_ids:
        for sid, pid, qty, cost in db.query(SaleItem.sale_id, SaleItem.product_id, SaleItem.quantity,
                                            SaleItem.cost_price).filter(SaleItem.sale_id.in_(sale_ids)):
            k = (sid, pid)
            prev_q, prev_c = unit_cost.get(k, (ZERO, ZERO))
            q = Decimal(str(qty or 0))
            unit_cost[k] = (prev_q + q, prev_c + q * Decimal(str(cost or 0)))
    dishes = defaultdict(lambda: {"qty": ZERO, "revenue": ZERO, "cost": ZERO})
    for o in paid:
        for it in o.items:
            if it.status == "cancelled":
                continue
            q = Decimal(str(it.quantity)) - Decimal(str(it.refunded_qty or 0))
            if q <= 0:
                continue
            price = Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0))
            d = dishes[(it.product_id, it.name)]
            d["qty"] += q
            d["revenue"] += q * price
            tq, tc = unit_cost.get((o.sale_id, it.product_id), (ZERO, ZERO))
            if tq > 0:
                d["cost"] += q * tc / tq
    dish_rows = sorted(
        ({"product_id": pid, "name": name, "qty": float(v["qty"]), "revenue": _m(v["revenue"]),
          "cost": _m(v["cost"]), "profit": _m(v["revenue"] - v["cost"]),
          "food_cost_pct": _pct(v["cost"], v["revenue"])} for (pid, name), v in dishes.items()),
        key=lambda r: -r["revenue"])

    # ── bekor qilishlar (davrda bekor qilingan qatorlar, chek holatidan qat'i nazar) ──
    canc_q = (db.query(RestaurantOrderItem, RestaurantOrder)
              .join(RestaurantOrder, RestaurantOrder.id == RestaurantOrderItem.order_id)
              .filter(RestaurantOrderItem.status == "cancelled", RestaurantOrderItem.cancelled_at >= start,
                      RestaurantOrderItem.cancelled_at < end, RestaurantOrder.merged_into_id.is_(None)))
    canc_q = canc_q.filter(RestaurantOrder.company_id == company_id)
    if branch_id:
        canc_q = canc_q.filter(RestaurantOrder.branch_id == branch_id)
    cancels = canc_q.order_by(RestaurantOrderItem.cancelled_at.desc()).limit(500).all()

    user_ids = {o.waiter_id for o in paid if o.waiter_id}
    for it, o in cancels:
        user_ids |= {x for x in (it.cancelled_by, it.cancel_approved_by, o.waiter_id) if x}
    discounted = [o for o in paid if Decimal(str(o.discount_amount or 0)) > 0]
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_(user_ids or {0}))}

    cancel_rows = [{
        "order_id": o.id, "daily_no": o.daily_no, "name": it.name, "quantity": float(it.quantity),
        "amount": _m(Decimal(str(it.quantity)) * (Decimal(str(it.unit_price)) + Decimal(str(it.modifiers_total or 0)))),
        "reason": it.cancel_reason, "write_off": bool(it.write_off),
        "cancelled_by": names.get(it.cancelled_by), "approved_by": names.get(it.cancel_approved_by),
        "waiter": names.get(o.waiter_id), "at": it.cancelled_at.isoformat() if it.cancelled_at else None,
    } for it, o in cancels]

    # ── ofitsiantlar ──
    waiters = defaultdict(lambda: {"checks": 0, "revenue": ZERO, "guests": 0, "tips": ZERO, "discounts": ZERO,
                                   "cancels": 0, "cancel_amount": ZERO})
    for o in paid:
        w = waiters[o.waiter_id]
        w["checks"] += 1
        w["revenue"] += Decimal(str(o.total or 0)) - Decimal(str(o.refunded_amount or 0))
        w["guests"] += int(o.guests or 0) if o.order_type == "dine_in" else 0
        w["tips"] += Decimal(str(o.tips_amount or 0))
        w["discounts"] += Decimal(str(o.discount_amount or 0))
    for r, (it, o) in zip(cancel_rows, cancels):
        w = waiters[o.waiter_id]
        w["cancels"] += 1
        w["cancel_amount"] += Decimal(str(r["amount"]))
    waiter_rows = sorted(({
        "waiter_id": wid, "name": names.get(wid) or "-", "checks": v["checks"], "revenue": _m(v["revenue"]),
        "avg_check": _m(v["revenue"] / v["checks"]) if v["checks"] else 0.0, "guests": v["guests"],
        "tips": _m(v["tips"]), "discounts": _m(v["discounts"]), "cancels": v["cancels"],
        "cancel_amount": _m(v["cancel_amount"]),
    } for wid, v in waiters.items()), key=lambda r: -r["revenue"])

    discount_rows = [{
        "order_id": o.id, "daily_no": o.daily_no, "amount": _m(o.discount_amount),
        "pct": float(o.discount_pct) if o.discount_pct is not None else None, "reason": o.discount_reason,
        "waiter": names.get(o.waiter_id), "total": _m(o.total),
    } for o in sorted(discounted, key=lambda x: x.closed_at or x.opened_at, reverse=True)]

    cost_total = sum((Decimal(str(r["cost"])) for r in dish_rows), ZERO)
    dish_revenue = sum((Decimal(str(r["revenue"])) for r in dish_rows), ZERO)
    return {
        "period": {"from": d_from.isoformat(), "to": d_to.isoformat(), "branch_id": branch_id},
        "kpi": {
            "revenue": _m(net), "gross": _m(gross), "refunded": _m(refunded), "checks": checks,
            "avg_check": _m(net / checks) if checks else 0.0, "guests": guests,
            "avg_per_guest": _m(net / guests) if guests else 0.0,
            "service": _m(sum((Decimal(str(o.service_amount or 0)) for o in paid), ZERO)),
            "tips": _m(sum((Decimal(str(o.tips_amount or 0)) for o in paid), ZERO)),
            "discounts": _m(sum((Decimal(str(o.discount_amount or 0)) for o in paid), ZERO)),
            "cancels": len(cancel_rows),
            "cancel_amount": _m(sum((Decimal(str(r["amount"])) for r in cancel_rows), ZERO)),
            "food_cost_pct": _pct(cost_total, dish_revenue),
        },
        "payments": {k: _m(v) for k, v in sorted(pay_types.items())},
        "by_type": {k: {"checks": v["checks"], "revenue": _m(v["revenue"])} for k, v in by_type.items()},
        "dishes": dish_rows,
        "waiters": waiter_rows,
        "cancellations": cancel_rows,
        "discounts": discount_rows,
    }
