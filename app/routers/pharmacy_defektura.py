"""Dorixona: defektura va buyurtma tavsiyasi (D4.3).

GET /api/pharmacy/defektura — tugagan yoki minimal qoldiqdan past (yagona ta'rif: `stock_report`/`stock_utils`,
ombor min/max sozlamalari bilan) va oxirgi `days` kunda sotilgan dorilar; o'rtacha kunlik sotuv,
tavsiya = ceil(o'rtacha × cover_days − joriy yaroqli qoldiq); oxirgi ta'minotchi va oxirgi kirim narxi.
Natija ta'minotchi bo'yicha guruhlanadi. Faqat o'qiydi (hech narsa yozmaydi); xarid qoralamasini
frontend mavjud `POST /api/purchase-orders` orqali yaratadi.

Faqat dorixona moduli yoqilgan korxonada ishlaydi (aks holda 403) — oddiy do'konga ta'sir yo'q.
"""
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.report_scope import effective_ctx
from app.database import get_db
from app.models.batch import Batch
from app.models.product import Product
from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.services import stock_report
from app.services.pharmacy import pharmacy_enabled

router = APIRouter(prefix="/pharmacy", tags=["Pharmacy"], dependencies=[Depends(get_branch_context)])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.warehouse)
PHARMACY_DISABLED = "Dorixona moduli yoqilmagan"

_ZERO = Decimal(0)


def _dec(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def _f(v: Decimal) -> float:
    return float(v)


def _now_naive() -> datetime:
    """Bazada vaqt UTC'da, tz-siz saqlanadi."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sold_qty(db: Session, cid: int, wh_ids: Optional[List[int]], since: datetime) -> Dict[int, Decimal]:
    """Oxirgi kunlarda sof sotilgan miqdor (qaytarilgani ayirilgan): {product_id: miqdor}."""
    wh_col = func.coalesce(SaleItem.warehouse_id, Sale.warehouse_id)
    net = SaleItem.quantity - func.coalesce(SaleItem.returned_quantity, 0)
    q = (
        db.query(SaleItem.product_id, func.coalesce(func.sum(net), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .filter(
            Sale.company_id == cid,
            Sale.status.in_([SaleStatus.completed, SaleStatus.partial_refund]),
            Sale.created_at >= since,
            Product.company_id == cid,
            Product.is_deleted == False,  # noqa: E712
            func.coalesce(Product.product_type, "simple") != stock_report.VIRTUAL_PRODUCT_TYPE,
        )
        .group_by(SaleItem.product_id)
    )
    if wh_ids is not None:
        q = q.filter(wh_col.in_(list(wh_ids)))
    return {pid: _dec(v) for pid, v in q.all() if _dec(v) > 0}


def _expired_qty(db: Session, cid: int, wh_ids: Optional[List[int]], pids: List[int]) -> Dict[int, Decimal]:
    """Muddati o'tgan partiyalardagi qoldiq (doira omborlarida): {product_id: miqdor}."""
    if not pids:
        return {}
    q = (
        db.query(Batch.product_id, func.coalesce(func.sum(Batch.quantity), 0))
        .join(Warehouse, Warehouse.id == Batch.warehouse_id)
        .filter(
            Batch.product_id.in_(pids), Batch.quantity > 0,
            Batch.expiry_date.isnot(None), Batch.expiry_date < _now_naive(),
            Warehouse.company_id == cid, Warehouse.is_active.isnot(False),
        )
        .group_by(Batch.product_id)
    )
    if wh_ids is not None:
        q = q.filter(Warehouse.id.in_(list(wh_ids)))
    return {pid: _dec(v) for pid, v in q.all()}


def _last_purchases(db: Session, cid: int, pids: List[int]) -> Dict[int, dict]:
    """Har mahsulot uchun oxirgi kirim (qabul qilingan xarid qatori): ta'minotchi, narx, sana."""
    if not pids:
        return {}
    last_ids = (
        db.query(func.max(POItem.id))
        .join(PurchaseOrder, PurchaseOrder.id == POItem.po_id)
        .filter(
            PurchaseOrder.company_id == cid,
            PurchaseOrder.status.in_([POStatus.received, POStatus.partial]),
            POItem.product_id.in_(pids), POItem.qty_received > 0,
        )
        .group_by(POItem.product_id)
        .subquery()
    )
    rows = (
        db.query(POItem.product_id, POItem.unit_cost, PurchaseOrder.created_at,
                 Supplier.id, Supplier.name)
        .join(PurchaseOrder, PurchaseOrder.id == POItem.po_id)
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .filter(POItem.id.in_(db.query(last_ids)))
        .all()
    )
    return {
        pid: {"last_cost": _dec(cost), "last_purchase_at": at, "supplier_id": sid, "supplier_name": sname}
        for pid, cost, at, sid, sname in rows
    }


@router.get("/defektura")
def defektura(
    branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
    warehouse_id: Optional[int] = Query(None, description="Faqat shu ombor"),
    days: int = Query(30, ge=1, le=365, description="Sotuv tahlili davri (kun)"),
    cover_days: int = Query(14, ge=1, le=365, description="Necha kunga yetadigan zaxira kerak"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    cid = current_user.company_id
    if not pharmacy_enabled(db, cid):
        raise HTTPException(status_code=403, detail=PHARMACY_DISABLED)
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, warehouse_id, ctx)

    whs = []
    if wh_ids is None or wh_ids:
        wq = db.query(Warehouse).filter(Warehouse.company_id == cid, Warehouse.is_active.isnot(False))
        if wh_ids is not None:
            wq = wq.filter(Warehouse.id.in_(list(wh_ids)))
        whs = [{"id": w.id, "name": w.name, "branch_id": w.branch_id} for w in wq.order_by(Warehouse.id).all()]

    result = {
        "branch_id": branch_id, "warehouse_id": warehouse_id, "days": days, "cover_days": cover_days,
        "warehouses": whs, "groups": [], "total_items": 0, "total_recommended_cost": 0.0,
    }
    if wh_ids is not None and not wh_ids:
        return result

    since = _now_naive() - timedelta(days=days)
    sold = _sold_qty(db, cid, wh_ids, since)
    if not sold:
        return result
    pids = list(sold.keys())

    # Yagona "kam qoldiq" ta'rifi (mahsulot min_stock / ombor sozlamasi): {product_id: min_stock}
    low_min: Dict[int, Decimal] = {}
    for r in stock_report.low_stock_products(db, cid, wh_ids):
        low_min[r["product_id"]] = max(low_min.get(r["product_id"], _ZERO), _dec(r["min_stock"]))

    totals = stock_report.product_stock_totals(db, cid, wh_ids, pids)
    expired = _expired_qty(db, cid, wh_ids, pids)
    valid: Dict[int, Decimal] = {}
    for pid in pids:
        total = totals.get(pid, _ZERO)
        valid[pid] = max(total - min(expired.get(pid, _ZERO), max(total, _ZERO)), _ZERO)

    cand = [pid for pid in pids if valid[pid] <= 0 or pid in low_min]
    if not cand:
        return result

    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(cand)).all()}
    purchases = _last_purchases(db, cid, cand)

    groups: Dict[Optional[int], dict] = {}
    for pid in cand:
        p = products.get(pid)
        if p is None:
            continue
        avg = sold[pid] / Decimal(days)
        cur = valid[pid]
        rec = max(Decimal(math.ceil(avg * Decimal(cover_days) - cur)), _ZERO)
        lp = purchases.get(pid)
        if lp:
            cost, cost_src = lp["last_cost"], "purchase"
        else:
            cost, cost_src = _dec(p.cost_price), "product"
        sid = lp["supplier_id"] if lp else None
        g = groups.setdefault(sid, {
            "supplier_id": sid,
            "supplier_name": (lp["supplier_name"] if lp else None),
            "items": [], "total_recommended": _ZERO, "estimated_cost": _ZERO,
        })
        g["items"].append({
            "product_id": pid, "product_name": p.name, "sku": p.sku, "barcode": p.barcode, "unit": p.unit,
            "product_type": p.product_type,
            "status": "out" if cur <= 0 else "low",
            "current_qty": _f(cur), "total_qty": _f(totals.get(pid, _ZERO)), "expired_qty": _f(expired.get(pid, _ZERO)),
            "min_stock": _f(low_min.get(pid, _dec(p.min_stock))),
            "sold_qty": _f(sold[pid]), "avg_daily": round(_f(avg), 3),
            "recommended_qty": _f(rec),
            "last_cost": _f(cost), "cost_source": cost_src,
            "last_purchase_at": lp["last_purchase_at"].isoformat() if lp and lp["last_purchase_at"] else None,
        })
        g["total_recommended"] += rec
        g["estimated_cost"] += rec * cost

    out_groups = []
    for g in groups.values():
        g["items"].sort(key=lambda i: (i["status"] != "out", -i["recommended_qty"], i["product_name"] or ""))
        g["total_recommended"] = _f(g["total_recommended"])
        g["estimated_cost"] = _f(g["estimated_cost"])
        out_groups.append(g)
    # Ta'minotchisizlar oxirida; qolganlari nomi bo'yicha
    out_groups.sort(key=lambda g: (g["supplier_id"] is None, (g["supplier_name"] or "").lower()))
    result["groups"] = out_groups
    result["total_items"] = sum(len(g["items"]) for g in out_groups)
    result["total_recommended_cost"] = sum(g["estimated_cost"] for g in out_groups)
    return result
