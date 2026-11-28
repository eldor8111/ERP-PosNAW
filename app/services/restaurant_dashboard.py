"""Restoran bosh sahifasi (12-bo'lim oxiri): bugungi tushum, ochiq stollar va cheklar, oshxona navbati,
kechikayotgan taomlar (tex karta me'yori `cooking_time_min` dan oshgan), bugungi bronlar, stop-list.

Filial berilmasa korxonaning barcha faol filiallari jamlanadi.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.models.bom import BOM
from app.models.restaurant import Hall, KitchenStation, RestaurantTable
from app.models.restaurant_order import RestaurantOrder

ZERO = Decimal("0")
LATE_LIMIT = 15


def _naive(d):
    if d is None:
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def _branches(db: Session, company_id: int, branch_id: Optional[int]) -> list:
    from app.models.branch import Branch
    if branch_id:
        return [branch_id]
    q = db.query(Branch.id).filter(Branch.company_id == company_id)
    if hasattr(Branch, "is_active"):
        q = q.filter(Branch.is_active == True)  # noqa: E712
    return [r[0] for r in q.order_by(Branch.id).all()]


def build_dashboard(db: Session, company_id: int, branch_id: Optional[int], settings: dict,
                    now: Optional[datetime] = None) -> dict:
    from app.services import restaurant_reservations as rsv
    from app.services import restaurant_stops as stops
    from app.services.document_numbers import tashkent_today
    from app.services.restaurant_reports import build_report

    now = _naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    today = tashkent_today()
    bids = _branches(db, company_id, branch_id)
    kpi = build_report(db, company_id, branch_id, today, today)["kpi"]

    # ── ochiq cheklar va stollar ──
    orders = (db.query(RestaurantOrder).options(selectinload(RestaurantOrder.items))
              .filter(RestaurantOrder.company_id == company_id, RestaurantOrder.branch_id.in_(bids or [0]),
                      RestaurantOrder.status.in_(("open", "prechecked"))).all())
    open_sum = sum((Decimal(str(o.total or 0)) for o in orders), ZERO)
    busy_tables = {o.table_id for o in orders if o.table_id}
    total_tables = (db.query(RestaurantTable.id).join(Hall, Hall.id == RestaurantTable.hall_id)
                    .filter(Hall.company_id == company_id, Hall.branch_id.in_(bids or [0]), Hall.is_active == True,  # noqa: E712
                            RestaurantTable.is_active == True).count())  # noqa: E712

    # ── oshxona ──
    bom_ids = {it.bom_id for o in orders for it in o.items if it.bom_id}
    norms = {b.id: b.cooking_time_min for b in db.query(BOM.id, BOM.cooking_time_min).filter(BOM.id.in_(bom_ids or {0}))}
    stations = {s.id: s.name for s in db.query(KitchenStation).filter(KitchenStation.company_id == company_id)}
    tables = {t.id: t.name for t in db.query(RestaurantTable).filter(RestaurantTable.id.in_(busy_tables or {0}))}
    queue, ready_waiting, late = 0, 0, []
    by_station = {}
    for o in orders:
        for it in o.items:
            if it.status in ("sent", "cooking"):
                queue += 1
                st = by_station.setdefault(it.station_id, {"station_id": it.station_id,
                                                           "name": stations.get(it.station_id) or "-",
                                                           "queue": 0, "late": 0})
                st["queue"] += 1
                sent = _naive(it.sent_at)
                norm = norms.get(it.bom_id) if it.bom_id else None
                if sent is not None:
                    minutes = (now - sent).total_seconds() / 60.0
                    if norm and minutes > norm:
                        st["late"] += 1
                        late.append({"order_id": o.id, "daily_no": o.daily_no, "name": it.name,
                                     "quantity": float(it.quantity), "table": tables.get(o.table_id),
                                     "station": stations.get(it.station_id), "minutes": int(minutes),
                                     "norm": norm, "over": int(minutes - norm), "status": it.status})
            elif it.status == "ready":
                ready_waiting += 1
    late.sort(key=lambda x: -x["over"])

    # ── bugungi bronlar ──
    start, end = rsv.local_day_bounds(today)
    res_rows = []
    for bid in bids:
        res_rows += rsv.list_range(db, company_id, bid, start, end, statuses=("booked", "arrived"))
    res_rows.sort(key=lambda r: r.starts_at)
    names = rsv.table_names(db, company_id, {t for r in res_rows for t in (r.table_ids or [])})
    upcoming = [r for r in res_rows if r.status == "booked"]

    # ── stop-list ──
    stopped, low = {}, {}
    for bid in bids:
        st = stops.status(db, company_id, bid, settings)
        for s in st["stops"]:
            if s["effective"]:
                stopped[s["product_id"]] = s["name"]
        for x in st["low"]:
            low[x["product_id"]] = x["name"]

    return {
        "date": today.isoformat(), "branch_id": branch_id,
        "today": {"revenue": kpi["revenue"], "checks": kpi["checks"], "avg_check": kpi["avg_check"],
                  "guests": kpi["guests"], "food_cost_pct": kpi["food_cost_pct"], "cancels": kpi["cancels"],
                  "discounts": kpi["discounts"]},
        "open": {"checks": len(orders), "sum": float(open_sum),
                 "prechecked": sum(1 for o in orders if o.status == "prechecked"),
                 "busy_tables": len(busy_tables), "tables": total_tables,
                 "without_table": sum(1 for o in orders if not o.table_id)},
        "kitchen": {"queue": queue, "ready_waiting": ready_waiting, "late": len(late), "late_items": late[:LATE_LIMIT],
                    "stations": sorted(by_station.values(), key=lambda s: -s["queue"])},
        "reservations": {
            "count": len(upcoming), "guests": sum(int(r.guests or 0) for r in upcoming),
            "arrived": sum(1 for r in res_rows if r.status == "arrived"),
            "items": [{"id": r.id, "starts_at": rsv.iso(r.starts_at), "name": r.name, "phone": r.phone,
                       "guests": r.guests, "status": r.status,
                       "tables": [names.get(int(t), str(t)) for t in r.table_ids or []],
                       "deposit_held": float(rsv.held_amount(r))} for r in res_rows],
        },
        "stop_list": {"stopped": sorted(stopped.values(), key=str.lower), "low": sorted(low.values(), key=str.lower)},
    }
