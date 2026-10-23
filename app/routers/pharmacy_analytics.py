"""Dorixona: modda, ishlab chiqaruvchi va ustama tahlili (D4.5).

GET /api/pharmacy/analytics/sales?from&to&group=substance|manufacturer|country&branch_id —
sotuvni modda / ishlab chiqaruvchi / mamlakat bo'yicha guruhlaydi: sof miqdor (qaytarilgani ayirilgan),
tushum, tannarx (SaleItem.cost_price), marja va ustama.
GET /api/pharmacy/analytics/summary?branch_id — qisqa ko'rsatkichlar: muddati yaqinlashgan / o'tgan
partiyalar, defektura soni, bugungi retseptli sotuvlar.

Faqat o'qiydi. Faqat dorixona moduli yoqilgan korxonada ishlaydi (aks holda 403) — oddiy do'konga ta'sir yo'q.
"""
from datetime import date, datetime, time, timedelta, timezone
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
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.services import stock_report
from app.services.pharmacy import pharmacy_context

router = APIRouter(prefix="/pharmacy/analytics", tags=["Pharmacy"], dependencies=[Depends(get_branch_context)])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.warehouse)
PHARMACY_DISABLED = "Dorixona moduli yoqilmagan"
GROUPS = ("substance", "manufacturer", "country")
SOLD_STATUSES = (SaleStatus.completed, SaleStatus.partial_refund)

_ZERO = Decimal(0)


def _dec(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def _f(v: Decimal) -> float:
    return float(v)


def _now_naive() -> datetime:
    """Bazada vaqt UTC'da, tz-siz saqlanadi."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sold_scope(q, cid: int, wh_ids: Optional[List[int]]):
    """Sotuv qatorlari so'roviga umumiy shartlar: korxona, holat, virtual mahsulot emas, ombor doirasi."""
    wh_col = func.coalesce(SaleItem.warehouse_id, Sale.warehouse_id)
    q = q.filter(
        Sale.company_id == cid,
        Sale.status.in_(SOLD_STATUSES),
        Product.company_id == cid,
        Product.is_deleted == False,  # noqa: E712
        func.coalesce(Product.product_type, "simple") != stock_report.VIRTUAL_PRODUCT_TYPE,
    )
    if wh_ids is not None:
        q = q.filter(wh_col.in_(list(wh_ids)))
    return q


def _check_enabled(db: Session, cid: int) -> dict:
    enabled, settings = pharmacy_context(db, cid)
    if not enabled:
        raise HTTPException(status_code=403, detail=PHARMACY_DISABLED)
    return settings


def _metrics(qty: Decimal, revenue: Decimal, cost: Decimal) -> dict:
    margin = revenue - cost
    return {
        "quantity": _f(qty), "revenue": _f(revenue), "cost": _f(cost), "margin": _f(margin),
        # marja = foyda / tushum; ustama = foyda / tannarx (bo'luvchi 0 bo'lsa — None)
        "margin_pct": round(_f(margin / revenue * 100), 2) if revenue > 0 else None,
        "markup_pct": round(_f(margin / cost * 100), 2) if cost > 0 else None,
    }


def _label(v: Optional[str]) -> Optional[str]:
    v = (v or "").strip()
    return v or None


@router.get("/sales")
def sales_analytics(
    date_from: Optional[date] = Query(None, alias="from", description="Boshlanish sanasi (standart: to - 29 kun)"),
    date_to: Optional[date] = Query(None, alias="to", description="Tugash sanasi, shu kun ham kiradi (standart: bugun)"),
    group: str = Query("substance", pattern="^(substance|manufacturer|country)$"),
    branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    cid = current_user.company_id
    _check_enabled(db, cid)
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, None, ctx)

    d_to = date_to or _now_naive().date()
    d_from = date_from or (d_to - timedelta(days=29))
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="Boshlanish sanasi tugash sanasidan keyin bo'lmasligi kerak")

    result = {
        "group": group, "from": d_from.isoformat(), "to": d_to.isoformat(), "branch_id": branch_id,
        # modda bo'yicha: bitta dori bir necha moddadan iborat bo'lsa, har bir moddaga to'liq yoziladi
        "overlap": group == "substance",
        "groups": [], "total": _metrics(_ZERO, _ZERO, _ZERO),
    }
    if wh_ids is not None and not wh_ids:
        return result

    # Mahsulot kesimida sof miqdor / tushum / tannarx (qaytarilgan ulush ayirilgan)
    qty = SaleItem.quantity
    net = SaleItem.quantity - func.coalesce(SaleItem.returned_quantity, 0)
    rev = func.sum(SaleItem.subtotal * net / qty)
    q = (
        db.query(SaleItem.product_id, func.sum(net), rev, func.sum(SaleItem.cost_price * net))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .filter(
            Sale.created_at >= datetime.combine(d_from, time.min),
            Sale.created_at < datetime.combine(d_to + timedelta(days=1), time.min),
            qty > 0,
        )
        .group_by(SaleItem.product_id)
    )
    rows = _sold_scope(q, cid, wh_ids).all()
    per_product: Dict[int, tuple] = {
        pid: (_dec(n), _dec(r), _dec(c)) for pid, n, r, c in rows if _dec(n) > 0
    }
    if not per_product:
        return result
    pids = list(per_product.keys())

    # Mahsulot -> guruh kalitlari. Kalit None = "ko'rsatilmagan".
    keys: Dict[int, List[tuple]] = {pid: [] for pid in pids}   # pid -> [(kalit, nom)]
    if group == "substance":
        subs = (
            db.query(ProductSubstance.product_id, PharmaSubstance.id, PharmaSubstance.name_uz)
            .join(PharmaSubstance, PharmaSubstance.id == ProductSubstance.substance_id)
            .filter(
                ProductSubstance.product_id.in_(pids),
                (PharmaSubstance.company_id.is_(None)) | (PharmaSubstance.company_id == cid),
            )
            .all()
        )
        for pid, sid, name in subs:
            keys[pid].append((f"s{sid}", name))
    else:
        col = ProductPharma.manufacturer if group == "manufacturer" else ProductPharma.country
        for pid, val in (
            db.query(ProductPharma.product_id, col)
            .filter(ProductPharma.company_id == cid, ProductPharma.product_id.in_(pids))
            .all()
        ):
            name = _label(val)
            if name:
                keys[pid].append((name.lower(), name))

    acc: Dict[Optional[str], dict] = {}
    for pid, (n, r, c) in per_product.items():
        for key, name in (keys[pid] or [(None, None)]):
            g = acc.setdefault(key, {"key": key, "name": name, "qty": _ZERO, "rev": _ZERO, "cost": _ZERO, "products": 0})
            g["qty"] += n
            g["rev"] += r
            g["cost"] += c
            g["products"] += 1

    out = []
    for g in acc.values():
        item = {"key": g["key"], "name": g["name"], "products_count": g["products"]}
        item.update(_metrics(g["qty"], g["rev"], g["cost"]))
        out.append(item)
    out.sort(key=lambda x: (x["name"] is None, -x["revenue"], x["name"] or ""))   # ko'rsatilmagan oxirida

    tq = sum((v[0] for v in per_product.values()), _ZERO)
    tr = sum((v[1] for v in per_product.values()), _ZERO)
    tc = sum((v[2] for v in per_product.values()), _ZERO)
    result["groups"] = out
    result["total"] = _metrics(tq, tr, tc)
    return result


@router.get("/summary")
def summary(
    branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
    ctx: BranchContext = Depends(get_branch_context),
):
    cid = current_user.company_id
    settings = _check_enabled(db, cid)
    warn_days = int(settings.get("expiry_warn_days") or 0)
    ctx = effective_ctx(current_user, ctx)
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, None, ctx)

    result = {
        "branch_id": branch_id, "expiry_warn_days": warn_days,
        "expiring_batches": 0, "expired_batches": 0, "defektura_count": 0, "rx_sales_today": 0,
    }
    if wh_ids is not None and not wh_ids:
        return result

    now = _now_naive()

    # Muddati yaqin / o'tgan partiyalar (qoldig'i bor, faol omborlarda)
    bq = (
        db.query(Batch.id, Batch.expiry_date)
        .join(Warehouse, Warehouse.id == Batch.warehouse_id)
        .join(Product, Product.id == Batch.product_id)
        .filter(
            Batch.quantity > 0, Batch.expiry_date.isnot(None),
            Warehouse.company_id == cid, Warehouse.is_active.isnot(False),
            Product.company_id == cid, Product.is_deleted == False,  # noqa: E712
        )
    )
    if wh_ids is not None:
        bq = bq.filter(Warehouse.id.in_(list(wh_ids)))
    limit = now + timedelta(days=warn_days)
    expired = expiring = 0
    for _bid, exp in bq.all():
        if exp < now:
            expired += 1
        elif exp <= limit:
            expiring += 1
    result["expired_batches"] = expired
    result["expiring_batches"] = expiring

    # Defektura: oxirgi 30 kunda sotilgan, lekin tugagan yoki minimal qoldiqdan past dorilar
    since = now - timedelta(days=30)
    sq = (
        db.query(SaleItem.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .filter(Sale.created_at >= since)
        .group_by(SaleItem.product_id)
        .having(func.sum(SaleItem.quantity - func.coalesce(SaleItem.returned_quantity, 0)) > 0)
    )
    sold_pids = [pid for (pid,) in _sold_scope(sq, cid, wh_ids).all()]
    if sold_pids:
        low = {r["product_id"] for r in stock_report.low_stock_products(db, cid, wh_ids)}
        totals = stock_report.product_stock_totals(db, cid, wh_ids, sold_pids)
        result["defektura_count"] = sum(
            1 for pid in sold_pids if totals.get(pid, _ZERO) <= 0 or pid in low
        )

    # Bugungi retseptli sotuvlar: retseptli (is_rx) dori sotilgan cheklar soni.
    # D2.5 (retsept jadvali) tayyor bo'lmaguncha mahsulot belgisi bo'yicha hisoblanadi.
    day0 = datetime.combine(now.date(), time.min)
    rq = (
        db.query(func.count(func.distinct(Sale.id)))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .join(ProductPharma, ProductPharma.product_id == SaleItem.product_id)
        .filter(Sale.created_at >= day0, ProductPharma.is_rx == True)  # noqa: E712
    )
    result["rx_sales_today"] = int(_sold_scope(rq, cid, wh_ids).scalar() or 0)
    return result
