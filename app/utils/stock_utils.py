"""Ombor bo'yicha min/max qoldiq va "kam qoldiq" hisob-kitobi (T4.4).

`WarehouseStockSetting` (ombor x mahsulot) bo'lsa — shu ombor uchun alohida chegara, bo'lmasa
mahsulot darajasidagi `Product.min_stock` / `Product.max_stock`:

    effective_min() = coalesce(WarehouseStockSetting.min_qty, Product.min_stock)
    effective_max() = coalesce(WarehouseStockSetting.max_qty, Product.max_stock)

"Kam qoldiq" ta'rifi (T2.3 ta'rifining kengaytmasi, sozlama yo'q bo'lsa AYNAN o'sha natija):
  - `min_qty` o'rnatilgan (ombor, mahsulot) juftligi alohida birlik: shu ombordagi qoldiq (variantlar
    yig'indisi) `<= min_qty` va `min_qty > 0`;
  - qolgan omborlar (doiradagi, `min_qty` o'rnatilmagan) mahsulot bo'yicha YIG'ILADI: jami qoldiq
    `<= Product.min_stock` va `Product.min_stock > 0` (doirada shunday ombor bo'lsa).
Mahsulot — birliklardan kamida biri kam bo'lsa kam hisoblanadi. Faqat faol omborlar,
`is_deleted = false`, `product_type != 'sell'`.

Doira (`wh_ids`): `None` — butun korxona, ro'yxat — shu omborlar, bo'sh ro'yxat — hech narsa.
"""
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.models.warehouse_stock_setting import WarehouseStockSetting as WSS

# Qoldig'i o'zida saqlanmaydigan (konversiya orqali virtual) mahsulot turi
VIRTUAL_PRODUCT_TYPE = "sell"


def effective_min():
    """SQL ifoda: ombor sozlamasi `min_qty`, bo'lmasa `Product.min_stock`."""
    return func.coalesce(WSS.min_qty, Product.min_stock)


def effective_max():
    """SQL ifoda: ombor sozlamasi `max_qty`, bo'lmasa `Product.max_stock`."""
    return func.coalesce(WSS.max_qty, Product.max_stock)


def _dec(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def _scope_filters(cid, wh_ids):
    """Faol ombor + doira sharti (StockLevel/WSS Warehouse bilan join qilingan so'rovlar uchun)."""
    conds = [Warehouse.company_id == cid, Warehouse.is_active.isnot(False)]
    if wh_ids is not None:
        conds.append(Warehouse.id.in_(list(wh_ids)))
    return conds


def _scope_warehouse_count(db: Session, cid, wh_ids) -> int:
    return int(db.query(func.count(Warehouse.id)).filter(*_scope_filters(cid, wh_ids)).scalar() or 0)


def _product_type_filter(q, product_types):
    if product_types:
        return q.filter(Product.product_type.in_(list(product_types)))
    return q.filter(func.coalesce(Product.product_type, "simple") != VIRTUAL_PRODUCT_TYPE)


# ─── SQL: kam qoldiq ─────────────────────────────────────────────────────────

def _wh_qty_subq(db: Session, cid, wh_ids):
    """(ombor, mahsulot) bo'yicha jami qoldiq (variantlar yig'indisi)."""
    return (
        db.query(StockLevel.warehouse_id.label("warehouse_id"), StockLevel.product_id.label("product_id"),
                 func.coalesce(func.sum(StockLevel.quantity), 0).label("qty"))
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .filter(*_scope_filters(cid, wh_ids))
        .group_by(StockLevel.warehouse_id, StockLevel.product_id)
        .subquery()
    )


def _override_low_query(db: Session, cid, wh_ids, product_types=None):
    """`min_qty` o'rnatilgan va qoldig'i shu chegaradan oshmagan (ombor, mahsulot) juftliklari."""
    wq = _wh_qty_subq(db, cid, wh_ids)
    qty = func.coalesce(wq.c.qty, 0)
    q = (
        db.query(WSS.warehouse_id.label("warehouse_id"), WSS.product_id.label("product_id"),
                 qty.label("qty"), WSS.min_qty.label("min_v"))
        .select_from(WSS)
        .join(Warehouse, Warehouse.id == WSS.warehouse_id)
        .join(Product, Product.id == WSS.product_id)
        .outerjoin(wq, and_(wq.c.warehouse_id == WSS.warehouse_id, wq.c.product_id == WSS.product_id))
        .filter(
            WSS.company_id == cid,
            Product.company_id == cid,
            Product.is_deleted == False,  # noqa: E712
            WSS.min_qty.isnot(None),
            WSS.min_qty > 0,
            qty <= WSS.min_qty,
            *_scope_filters(cid, wh_ids),
        )
    )
    return _product_type_filter(q, product_types)


def _remainder_low_query(db: Session, cid, wh_ids, product_types=None):
    """`(Product, jami qoldiq)`: `min_qty` o'rnatilmagan doira omborlari yig'indisi `<= Product.min_stock`."""
    rem = (
        db.query(StockLevel.product_id.label("product_id"),
                 func.coalesce(func.sum(StockLevel.quantity), 0).label("qty"))
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .outerjoin(WSS, and_(WSS.warehouse_id == StockLevel.warehouse_id, WSS.product_id == StockLevel.product_id,
                             WSS.min_qty.isnot(None)))
        .filter(WSS.id.is_(None), *_scope_filters(cid, wh_ids))
        .group_by(StockLevel.product_id)
        .subquery()
    )
    ov = (
        db.query(WSS.product_id.label("product_id"), func.count(WSS.id).label("cnt"))
        .join(Warehouse, Warehouse.id == WSS.warehouse_id)
        .filter(WSS.company_id == cid, WSS.min_qty.isnot(None), *_scope_filters(cid, wh_ids))
        .group_by(WSS.product_id)
        .subquery()
    )
    n_scope = _scope_warehouse_count(db, cid, wh_ids)
    qty = func.coalesce(rem.c.qty, 0)
    q = (
        db.query(Product, qty.label("qty"))
        .outerjoin(rem, rem.c.product_id == Product.id)
        .outerjoin(ov, ov.c.product_id == Product.id)
        .filter(
            Product.company_id == cid,
            Product.is_deleted == False,  # noqa: E712
            Product.min_stock > 0,
            qty <= Product.min_stock,
            # sozlamasi yo'q mahsulot — avvalgidek; sozlamali bo'lsa doirada sozlamasiz ombor qolishi kerak
            or_(ov.c.cnt.is_(None), n_scope - ov.c.cnt > 0),
        )
    )
    return _product_type_filter(q, product_types)


def low_stock_subquery(db: Session, cid, wh_ids, product_types=None):
    """Kam qoldiqli mahsulot id'lari (`SELECT id ...`) — boshqa so'rovlarda `IN` uchun."""
    a = _override_low_query(db, cid, wh_ids, product_types).with_entities(WSS.product_id.label("id"))
    b = _remainder_low_query(db, cid, wh_ids, product_types).with_entities(Product.id.label("id"))
    return a.union(b).subquery()


def low_stock_count(db: Session, cid, wh_ids, *, product_types=None) -> int:
    """Kam qoldiqli MAHSULOTLAR soni (qator emas)."""
    if wh_ids is not None and not wh_ids:
        return 0
    sub = low_stock_subquery(db, cid, wh_ids, product_types)
    return int(db.query(func.count()).select_from(sub).scalar() or 0)


def low_stock_rows_filter(db: Session, cid, wh_ids):
    """`/inventory/stock?low_stock_only` uchun: `(StockLevel so'roviga qo'shiladigan outerjoin'lar, shart)`.
    Qator kam: uning (ombor, mahsulot) juftligida `min_qty` bo'lsa — shu ombor qoldig'i bo'yicha,
    bo'lmasa — mahsulotning sozlamasiz omborlar yig'indisi bo'yicha."""
    wq = _wh_qty_subq(db, cid, wh_ids)
    rem_ids = _remainder_low_query(db, cid, wh_ids).with_entities(Product.id).subquery()
    own_low = and_(
        WSS.min_qty.isnot(None), WSS.min_qty > 0,
        func.coalesce(wq.c.qty, 0) <= WSS.min_qty,
    )
    cond = or_(
        own_low,
        and_(or_(WSS.id.is_(None), WSS.min_qty.is_(None)), StockLevel.product_id.in_(db.query(rem_ids.c.id))),
    )
    joins = [
        (WSS, and_(WSS.warehouse_id == StockLevel.warehouse_id, WSS.product_id == StockLevel.product_id)),
        (wq, and_(wq.c.warehouse_id == StockLevel.warehouse_id, wq.c.product_id == StockLevel.product_id)),
    ]
    return joins, cond


# ─── Python: sahifadagi qatorlar uchun min/max/bayroq ────────────────────────

def row_stock_info(db: Session, cid, wh_ids, stocks) -> Dict[int, dict]:
    """`StockLevel` qatorlari uchun `{stock.id: {min, max, is_low}}` (SQL bilan bir xil qoida).
    `min`/`max` — samarali qiymatlar (ombor sozlamasi yoki mahsulot)."""
    stocks = list(stocks)
    if not stocks:
        return {}
    pids = {s.product_id for s in stocks}
    sets = {
        (r.warehouse_id, r.product_id): r
        for r in db.query(WSS).join(Warehouse, Warehouse.id == WSS.warehouse_id)
        .filter(WSS.company_id == cid, WSS.product_id.in_(pids), *_scope_filters(cid, wh_ids)).all()
    }
    wq: Dict[tuple, Decimal] = {}
    for wid, pid, q in (
        db.query(StockLevel.warehouse_id, StockLevel.product_id, func.coalesce(func.sum(StockLevel.quantity), 0))
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .filter(StockLevel.product_id.in_(pids), *_scope_filters(cid, wh_ids))
        .group_by(StockLevel.warehouse_id, StockLevel.product_id).all()
    ):
        wq[(wid, pid)] = _dec(q)
    n_scope = _scope_warehouse_count(db, cid, wh_ids)
    ov_cnt: Dict[int, int] = {}
    rem_qty: Dict[int, Decimal] = {}
    for (wid, pid), st in sets.items():
        if st.min_qty is not None:
            ov_cnt[pid] = ov_cnt.get(pid, 0) + 1
    for (wid, pid), q in wq.items():
        st = sets.get((wid, pid))
        if st is None or st.min_qty is None:
            rem_qty[pid] = rem_qty.get(pid, Decimal(0)) + q

    out: Dict[int, dict] = {}
    for s in stocks:
        p = s.product
        st = sets.get((s.warehouse_id, s.product_id))
        pmin = _dec(p.min_stock)
        if st is not None and st.min_qty is not None:
            emin = _dec(st.min_qty)
            low = emin > 0 and wq.get((s.warehouse_id, s.product_id), Decimal(0)) <= emin
        else:
            emin = pmin
            has_rem = ov_cnt.get(s.product_id, 0) == 0 or n_scope - ov_cnt[s.product_id] > 0
            low = pmin > 0 and has_rem and rem_qty.get(s.product_id, Decimal(0)) <= pmin
        if st is not None and st.max_qty is not None:
            emax = _dec(st.max_qty)
        else:
            emax = _dec(p.max_stock) if p.max_stock is not None else None
        out[s.id] = {"min": emin, "max": emax, "is_low": bool(low)}
    return out


# ─── Kam qoldiqli mahsulotlar ro'yxati ───────────────────────────────────────

def low_stock_products(db: Session, cid, wh_ids, *, product_types=None,
                       limit: Optional[int] = None, skip: int = 0) -> List[dict]:
    """Kam qoldiqli birliklar (eng kritik — eng katta yetishmovchilik — birinchi).

    Ikki xil qator: `scope="product"` (sozlamasiz omborlar yig'indisi) va `scope="warehouse"`
    (ombor sozlamasi `min_qty` bo'lgan juftlik; `warehouse_id`/`warehouse_name` bilan).
    Qator: product_id, product_name, sku, barcode, unit, current_qty, min_stock, shortage, warehouses."""
    if wh_ids is not None and not wh_ids:
        return []
    fetch = None if limit is None else skip + limit

    # 1) sozlamasiz omborlar yig'indisi
    rq = _remainder_low_query(db, cid, wh_ids, product_types)
    rq = rq.order_by((rq.column_descriptions[1]["expr"] - Product.min_stock).asc(), Product.id.asc())
    if fetch is not None:
        rq = rq.limit(fetch)
    rem_rows = rq.all()
    pids = [p.id for p, _ in rem_rows]
    by_wh: Dict[int, list] = {pid: [] for pid in pids}
    if pids:
        for pid, wid, wname, wbranch, wqty in (
            db.query(StockLevel.product_id, Warehouse.id, Warehouse.name, Warehouse.branch_id,
                     func.coalesce(func.sum(StockLevel.quantity), 0))
            .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
            .filter(StockLevel.product_id.in_(pids), *_scope_filters(cid, wh_ids))
            .group_by(StockLevel.product_id, Warehouse.id, Warehouse.name, Warehouse.branch_id)
            .order_by(Warehouse.name, Warehouse.id).all()
        ):
            by_wh[pid].append({"warehouse_id": wid, "name": wname, "branch_id": wbranch, "qty": _dec(wqty)})
    result = []
    for p, qty in rem_rows:
        cur = _dec(qty)
        result.append({
            "scope": "product", "product_id": p.id, "product_name": p.name, "sku": p.sku, "barcode": p.barcode,
            "unit": p.unit, "current_qty": cur, "min_stock": _dec(p.min_stock),
            "shortage": _dec(p.min_stock) - cur, "warehouses": by_wh.get(p.id, []),
        })

    # 2) ombor sozlamasi bor juftliklar
    oq = _override_low_query(db, cid, wh_ids, product_types).subquery()
    pq = (
        db.query(Product, Warehouse, oq.c.qty, oq.c.min_v)
        .select_from(oq)
        .join(Product, Product.id == oq.c.product_id)
        .join(Warehouse, Warehouse.id == oq.c.warehouse_id)
        .order_by((oq.c.qty - oq.c.min_v).asc(), Product.id.asc(), Warehouse.id.asc())
    )
    if fetch is not None:
        pq = pq.limit(fetch)
    for p, w, qty, mv in pq.all():
        cur, mn = _dec(qty), _dec(mv)
        result.append({
            "scope": "warehouse", "product_id": p.id, "product_name": p.name, "sku": p.sku, "barcode": p.barcode,
            "unit": p.unit, "current_qty": cur, "min_stock": mn, "shortage": mn - cur,
            "warehouse_id": w.id, "warehouse_name": w.name,
            "warehouses": [{"warehouse_id": w.id, "name": w.name, "branch_id": w.branch_id, "qty": cur}],
        })

    result.sort(key=lambda r: (-r["shortage"], r["product_id"]))
    result = result[skip:]
    return result if limit is None else result[:limit]


# ─── Bitta ombor: samarali chegaralar (AI vositasi, to'ldirish) ──────────────

def warehouse_limits(db: Session, cid, warehouse_id: int, product_ids=None) -> Dict[int, dict]:
    """Bitta ombor uchun `{product_id: {min, max, current_qty}}` — samarali chegaralar.
    `product_ids` berilmasa: qoldig'i `<= samarali min` (min > 0) bo'lgan barcha mahsulotlar."""
    wq = _wh_qty_subq(db, cid, [warehouse_id])
    qty = func.coalesce(wq.c.qty, 0)
    emin, emax = effective_min(), effective_max()
    q = (
        db.query(Product.id, qty, emin, emax)
        .outerjoin(WSS, and_(WSS.product_id == Product.id, WSS.warehouse_id == warehouse_id))
        .outerjoin(wq, wq.c.product_id == Product.id)
        .filter(Product.company_id == cid, Product.is_deleted == False)  # noqa: E712
        .filter(func.coalesce(Product.product_type, "simple") != VIRTUAL_PRODUCT_TYPE)
    )
    if product_ids is not None:
        ids = list(product_ids)
        if not ids:
            return {}
        q = q.filter(Product.id.in_(ids))
    else:
        q = q.filter(emin > 0, qty <= emin)
    return {pid: {"min": _dec(mn), "max": None if mx is None else _dec(mx), "current_qty": _dec(cur)}
            for pid, cur, mn, mx in q.all()}


# ─── To'ldirish tavsiyasi ────────────────────────────────────────────────────

def replenishment(db: Session, cid, dest_wh_ids, *, source_warehouse_id: Optional[int] = None,
                  use_product_max: bool = False, limit: int = 1000) -> List[dict]:
    """Ombor sozlamasi bor (ombor, mahsulot) juftliklari uchun to'ldirish tavsiyasi.

    Juftlik tavsiyaga tushadi: samarali min > 0 va qoldiq <= min. Kerakli miqdor: `max` (faqat ombor
    sozlamasi `max_qty`; `use_product_max=True` bo'lsa `Product.max_stock` ham) bo'lsa `max - qoldiq`;
    bo'lmasa `reorder_qty`; bo'lmasa `min - qoldiq`. Manba: qatorning `source_warehouse_id`, bo'lmasa
    `source_warehouse_id` argumenti. Manbadan beriladigani: `min(kerak, manba qoldig'i - manbaning
    o'z samarali min'i)`; yetmagan qismi `purchase_needed`. Manba qoldig'i bir nechta qator o'rtasida
    kamayib boradi (eng katta yetishmovchilik birinchi)."""
    if dest_wh_ids is not None and not dest_wh_ids:
        return []
    wq = _wh_qty_subq(db, cid, dest_wh_ids)
    qty = func.coalesce(wq.c.qty, 0)
    emin = effective_min()
    q = (
        db.query(WSS, Product, Warehouse, qty.label("qty"), emin.label("emin"))
        .select_from(WSS)
        .join(Warehouse, Warehouse.id == WSS.warehouse_id)
        .join(Product, Product.id == WSS.product_id)
        .outerjoin(wq, and_(wq.c.warehouse_id == WSS.warehouse_id, wq.c.product_id == WSS.product_id))
        .filter(WSS.company_id == cid, Product.company_id == cid, Product.is_deleted == False,  # noqa: E712
                emin > 0, qty <= emin, *_scope_filters(cid, dest_wh_ids))
        .filter(func.coalesce(Product.product_type, "simple") != VIRTUAL_PRODUCT_TYPE)
        .order_by((qty - emin).asc(), WSS.id.asc())
    )
    rows = q.limit(limit).all()

    cands = []
    for st, p, w, cur_raw, emin_raw in rows:
        cur, mn = _dec(cur_raw), _dec(emin_raw)
        mx = _dec(st.max_qty) if st.max_qty is not None else (
            _dec(p.max_stock) if (use_product_max and p.max_stock is not None) else None)
        if mx is not None:
            need = mx - cur
        elif st.reorder_qty is not None:
            need = _dec(st.reorder_qty)
        else:
            need = mn - cur
        if need <= 0:
            continue
        src_id = st.source_warehouse_id or source_warehouse_id
        if src_id == w.id:
            src_id = None
        cands.append((st, p, w, cur, mn, mx, need, src_id))

    # Manba qoldiqlari va ularning o'z minimumi
    src_ids = {c[7] for c in cands if c[7]}
    src_avail: Dict[tuple, Decimal] = {}
    src_names: Dict[int, str] = {}
    src_info: Dict[tuple, tuple] = {}
    if src_ids:
        src_names = {i: n for i, n in db.query(Warehouse.id, Warehouse.name).filter(
            Warehouse.id.in_(src_ids), Warehouse.company_id == cid).all()}
        pids = {c[1].id for c in cands}
        sq = (
            db.query(StockLevel.warehouse_id, StockLevel.product_id, func.coalesce(func.sum(StockLevel.quantity), 0))
            .filter(StockLevel.warehouse_id.in_(src_ids), StockLevel.product_id.in_(pids))
            .group_by(StockLevel.warehouse_id, StockLevel.product_id).all()
        )
        sqty = {(w, p): _dec(v) for w, p, v in sq}
        smin = {
            (r.warehouse_id, r.product_id): r for r in db.query(WSS).filter(
                WSS.company_id == cid, WSS.warehouse_id.in_(src_ids), WSS.product_id.in_(pids)).all()
        }
        pmins = {c[1].id: _dec(c[1].min_stock) for c in cands}
        for sid in src_ids:
            for pid in pids:
                s_set = smin.get((sid, pid))
                s_min = _dec(s_set.min_qty) if (s_set is not None and s_set.min_qty is not None) else pmins[pid]
                have = sqty.get((sid, pid), Decimal(0))
                src_avail[(sid, pid)] = max(have - s_min, Decimal(0))
                src_info[(sid, pid)] = (have, s_min)

    out = []
    for st, p, w, cur, mn, mx, need, src_id in cands:
        give = Decimal(0)
        have = s_min = None
        if src_id and src_id in src_names:
            give = min(need, src_avail.get((src_id, p.id), Decimal(0)))
            src_avail[(src_id, p.id)] = src_avail.get((src_id, p.id), Decimal(0)) - give
            have, s_min = src_info.get((src_id, p.id), (None, None))
        else:
            src_id = None
        out.append({
            "warehouse_id": w.id, "warehouse_name": w.name, "branch_id": w.branch_id,
            "product_id": p.id, "product_name": p.name, "sku": p.sku, "unit": p.unit,
            "current_qty": float(cur), "min": float(mn), "max": None if mx is None else float(mx),
            "reorder_qty": None if st.reorder_qty is None else float(st.reorder_qty),
            "shortage": float(mn - cur), "need_qty": float(need),
            "source_warehouse_id": src_id, "source_warehouse_name": src_names.get(src_id) if src_id else None,
            "source_qty": None if have is None else float(have),
            "source_min": None if s_min is None else float(s_min),
            "transfer_qty": float(give), "purchase_needed": float(need - give),
        })
    return out
