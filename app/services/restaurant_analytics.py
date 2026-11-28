"""Restoran tahliliy hisobotlari (12-bo'lim: 3, 5, 6, 7, 9; R7.4 nazariy va haqiqiy sarf).

3. Menyu muhandisligi (ABC, Kasavana-Smith): mashhurlik chegarasi = 70% x (1 / taomlar soni) ulush;
   foydalilik chegarasi = o'rtacha (vaznli) marja = jami foyda / jami miqdor. Guruhlar:
   star (ko'p va foydali), plowhorse (ko'p, kam foyda), puzzle (kam, foydali), dog (kam, kam foyda).
5. Yuklama: hafta kuni x soat (Toshkent vaqti, chek ochilgan vaqt) — cheklar, tushum, mehmonlar.
6. Stol aylanishi: stol bo'yicha to'langan zal cheklari soni, kuniga aylanish, o'rtacha o'tirish vaqti, tushum.
7. Oshxona tezligi: yuborishdan tayyorgacha (va navbatda kutish) o'rtacha daqiqa; sex va taom bo'yicha,
   tex karta me'yoridan (cooking_time_min) kechikkanlar.
9. Ombor: oshxona omboridagi ingredient va yarim tayyorlar — qoldiq, qiymat, tex karta bo'yicha nazariy sarf
   (sotuv + yarim tayyor tayyorlash), chiqim (bekor qilingan taom), inventarizatsiya farqi (revizya) va
   haqiqiy sarf = nazariy - farq; manfiy qoldiqlar.
"""
from collections import defaultdict
from datetime import date, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.restaurant import Hall, KitchenStation, RestaurantTable
from app.models.restaurant_order import RestaurantOrder, RestaurantOrderItem
from app.services.restaurant_reports import ZERO, _check_period, _m, _pct, _utc_bounds, dish_rows, paid_orders

LOCAL_OFFSET = timedelta(hours=5)
POPULARITY_FACTOR = Decimal("0.7")
SALES_REFS = ("restaurant_order",)
PRODUCTION_REFS = ("production_order", "production_cancel")
WRITEOFF_REFS = ("rest_writeoff",)
REVISION_REFS = ("revision", "revision_revert")


def _minutes(a, b) -> Optional[float]:
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 60.0


def _avg(xs) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _local(d):
    if d is None:
        return None
    if d.tzinfo is not None:
        d = d.astimezone(timezone.utc).replace(tzinfo=None)
    return d + LOCAL_OFFSET


# ── 3. menyu muhandisligi ─────────────────────────────────────────

def menu_engineering(rows: list) -> dict:
    items = [r for r in rows if r["qty"] > 0]
    if not items:
        return {"items": [], "popularity_threshold": None, "margin_threshold": None, "groups": {}}
    total_qty = sum((Decimal(str(r["qty"])) for r in items), ZERO)
    total_profit = sum((Decimal(str(r["profit"])) for r in items), ZERO)
    share_threshold = POPULARITY_FACTOR / Decimal(len(items))          # ulush (0..1)
    margin_threshold = total_profit / total_qty if total_qty > 0 else ZERO
    out = []
    groups = defaultdict(int)
    for r in items:
        qty = Decimal(str(r["qty"]))
        share = qty / total_qty if total_qty > 0 else ZERO
        margin = Decimal(str(r["profit"])) / qty
        popular = share >= share_threshold
        profitable = margin >= margin_threshold
        cls = ("star" if popular and profitable else "plowhorse" if popular
               else "puzzle" if profitable else "dog")
        groups[cls] += 1
        out.append({**r, "share_pct": float((share * 100).quantize(Decimal("0.1"))), "margin": _m(margin),
                    "class": cls})
    order = {"star": 0, "plowhorse": 1, "puzzle": 2, "dog": 3}
    out.sort(key=lambda x: (order[x["class"]], -x["profit"]))
    return {
        "items": out,
        "popularity_threshold": float((share_threshold * 100).quantize(Decimal("0.1"))),
        "margin_threshold": _m(margin_threshold),
        "groups": {k: groups.get(k, 0) for k in order},
    }


# ── 5. yuklama ────────────────────────────────────────────────────

def load_heatmap(paid: list, d_from: date, d_to: date) -> dict:
    checks = [[0] * 24 for _ in range(7)]
    revenue = [[ZERO] * 24 for _ in range(7)]
    guests = [[0] * 24 for _ in range(7)]
    for o in paid:
        t = _local(o.opened_at or o.closed_at)
        if t is None:
            continue
        wd, h = t.weekday(), t.hour
        checks[wd][h] += 1
        revenue[wd][h] += Decimal(str(o.total or 0)) - Decimal(str(o.refunded_amount or 0))
        guests[wd][h] += int(o.guests or 0) if o.order_type == "dine_in" else 0
    # davrdagi har hafta kuni soni (o'rtacha uchun)
    days = defaultdict(int)
    d = d_from
    while d <= d_to:
        days[d.weekday()] += 1
        d += timedelta(days=1)
    by_hour = [sum(checks[w][h] for w in range(7)) for h in range(24)]
    by_weekday = [sum(checks[w]) for w in range(7)]
    peak = max(((w, h) for w in range(7) for h in range(24)), key=lambda x: checks[x[0]][x[1]])
    return {
        "checks": checks,
        "revenue": [[_m(v) for v in row] for row in revenue],
        "guests": guests,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "weekday_days": [days.get(w, 0) for w in range(7)],
        "peak": {"weekday": peak[0], "hour": peak[1], "checks": checks[peak[0]][peak[1]]} if paid else None,
    }


# ── 6. stol aylanishi ─────────────────────────────────────────────

def table_turnover(db: Session, company_id: int, branch_id: Optional[int], paid: list, days: int) -> dict:
    tq = (db.query(RestaurantTable, Hall).join(Hall, Hall.id == RestaurantTable.hall_id)
          .filter(Hall.company_id == company_id))
    if branch_id:
        tq = tq.filter(Hall.branch_id == branch_id)
    tables = {t.id: (t, h) for t, h in tq.all()}
    agg = defaultdict(lambda: {"turns": 0, "minutes": [], "revenue": ZERO, "guests": 0})
    for o in paid:
        if o.order_type != "dine_in" or not o.table_id:
            continue
        a = agg[o.table_id]
        a["turns"] += 1
        a["minutes"].append(_minutes(o.opened_at, o.closed_at))
        a["revenue"] += Decimal(str(o.total or 0)) - Decimal(str(o.refunded_amount or 0))
        a["guests"] += int(o.guests or 0)
    rows = []
    for tid, (t, h) in tables.items():
        a = agg.get(tid, {"turns": 0, "minutes": [], "revenue": ZERO, "guests": 0})
        rows.append({
            "table_id": tid, "name": t.name, "hall": h.name, "seats": t.seats, "active": bool(t.is_active and h.is_active),
            "turns": a["turns"], "turns_per_day": round(a["turns"] / days, 2) if days else 0,
            "avg_minutes": _avg(a["minutes"]), "revenue": _m(a["revenue"]), "guests": a["guests"],
            "avg_check": _m(a["revenue"] / a["turns"]) if a["turns"] else 0.0,
            "revenue_per_seat": _m(a["revenue"] / t.seats) if t.seats else 0.0,
        })
    rows = [r for r in rows if r["active"] or r["turns"]]
    rows.sort(key=lambda r: (-r["turns"], r["hall"], r["name"]))
    all_minutes = [m for a in agg.values() for m in a["minutes"]]
    used = [r for r in rows if r["active"]]
    total_turns = sum(r["turns"] for r in rows)
    return {
        "rows": rows,
        "summary": {
            "tables": len(used), "turns": total_turns,
            "turns_per_table_day": round(total_turns / (len(used) * days), 2) if used and days else 0,
            "avg_minutes": _avg(all_minutes),
            "idle_tables": sum(1 for r in used if r["turns"] == 0),
        },
    }


# ── 7. oshxona tezligi ────────────────────────────────────────────

def kitchen_speed(db: Session, company_id: int, branch_id: Optional[int], start, end) -> dict:
    from app.models.bom import BOM
    q = (db.query(RestaurantOrderItem, RestaurantOrder.branch_id)
         .join(RestaurantOrder, RestaurantOrder.id == RestaurantOrderItem.order_id)
         .filter(RestaurantOrder.company_id == company_id, RestaurantOrderItem.sent_at >= start,
                 RestaurantOrderItem.sent_at < end, RestaurantOrderItem.ready_at.isnot(None),
                 RestaurantOrderItem.status != "cancelled"))
    if branch_id:
        q = q.filter(RestaurantOrder.branch_id == branch_id)
    items = [it for it, _ in q.all()]
    norms = {}
    bom_ids = {it.bom_id for it in items if it.bom_id}
    if bom_ids:
        norms = {b.id: b.cooking_time_min for b in db.query(BOM.id, BOM.cooking_time_min).filter(BOM.id.in_(bom_ids))}
    stations = {s.id: s.name for s in db.query(KitchenStation).filter(KitchenStation.company_id == company_id)}
    by_station = defaultdict(lambda: {"n": 0, "total": [], "wait": [], "late": 0})
    by_dish = defaultdict(lambda: {"n": 0, "total": [], "late": 0, "norm": None})
    all_total, all_wait, late = [], [], 0
    for it in items:
        total = _minutes(it.sent_at, it.ready_at)
        if total is None or total < 0:
            continue
        wait = _minutes(it.sent_at, it.cooking_at) if it.cooking_at else None
        norm = norms.get(it.bom_id) if it.bom_id else None
        is_late = bool(norm) and total > norm
        s = by_station[it.station_id]
        s["n"] += 1
        s["total"].append(total)
        s["wait"].append(wait)
        s["late"] += 1 if is_late else 0
        d = by_dish[(it.product_id, it.name)]
        d["n"] += 1
        d["total"].append(total)
        d["late"] += 1 if is_late else 0
        d["norm"] = norm or d["norm"]
        all_total.append(total)
        all_wait.append(wait)
        late += 1 if is_late else 0

    def p90(xs):
        xs = sorted(x for x in xs if x is not None)
        return round(xs[min(len(xs) - 1, int(len(xs) * 0.9))], 1) if xs else None

    station_rows = sorted(({
        "station_id": sid, "name": stations.get(sid) or "-", "items": v["n"], "avg_minutes": _avg(v["total"]),
        "p90_minutes": p90(v["total"]), "avg_wait": _avg(v["wait"]), "late": v["late"],
        "late_pct": round(v["late"] / v["n"] * 100, 1) if v["n"] else 0,
    } for sid, v in by_station.items()), key=lambda r: -(r["avg_minutes"] or 0))
    dish_rows_ = sorted(({
        "product_id": pid, "name": name, "items": v["n"], "avg_minutes": _avg(v["total"]),
        "norm": v["norm"], "late": v["late"], "late_pct": round(v["late"] / v["n"] * 100, 1) if v["n"] else 0,
    } for (pid, name), v in by_dish.items()), key=lambda r: (-r["late_pct"], -(r["avg_minutes"] or 0)))
    return {
        "summary": {"items": len(all_total), "avg_minutes": _avg(all_total), "p90_minutes": p90(all_total),
                    "avg_wait": _avg(all_wait), "late": late,
                    "late_pct": round(late / len(all_total) * 100, 1) if all_total else 0},
        "stations": station_rows,
        "dishes": dish_rows_,
    }


# ── 9. ombor (R7.4 nazariy va haqiqiy sarf) ───────────────────────

def _kitchen_warehouses(db: Session, company_id: int, branch_id: Optional[int]) -> list:
    from app.models.branch import Branch
    from app.services.restaurant import get_kitchen_warehouse
    bq = db.query(Branch).filter(Branch.company_id == company_id)
    if branch_id:
        bq = bq.filter(Branch.id == branch_id)
    out = []
    for b in bq.all():
        wh = get_kitchen_warehouse(db, company_id, b.id)
        if wh is not None and wh.id not in {w.id for w in out}:
            out.append(wh)
    return out


def stock_report(db: Session, company_id: int, branch_id: Optional[int], start, end) -> dict:
    from app.services.restaurant_menu import CostCalc
    whs = _kitchen_warehouses(db, company_id, branch_id)
    wh_ids = [w.id for w in whs]
    products = {p.id: p for p in db.query(Product).filter(
        Product.company_id == company_id, Product.is_deleted == False,  # noqa: E712
        Product.item_kind.in_(("ingredient", "semi")))}
    if not wh_ids or not products:
        return {"warehouses": [{"id": w.id, "name": w.name} for w in whs], "rows": [], "negative": [],
                "summary": {"value": 0.0, "theoretical_cost": 0.0, "variance_cost": 0.0, "writeoff_cost": 0.0,
                            "variance_pct": None, "negative": 0}}
    pids = list(products)
    stock = defaultdict(lambda: ZERO)
    for pid, qty in db.query(StockLevel.product_id, StockLevel.quantity).filter(
            StockLevel.warehouse_id.in_(wh_ids), StockLevel.product_id.in_(pids), StockLevel.variant_id.is_(None)):
        stock[pid] += Decimal(str(qty or 0))

    sales = defaultdict(lambda: ZERO)        # tex karta bo'yicha sotuv sarfi (qaytgani ayirilgan)
    production = defaultdict(lambda: ZERO)   # yarim tayyor tayyorlashga sarf (bekor qilingani ayirilgan)
    produced = defaultdict(lambda: ZERO)     # tayyorlangan yarim tayyor (kirim)
    writeoff = defaultdict(lambda: ZERO)
    variance = defaultdict(lambda: ZERO)     # revizya: + ortiqcha, - kamomad
    mq = db.query(StockMovement).filter(
        StockMovement.warehouse_id.in_(wh_ids), StockMovement.product_id.in_(pids),
        StockMovement.created_at >= start, StockMovement.created_at < end,
        StockMovement.reference_type.in_(SALES_REFS + PRODUCTION_REFS + WRITEOFF_REFS + REVISION_REFS))
    for m in mq.all():
        q = Decimal(str(m.quantity or 0))
        out_ = m.type == MovementType.OUT
        ref = m.reference_type
        if ref in SALES_REFS:
            sales[m.product_id] += q if out_ else -q
        elif ref in PRODUCTION_REFS:
            # tayyorlash: xom ashyo OUT, yarim tayyor IN; bekor qilish teskari
            if ref == "production_order":
                (production if out_ else produced)[m.product_id] += q
            else:
                if out_:
                    produced[m.product_id] -= q
                else:
                    production[m.product_id] -= q
        elif ref in WRITEOFF_REFS:
            writeoff[m.product_id] += q if out_ else -q
        elif ref in REVISION_REFS:
            variance[m.product_id] += Decimal(str(m.qty_after or 0)) - Decimal(str(m.qty_before or 0))

    calc = CostCalc(db, company_id)
    rows = []
    tot = defaultdict(lambda: ZERO)
    for pid, p in products.items():
        qty = stock.get(pid, ZERO)
        theo = sales.get(pid, ZERO) + production.get(pid, ZERO)
        wo = writeoff.get(pid, ZERO)
        var = variance.get(pid, ZERO)
        if not any((qty, theo, wo, var, produced.get(pid, ZERO))):
            continue
        uc = calc.unit_cost(p) if p.item_kind == "semi" else calc._own_cost(p)
        actual = theo + wo - var
        rows.append({
            "product_id": pid, "name": p.name, "kind": p.item_kind, "unit": p.unit,
            "stock": float(qty), "value": _m(qty * uc) if qty > 0 else 0.0, "unit_cost": _m(uc),
            "sales": float(sales.get(pid, ZERO)), "production": float(production.get(pid, ZERO)),
            "produced": float(produced.get(pid, ZERO)), "theoretical": float(theo), "writeoff": float(wo),
            "variance": float(var), "actual": float(actual),
            "variance_pct": _pct(-var, theo) if theo > 0 and var != 0 else None,
            "variance_cost": _m(var * uc), "theoretical_cost": _m(theo * uc), "writeoff_cost": _m(wo * uc),
            "negative": qty < 0,
        })
        tot["value"] += qty * uc if qty > 0 else ZERO
        tot["theo"] += theo * uc
        tot["var"] += var * uc
        tot["wo"] += wo * uc
    rows.sort(key=lambda r: (r["variance_cost"], -r["theoretical_cost"]))
    negative = [r for r in rows if r["negative"]]
    return {
        "warehouses": [{"id": w.id, "name": w.name} for w in whs],
        "rows": rows,
        "negative": negative,
        "summary": {"value": _m(tot["value"]), "theoretical_cost": _m(tot["theo"]), "variance_cost": _m(tot["var"]),
                    "writeoff_cost": _m(tot["wo"]), "variance_pct": _pct(-tot["var"], tot["theo"]) if tot["theo"] else None,
                    "negative": len(negative)},
    }


def build_analytics(db: Session, company_id: int, branch_id: Optional[int], d_from: date, d_to: date) -> dict:
    _check_period(d_from, d_to)
    start, end = _utc_bounds(d_from, d_to)
    days = (d_to - d_from).days + 1
    paid = paid_orders(db, company_id, branch_id, start, end)
    return {
        "period": {"from": d_from.isoformat(), "to": d_to.isoformat(), "branch_id": branch_id, "days": days},
        "menu": menu_engineering(dish_rows(db, paid)),
        "load": load_heatmap(paid, d_from, d_to),
        "tables": table_turnover(db, company_id, branch_id, paid, days),
        "kitchen": kitchen_speed(db, company_id, branch_id, start, end),
        "stock": stock_report(db, company_id, branch_id, start, end),
    }
