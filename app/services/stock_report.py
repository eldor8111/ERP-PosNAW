"""Ombor qoldig'i va kam zaxira hisobotlari uchun yagona qoidalar (T2.3).

Yagona "kam qoldiq" ta'rifi: **mahsulot** (variantlar yig'indisi) doira omborlari bo'yicha jami
qoldig'i `<= Product.min_stock` va `Product.min_stock > 0`. Doira — tanlangan ombor, yoki filial
omborlari, yoki butun korxona. `Product.is_deleted = false`, `product_type != 'sell'` (konversiya
orqali virtual mahsulot, o'z qoldig'i yo'q). Faqat faol (`is_active`) omborlar hisoblanadi.
Ombor bo'yicha alohida `min_stock` T4.4 ga qoladi.

Doira (`wh_ids`): `None` — butun korxona (faol omborlar), ro'yxat — shu omborlar, bo'sh ro'yxat —
hech narsa (filialida ombori yo'q yoki biriktirilmagan xodim).
"""
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.branch_context import BRANCH_FORBIDDEN, BRANCH_NOT_FOUND
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.warehouse import Warehouse
from app.services.warehouse_access import WAREHOUSE_BRANCH_FORBIDDEN, resolve_ctx

WAREHOUSE_NOT_FOUND = "Ombor topilmadi"
WAREHOUSE_BRANCH_MISMATCH = "Ombor tanlangan filialga tegishli emas"

# Qoldig'i o'zida saqlanmaydigan (konversiya orqali virtual) mahsulot turi
VIRTUAL_PRODUCT_TYPE = "sell"


def resolve_wh_scope(
    db: Session,
    user,
    cid: Optional[int],
    branch_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    ctx=None,
) -> Optional[List[int]]:
    """Hisobot doirasi: ombor id'lari ro'yxati yoki `None` (butun korxona).

    - `warehouse_id`: ombor korxonaniki bo'lishi shart (aks holda 404); `branch_id` ham berilsa va
      ombor shu filialniki bo'lmasa 400; cheklangan xodim uchun ruxsatsiz filial ombori — 403;
    - `branch_id`: filial korxonaniki (aks holda 404), cheklangan xodim uchun ruxsatsiz filial — 403;
      filialning omborlari qaytadi (`-1` — filialsiz omborlar guruhi);
    - ikkalasi ham berilmasa: cheklangan xodim uchun o'z filiali(lari) omborlari, aks holda `None`.
    """
    from app.services.pnl_service import UNASSIGNED_BRANCH

    ctx = resolve_ctx(db, user, ctx)
    allowed = ctx.allowed_branch_ids   # None — cheklanmagan

    if warehouse_id:
        wq = db.query(Warehouse).filter(Warehouse.id == warehouse_id)
        if cid is not None:
            wq = wq.filter(Warehouse.company_id == cid)
        wh = wq.first()
        if not wh:
            raise HTTPException(status_code=404, detail=WAREHOUSE_NOT_FOUND)
        if branch_id and branch_id != UNASSIGNED_BRANCH and wh.branch_id != branch_id:
            raise HTTPException(status_code=400, detail=WAREHOUSE_BRANCH_MISMATCH)
        if branch_id == UNASSIGNED_BRANCH and wh.branch_id is not None:
            raise HTTPException(status_code=400, detail=WAREHOUSE_BRANCH_MISMATCH)
        if allowed is not None and wh.branch_id not in allowed:
            raise HTTPException(status_code=403, detail=WAREHOUSE_BRANCH_FORBIDDEN)
        return [wh.id]

    if branch_id:
        if branch_id == UNASSIGNED_BRANCH:
            cond = Warehouse.branch_id.is_(None)
            if allowed is not None:
                raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        else:
            bq = db.query(Branch.id).filter(Branch.id == branch_id)
            if cid is not None:
                bq = bq.filter(Branch.company_id == cid)
            if not bq.first():
                raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
            if allowed is not None and branch_id not in allowed:
                raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
            cond = Warehouse.branch_id == branch_id
        rows = db.query(Warehouse.id).filter(cond, Warehouse.company_id == cid).order_by(Warehouse.id).all()
        return [r[0] for r in rows]

    ids = ctx.scope_ids()
    if ids is None:
        return None
    if not ids:
        return []
    rows = db.query(Warehouse.id).filter(
        Warehouse.company_id == cid, Warehouse.branch_id.in_(list(ids)),
    ).order_by(Warehouse.id).all()
    return [r[0] for r in rows]


# ─── Kam qoldiq ──────────────────────────────────────────────────────────────

def _scope_filters(cid, wh_ids):
    """Faol ombor + doira sharti (StockLevel Warehouse bilan join qilingan so'rovlar uchun)."""
    conds = [Warehouse.company_id == cid, Warehouse.is_active.isnot(False)]
    if wh_ids is not None:
        conds.append(Warehouse.id.in_(list(wh_ids)))
    return conds


def low_stock_subquery(db: Session, cid, wh_ids, product_types=None):
    """Kam qoldiqli mahsulot id'lari — C4.1 (T4.4): yagona ta'rif `app.utils.stock_utils` da (ombor sozlamalari bilan)."""
    from app.utils import stock_utils
    return stock_utils.low_stock_subquery(db, cid, wh_ids, product_types)


def low_stock_count(db: Session, cid, wh_ids, *, product_types=None) -> int:
    """Kam qoldiqli MAHSULOTLAR soni (qator emas) — `stock_utils.low_stock_count` ga yo'naltirilgan (C4.1)."""
    from app.utils import stock_utils
    return stock_utils.low_stock_count(db, cid, wh_ids, product_types=product_types)


def low_stock_products(
    db: Session,
    cid,
    wh_ids,
    *,
    product_types=None,
    limit: Optional[int] = None,
    skip: int = 0,
) -> List[dict]:
    """Kam qoldiqli mahsulotlar (eng kritik birinchi) — `stock_utils.low_stock_products` ga yo'naltirilgan (C4.1).

    Qator: product_id, product_name, sku, barcode, unit, current_qty, min_stock, shortage, warehouses
    va `scope` (`product` | `warehouse`; `warehouse` bo'lsa `warehouse_id`/`warehouse_name` ham)."""
    from app.utils import stock_utils
    return stock_utils.low_stock_products(db, cid, wh_ids, product_types=product_types, limit=limit, skip=skip)


def product_stock_totals(db: Session, cid, wh_ids, product_ids) -> Dict[int, Decimal]:
    """Berilgan mahsulotlar uchun doiradagi jami qoldiq (faol omborlar)."""
    pids = list(product_ids)
    if not pids or (wh_ids is not None and not wh_ids):
        return {}
    rows = (
        db.query(StockLevel.product_id, func.coalesce(func.sum(StockLevel.quantity), 0))
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .filter(StockLevel.product_id.in_(pids), *_scope_filters(cid, wh_ids))
        .group_by(StockLevel.product_id)
        .all()
    )
    return {pid: Decimal(str(total or 0)) for pid, total in rows}


# ─── Qoldiq hisoboti ─────────────────────────────────────────────────────────

def _cost_maps(db: Session, cid, wh_ids=None):
    """Tannarx xaritalari: `(product, ombor)` partiyalari o'rtachasi va korxona o'rtachasi.
    Partiya narxi `Batch.warehouse_id` bo'yicha (indeks `ix_batch_product_wh_qty`)."""
    rows = (
        db.query(
            Batch.product_id,
            Batch.warehouse_id,
            func.sum(Batch.quantity * Batch.purchase_price).label("total_cost"),
            func.sum(Batch.quantity).label("total_qty"),
        )
        .filter(Batch.company_id == cid, Batch.quantity > 0)
        .group_by(Batch.product_id, Batch.warehouse_id)
        .all()
    )
    wh_cost: dict = {}
    co_cost: dict = {}
    co_qty: dict = {}
    for r in rows:
        tq = float(r.total_qty or 0)
        if tq <= 0:
            continue
        tc = float(r.total_cost or 0)
        co_cost[r.product_id] = co_cost.get(r.product_id, 0.0) + tc
        co_qty[r.product_id] = co_qty.get(r.product_id, 0.0) + tq
        if r.warehouse_id is not None:
            wh_cost[(r.product_id, r.warehouse_id)] = tc / tq
    co_avg = {pid: co_cost[pid] / co_qty[pid] for pid in co_qty if co_qty[pid] > 0}
    return wh_cost, co_avg


def _unit_cost(maps, product_id, warehouse_id, product_cost_price):
    """Tannarx tartibi: shu ombor partiyalari o'rtachasi -> korxona o'rtachasi -> Product.cost_price."""
    wh_cost, co_avg = maps
    if (product_id, warehouse_id) in wh_cost:
        return wh_cost[(product_id, warehouse_id)], "batch_wh"
    if product_id in co_avg:
        return co_avg[product_id], "batch_company"
    return float(product_cost_price or 0), "product"


def _inventory_base(db: Session, cid, wh_ids):
    return (
        db.query(StockLevel, Product, Warehouse)
        .join(Product, Product.id == StockLevel.product_id)
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .filter(Product.company_id == cid, Product.is_deleted == False,  # noqa: E712
                *_scope_filters(cid, wh_ids))
    )


def inventory_rows(db: Session, cid, wh_ids, skip: int = 0, limit: int = 5000):
    """Qoldiq qatorlari `(mahsulot, variant, ombor)` kesimida: `(jami_qatorlar, [qator])`.

    Qator: stock, product, variant, warehouse, branch_name, quantity, unit_cost, value,
    cost_basis (`batch_wh|batch_company|product`), is_low (ombor sozlamalari bilan, stock_utils.row_stock_info)."""
    if wh_ids is not None and not wh_ids:
        return 0, []
    base = _inventory_base(db, cid, wh_ids)
    total = base.with_entities(func.count(StockLevel.id)).scalar() or 0
    page = (
        base.outerjoin(ProductVariant, ProductVariant.id == StockLevel.variant_id)
        .outerjoin(Branch, Branch.id == Warehouse.branch_id)
        .with_entities(StockLevel, Product, Warehouse, ProductVariant.name, Branch.name)
        .order_by(StockLevel.quantity, StockLevel.id)
        .offset(skip).limit(limit)
        .all()
    )
    maps = _cost_maps(db, cid)
    # C4.1 (T4.4): "kam" bayrog'i ombor sozlamalarini hisobga oluvchi yagona qoida (stock_utils) bo'yicha
    from app.utils import stock_utils
    info = stock_utils.row_stock_info(db, cid, wh_ids, [row[0] for row in page])
    out = []
    for s, p, w, vname, bname in page:
        qty = float(s.quantity or 0)
        unit_cost, basis = _unit_cost(maps, p.id, w.id, p.cost_price)
        out.append({
            "stock": s, "product": p, "warehouse": w,
            "variant_id": s.variant_id, "variant_name": vname, "branch_name": bname,
            "quantity": qty, "unit_cost": unit_cost, "cost_basis": basis,
            "value": round(qty * unit_cost, 2),
            "is_low": bool(info.get(s.id, {}).get("is_low", False)),
        })
    return int(total), out


def inventory_summary(db: Session, cid, wh_ids) -> dict:
    """Doiradagi qoldiq xulosasi: `{total_value, total_qty, sku_count, by_warehouse[], by_branch[]}`.
    `total_value` qator qiymatlari (`inventory_rows`) yig'indisiga teng."""
    empty = {"total_value": 0.0, "total_qty": 0.0, "sku_count": 0, "by_warehouse": [], "by_branch": []}
    if wh_ids is not None and not wh_ids:
        return empty
    maps = _cost_maps(db, cid)
    by_wh: dict = {}
    by_br: dict = {}
    skus = set()
    # Qator qiymatlari (mahsulot x ombor x variant) yaxlitlanadi; xulosa ham shu yig'indi
    var_rows = (
        _inventory_base(db, cid, wh_ids)
        .outerjoin(Branch, Branch.id == Warehouse.branch_id)
        .with_entities(StockLevel.product_id, Warehouse.id, Warehouse.name, Warehouse.branch_id, Branch.name,
                       Product.cost_price, StockLevel.quantity)
        .all()
    )
    total_value = 0.0
    total_qty = 0.0
    for pid, wid, wname, bid, bname, cost_price, qraw in var_rows:
        qty = float(qraw or 0)
        unit_cost, _ = _unit_cost(maps, pid, wid, cost_price)
        value = round(qty * unit_cost, 2)
        total_value += value
        total_qty += qty
        if qty != 0:
            skus.add(pid)
        w = by_wh.setdefault(wid, {"warehouse_id": wid, "warehouse_name": wname, "branch_id": bid,
                                   "branch_name": bname, "value": 0.0, "qty": 0.0, "_skus": set()})
        w["value"] += value
        w["qty"] += qty
        if qty != 0:
            w["_skus"].add(pid)
        b = by_br.setdefault(bid, {"branch_id": bid, "branch_name": bname, "value": 0.0, "qty": 0.0, "_skus": set()})
        b["value"] += value
        b["qty"] += qty
        if qty != 0:
            b["_skus"].add(pid)

    def _fin(d):
        d["sku_count"] = len(d.pop("_skus"))
        d["value"] = round(d["value"], 2)
        d["qty"] = round(d["qty"], 3)
        return d

    return {
        "total_value": round(total_value, 2),
        "total_qty": round(total_qty, 3),
        "sku_count": len(skus),
        "by_warehouse": sorted((_fin(d) for d in by_wh.values()), key=lambda d: (-d["value"], d["warehouse_id"])),
        "by_branch": sorted((_fin(d) for d in by_br.values()), key=lambda d: (-d["value"], d["branch_id"] or 0)),
    }


# ─── AI / Telegram hisobotlari uchun ─────────────────────────────────────────

def scope_wh_ids(scope) -> Optional[List[int]]:
    """`AIScope` (T2.9) doirasi -> ombor id'lari (`None` — butun korxona)."""
    return None if scope is None else [int(w) for w in scope.warehouse_ids]


def low_stock_count_for_scope(db: Session, cid, scope) -> int:
    """AI/Telegram hisobotlaridagi "kam qoldiq" soni — hamma joydagi bilan bir xil ta'rif."""
    return low_stock_count(db, cid, scope_wh_ids(scope))
