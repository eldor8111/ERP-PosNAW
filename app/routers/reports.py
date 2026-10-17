"""
Reports API — asosiy hisobotlar: Dashboard, Sotuvlar, Qaytarishlar, Ombor,
Stok ogohlantirishlari, O'lik stok, Xaridlar, Mahsulotlar (Sotuv).
Moliya hisobotlari → finance_report.py
Sotuv tahlili → sales_report.py
Valyuta, qaytarish hujjatlari va vaqt qoidalari → app/utils/report_utils.py
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import exists, func, case, cast, Date as DateType, select
from sqlalchemy.orm import Session, joinedload

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.report_scope import (
    ReportScope, effective_ctx, report_scope_dep, resolve_report_scope, restricted_branch_ids,
)
from app.core.roles import DASHBOARD_ROLES, REPORT_ROLES
from app.database import get_db
from app.models.customer import Customer
from app.models.inventory import StockLevel, StockMovement
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, POStatus
from app.models.sale import Sale, SaleItem
from app.models.batch import Batch
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.services import stock_report
from app.utils.report_utils import (
    _today_range, _date_range, local_today, local_day_start,
    is_return_doc, sale_doc_filter, return_doc_filter, sale_or_return_filter, doc_sign,
    sale_rate, item_revenue_uzs, item_cost_uzs,
    branch_warehouse_ids, sale_branch_filter, currency_code_map, load_debtors,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


def _code(codes: dict, currency_id) -> str:
    return codes.get(currency_id, "UZS") if currency_id else "UZS"


# ─── O'lik stok (Dashboard va hisobot uchun umumiy) ──────────────────────────

def _dead_stock_query(db: Session, company_id: int, months: int, wh_ids: Optional[list]):
    """O'lik stok so'rovi `(Product, qty)`: "sotilgan" tekshiruvi ham qoldiq bilan BIR XIL doirada
    (T2.3: boshqa filialdagi sotuv tanlangan filialdagi yotgan tovarni yashirmaydi). `NOT EXISTS` —
    NULL xavfsiz va `NOT IN (subquery)` dan tezroq."""
    cutoff = local_day_start(local_today()) - timedelta(days=months * 30)
    mv_conds = [
        StockMovement.product_id == Product.id,
        StockMovement.reference_type == "sale",
        StockMovement.created_at >= cutoff,
    ]
    item_conds = [
        SaleItem.product_id == Product.id,
        Sale.company_id == company_id,
        sale_doc_filter(),
        Sale.created_at >= cutoff,
    ]
    if wh_ids is not None:
        # StockMovement.warehouse_id NULL bo'lgan eski yozuvlar filial doirasida hisobga olinmaydi (T1.7 backfill)
        mv_conds.append(StockMovement.warehouse_id.in_(wh_ids))
        item_conds.append(func.coalesce(SaleItem.warehouse_id, Sale.warehouse_id).in_(wh_ids))
    sold_by_movement = exists().where(*mv_conds)
    sold_by_items = exists(select(SaleItem.id).join(Sale, Sale.id == SaleItem.sale_id).where(*item_conds))
    qty_sum = func.sum(StockLevel.quantity)
    q = (
        db.query(Product, qty_sum.label("qty"))
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(
            Product.company_id == company_id,
            Product.is_deleted == False,
            StockLevel.quantity > 0,
            (Product.created_at.is_(None)) | (Product.created_at < cutoff),
            ~sold_by_movement,
            ~sold_by_items,
        )
    )
    from sqlalchemy import or_ as _or_
    q = q.filter(_or_(StockLevel.warehouse_id.is_(None), StockLevel.warehouse.has(is_active=True)))
    if wh_ids is not None:
        q = q.filter(StockLevel.warehouse_id.in_(wh_ids))
    return q.group_by(Product.id).having(qty_sum > 0)


def _dead_stock_rows(db: Session, company_id: int, months: int, wh_ids: Optional[list]):
    """N oy davomida sotilmagan, qoldig'i bor mahsulotlar: [(Product, qty)].

    "Sotilgan" — ombordan sotuv bilan chiqqan (StockMovement): tarkibiy (sell)
    mahsulot sotilganda manba mahsulot shu yerda ko'rinadi. SaleItem ham
    hisobga olinadi. Oynadan keyin qo'shilgan yangi mahsulotlar kirmaydi.
    """
    return _dead_stock_query(db, company_id, months, wh_ids).all()


def dead_stock_count(db: Session, company_id: int, wh_ids: Optional[list], months: int = 6) -> int:
    """O'lik stokli mahsulotlar soni — SQL `count(*)` (ro'yxatni Python'ga yuklamaydi)."""
    sub = _dead_stock_query(db, company_id, months, wh_ids).with_entities(Product.id).subquery()
    return int(db.query(func.count()).select_from(sub).scalar() or 0)


def _batch_avg_costs(db: Session, company_id: int, product_ids: list, wh_ids: Optional[list]) -> dict:
    """Mahsulotning qolgan partiyalari bo'yicha o'rtacha tannarxi (UZS)."""
    if not product_ids:
        return {}
    q = (
        db.query(
            Batch.product_id,
            func.sum(Batch.quantity * Batch.purchase_price).label("total_cost"),
            func.sum(Batch.quantity).label("total_qty"),
        )
        .filter(Batch.company_id == company_id, Batch.quantity > 0, Batch.product_id.in_(product_ids))
    )
    if wh_ids is not None:
        q = q.filter(Batch.warehouse_id.in_(wh_ids))
    result = {}
    for row in q.group_by(Batch.product_id).all():
        if row.total_qty and float(row.total_qty) > 0:
            result[row.product_id] = float(row.total_cost) / float(row.total_qty)
    return result


# ─── Filial doirasi (T2.1) ───────────────────────────────────────────────────

@router.get("/scope")
def get_report_scope(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Frontend filial selektorini shunga qarab qulflaydi: `restricted` — foydalanuvchi o'z filiali
    bilan cheklangan, `branch_id` — majburiy filial, `can_select_all` — "Butun korxona" mumkin."""
    allowed = restricted_branch_ids(db, current_user)
    if allowed is None:
        return {"restricted": False, "branch_id": None, "can_select_all": True, "allowed_branch_ids": None}
    scope = resolve_report_scope(db, current_user, None)
    return {
        "restricted": True,
        "branch_id": scope.branch_id,
        "can_select_all": False,
        "allowed_branch_ids": list(allowed),
    }


# ─── Dashboard ───────────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filtr (None = hammasi)"),
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*DASHBOARD_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Direktor uchun asosiy ko'rsatkichlar"""
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches — kontekst cheklovisiz
    today_start, today_end = _today_range()
    today = local_today()
    cid = current_user.company_id

    # T2.3: ombor korxonaniki (404), tanlangan filialniki (400) va ruxsat doirasida (403) bo'lishi shart
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, warehouse_id, ctx)
    base = [Sale.company_id == cid]
    # T1.9: sotuv filtri — ombor aniq berilsa ombor bo'yicha, aks holda Sale.branch_id snapshot'i bo'yicha
    # (wh_ids qoldiq/dead-stock hisoblari uchun qoladi)
    if warehouse_id:
        base.append(Sale.warehouse_id == warehouse_id)
    elif branch_id:
        base.append(sale_branch_filter(branch_id))
    elif wh_ids is not None:
        # filialga biriktirilgan xodim: doira doim o'z filiali omborlari
        base.append(Sale.warehouse_id.in_(wh_ids))

    codes = currency_code_map(db, cid)

    def _sales_summary(start, end=None):
        """(soni, {valyuta: sotuv valyutasidagi summa}, UZS jami) — sotuv hujjatlari."""
        q = db.query(
            Sale.currency_id,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_amount / sale_rate()), 0),
            func.coalesce(func.sum(Sale.total_amount), 0),
        ).filter(*base, sale_doc_filter(), Sale.created_at >= start)
        if end is not None:
            q = q.filter(Sale.created_at < end)
        count, by_currency, total_uzs = 0, {}, 0.0
        for currency_id, cnt, amount, amount_uzs in q.group_by(Sale.currency_id).all():
            code = _code(codes, currency_id)
            by_currency[code] = by_currency.get(code, 0.0) + float(amount)
            count += cnt
            total_uzs += float(amount_uzs)
        return count, by_currency, total_uzs

    today_count, today_by_currency, today_uzs = _sales_summary(today_start, today_end)
    _, _, yesterday_uzs = _sales_summary(today_start - timedelta(days=1), today_start)
    today_change = round((today_uzs - yesterday_uzs) / yesterday_uzs * 100, 1) if yesterday_uzs > 0 else None

    # Kunlik trend (UZS) — oxirgi 30 kun, haftalik ham shundan olinadi
    trend_rows = (
        db.query(
            cast(Sale.created_at, DateType).label("day"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
            func.count(Sale.id).label("count"),
        )
        .filter(*base, sale_doc_filter(), Sale.created_at >= local_day_start(today - timedelta(days=29)))
        .group_by(cast(Sale.created_at, DateType))
        .all()
    )
    trend_map = {str(r.day): (float(r.total), r.count) for r in trend_rows}
    weekly_data = []
    for i in range(7):
        day = today - timedelta(days=6 - i)
        total, count = trend_map.get(str(day), (0.0, 0))
        weekly_data.append({"date": day.strftime("%d.%m"), "amount": total, "count": count})
    monthly_trend = []
    for i in range(30):
        day = today - timedelta(days=29 - i)
        monthly_trend.append({"date": day.strftime("%d.%m"), "amount": trend_map.get(str(day), (0.0, 0))[0]})

    month_start = local_day_start(today.replace(day=1))
    month_count, month_by_currency, _ = _sales_summary(month_start)
    month_profit = (
        db.query(func.coalesce(func.sum(doc_sign() * (item_revenue_uzs() - item_cost_uzs())), 0))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*base, sale_or_return_filter(), Sale.created_at >= month_start)
        .scalar()
    )

    top_revenue = func.sum(doc_sign() * item_revenue_uzs())
    top_rows = (
        db.query(
            Product.name,
            top_revenue.label("revenue"),
            func.sum(doc_sign() * SaleItem.quantity).label("qty"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*base, sale_or_return_filter(), Sale.created_at >= month_start)
        .group_by(Product.id, Product.name)
        .order_by(top_revenue.desc())
        .limit(10)
        .all()
    )

    # T2.3: yagona "kam qoldiq" ta'rifi — mahsulot darajasida (variant va omborlar yig'indisi)
    low_stock_total = stock_report.low_stock_count(db, cid, wh_ids)
    low_stock_rows = stock_report.low_stock_products(db, cid, wh_ids, limit=20)

    dead_stock_total = dead_stock_count(db, cid, wh_ids)

    cashier_rows = (
        db.query(
            User.id,
            User.name,
            Sale.currency_id,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total_amount / sale_rate()), 0),
            func.coalesce(func.sum(Sale.total_amount), 0),
        )
        .join(Sale, Sale.cashier_id == User.id)
        .filter(*base, sale_doc_filter(), Sale.created_at >= month_start)
        .group_by(User.id, User.name, Sale.currency_id)
        .all()
    )
    cashier_map = {}
    for uid, name, currency_id, cnt, amount, amount_uzs in cashier_rows:
        entry = cashier_map.setdefault(uid, {"cashier_id": uid, "name": name, "count": 0, "totals": {}, "_uzs": 0.0})
        code = _code(codes, currency_id)
        entry["count"] += cnt
        entry["totals"][code] = entry["totals"].get(code, 0.0) + float(amount)
        entry["_uzs"] += float(amount_uzs)
    cashier_perf = sorted(cashier_map.values(), key=lambda e: e["_uzs"], reverse=True)[:10]
    for entry in cashier_perf:
        entry.pop("_uzs")

    product_count = db.query(func.count(Product.id)).filter(Product.is_deleted == False, Product.company_id == cid).scalar()

    # Mijozlar qarzi — Mijozlar sahifasi bilan bir xil manba (debt_balances)
    debtors = load_debtors(db, Customer, cid)
    debt_by_currency = {}
    for _, balances in debtors:
        for code, amt in balances.items():
            debt_by_currency[code] = debt_by_currency.get(code, 0.0) + amt
    debtor_ids = [c.id for c, _ in debtors]
    overdue_debtor_count = 0
    if debtor_ids:
        # paid_amount sotuv valyutasida, total_amount UZS da — solishtirishdan oldin kursga ko'paytiriladi
        overdue_debtor_count = (
            db.query(func.count(func.distinct(Sale.customer_id)))
            .filter(
                Sale.company_id == cid,
                sale_doc_filter(),
                Sale.customer_id.in_(debtor_ids),
                Sale.debt_due_date.isnot(None),
                Sale.debt_due_date < today,
                Sale.paid_amount * sale_rate() < Sale.total_amount - 0.01,
            )
            .scalar()
        ) or 0

    return {
        "warehouse_id": warehouse_id,
        "scope": {"branch_id": branch_id, "warehouse_id": warehouse_id},
        "today": {
            "sales": today_by_currency,
            "orders": today_count,
            "change_pct": today_change,
        },
        "weekly_trend": weekly_data,
        "monthly": {
            "sales": month_by_currency,
            "orders": month_count,
            "profit": round(float(month_profit or 0), 2),
        },
        "top_products": [
            {"name": r.name, "revenue": float(r.revenue or 0), "qty": float(r.qty or 0)}
            for r in top_rows
        ],
        "low_stock": [
            {"product_id": r["product_id"], "name": r["product_name"], "qty": float(r["current_qty"]),
             "min_stock": r["min_stock"],
             "warehouses": [{"warehouse_id": w["warehouse_id"], "name": w["name"], "qty": float(w["qty"])}
                            for w in r["warehouses"]]}
            for r in low_stock_rows
        ],
        "inventory": {
            "product_count": product_count,
            "product_count_scope": "company",   # mahsulotlar soni filialga bog'lanmagan
            "low_stock_count": low_stock_total,
            "dead_stock_count": dead_stock_total,
        },
        "cashier_performance": cashier_perf,
        "debts": {
            "total_debt": debt_by_currency,
            "debtor_count": len(debtors),
            "overdue_count": overdue_debtor_count,
            "scope": "company",   # qarz hali filialsiz (T2.6 gacha)
        },
        "monthly_trend": monthly_trend,
    }


# ─── Sotuvlar ro'yxati ────────────────────────────────────────────────────────

@router.get("/sales")
def sales_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    include_returns: bool = Query(True, description="Qaytarish hujjatlarini ham ko'rsatish"),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Sotuvlar ro'yxati. Qisman/to'liq qaytarilgan sotuvlar ham kiradi (status bilan);
    qaytarish hujjatlari manfiy summa bilan. Summalar sotuv valyutasida."""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1: cheklangan menejer uchun majburan o'z filiali

    base_filters = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end]
    if branch_id:  # T1.9: Sale.branch_id snapshot'i
        base_filters.append(sale_branch_filter(branch_id))
    filters = [*base_filters, sale_or_return_filter() if include_returns else sale_doc_filter()]

    total_count = db.query(func.count(Sale.id)).filter(*filters).scalar() or 0
    rows = (
        db.query(Sale, User)
        .options(joinedload(Sale.currency), joinedload(Sale.customer))
        .join(User, User.id == Sale.cashier_id)
        .filter(*filters)
        .order_by(Sale.created_at.desc())
        .limit(limit)
        .all()
    )

    codes = currency_code_map(db, cid)

    # Xulosa ro'yxat cheklovidan va include_returns dan qat'i nazar butun davr uchun
    def _totals(doc_filter):
        out = {}
        q = (
            db.query(Sale.currency_id, func.coalesce(func.sum(Sale.total_amount / sale_rate()), 0))
            .filter(*base_filters, doc_filter)
            .group_by(Sale.currency_id)
        )
        for currency_id, amount in q.all():
            code = _code(codes, currency_id)
            out[code] = round(out.get(code, 0.0) + float(amount), 2)
        return out

    sales_by_currency = _totals(sale_doc_filter())
    returns_by_currency = _totals(return_doc_filter())
    net_by_currency = {
        c: round(sales_by_currency.get(c, 0.0) - returns_by_currency.get(c, 0.0), 2)
        for c in set(sales_by_currency) | set(returns_by_currency)
    }

    items = []
    for s, u in rows:
        is_return = (s.number or "").startswith("R")
        rate = float(s.exchange_rate or 0) or 1.0
        sign = -1 if is_return else 1
        items.append({
            "id": s.id,
            "number": s.number,
            "cashier_name": u.name,
            "customer_id": s.customer_id,
            "customer_name": s.customer.name if s.customer else None,
            "total_amount": round(sign * float(s.total_amount or 0) / rate, 2),
            "discount_amount": round(float(s.discount_amount or 0) / rate, 2),
            "currency_code": s.currency.code if s.currency else "UZS",
            "payment_type": s.payment_type.value if s.payment_type else None,
            "status": s.status.value if s.status else None,
            "type": "return" if is_return else "sale",
            "created_at": s.created_at.isoformat(),
        })

    return {
        "items": items,
        "total_count": total_count,
        "truncated": total_count > len(items),
        "summary": {
            "sales_by_currency": sales_by_currency,
            "returns_by_currency": returns_by_currency,
            "net_by_currency": net_by_currency,
        },
    }


# ─── Qaytarishlar ro'yxati ────────────────────────────────────────────────────

@router.get("/returns")
def returns_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Qaytarish hujjatlari ro'yxati va xulosa (sotuv valyutasida)"""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1

    q = (
        db.query(Sale, User)
        .options(joinedload(Sale.currency), joinedload(Sale.customer))
        .join(User, User.id == Sale.cashier_id)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= start,
            Sale.created_at < end,
            return_doc_filter(),
        )
    )
    if branch_id:  # T1.9: Sale.branch_id snapshot'i
        q = q.filter(sale_branch_filter(branch_id))
    rows = q.order_by(Sale.created_at.desc()).limit(500).all()

    items = []
    total_by_currency: dict = {}
    for s, u in rows:
        curr = s.currency.code if s.currency else "UZS"
        rate = float(s.exchange_rate or 0) or 1.0
        amt = float(s.total_amount or 0) / rate
        total_by_currency[curr] = round(total_by_currency.get(curr, 0.0) + amt, 2)
        items.append({
            "id": s.id,
            "number": s.number,
            "cashier_name": u.name,
            "customer_id": s.customer_id,
            "customer_name": s.customer.name if s.customer else None,
            "total_amount": round(amt, 2),
            "paid_amount": float(s.paid_amount or 0),
            "payment_type": s.payment_type.value if s.payment_type else None,
            "currency_code": curr,
            "note": s.note,
            "created_at": s.created_at.isoformat(),
        })

    return {
        "total_returns": total_by_currency,
        "count": len(items),
        "items": items,
    }


# ─── Ombor qoldiqlari ─────────────────────────────────────────────────────────

@router.get("/inventory")
def inventory_report(
    response: Response,
    branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
    warehouse_id: Optional[int] = Query(None, description="Faqat shu ombor"),
    skip: int = Query(0, ge=0),
    limit: int = Query(5000, ge=1, le=20000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Ombor qoldiqlari hisoboti: qator = (mahsulot, variant, ombor). Qiymat — shu ombor partiyalari
    o'rtacha tannarxida (yo'q bo'lsa korxona o'rtachasi, so'ng Product.cost_price; `cost_basis`).
    Jami qatorlar soni `X-Total-Count` sarlavhasida."""
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi
    cid = current_user.company_id
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, warehouse_id, ctx)
    total, rows = stock_report.inventory_rows(db, cid, wh_ids, skip, limit)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    result = []
    for r in rows:
        p, w = r["product"], r["warehouse"]
        result.append({
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku,
            "variant_id": r["variant_id"],
            "variant_name": r["variant_name"],
            "warehouse_id": w.id,
            "warehouse_name": w.name,
            "branch_id": w.branch_id,
            "branch_name": r["branch_name"],
            "quantity": r["quantity"],
            "min_stock": p.min_stock,
            "cost_price": r["unit_cost"],
            "cost_basis": r["cost_basis"],
            "sale_price": float(p.sale_price),
            "value": r["value"],
            "is_low": r["is_low"],   # mahsulot darajasidagi bayroq (doiradagi jami qoldiq bo'yicha)
        })
    return result


@router.get("/inventory/summary")
def inventory_summary(
    branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
    warehouse_id: Optional[int] = Query(None, description="Faqat shu ombor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Qoldiq xulosasi: jami qiymat/miqdor, mahsulot soni, ombor va filial kesimida."""
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi
    cid = current_user.company_id
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, warehouse_id, ctx)
    return stock_report.inventory_summary(db, cid, wh_ids)


# ─── Kam qoldiq ogohlantirish ─────────────────────────────────────────────────

@router.get("/stock-alert")
def stock_alert(
    branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
    warehouse_id: Optional[int] = Query(None, description="Faqat shu ombor"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Minimal qoldiqqa yetgan mahsulotlar (mahsulot darajasida; yagona kam qoldiq ta'rifi)"""
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi
    cid = current_user.company_id
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, warehouse_id, ctx)
    rows = stock_report.low_stock_products(db, cid, wh_ids)
    return [
        {
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "sku": r["sku"],
            "barcode": r["barcode"],
            "current_qty": str(r["current_qty"]),
            "min_stock": r["min_stock"],
            "shortage": str(r["shortage"]),
            "warehouses": [
                {"warehouse_id": w["warehouse_id"], "name": w["name"], "qty": str(w["qty"])}
                for w in r["warehouses"]
            ],
        }
        for r in rows
    ]


# ─── O'lik stok ───────────────────────────────────────────────────────────────

@router.get("/dead-stock")
def dead_stock_report(
    months: int = Query(6, ge=1, le=24),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """O'lik stok: N oy davomida sotilmagan mahsulotlar (qiymat UZS, partiya tannarxida).
    Filial berilsa "sotilgan" tekshiruvi ham shu filial doirasida."""
    cid = current_user.company_id
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches
    wh_ids = stock_report.resolve_wh_scope(db, current_user, cid, branch_id, None, ctx)
    rows = _dead_stock_rows(db, cid, months, wh_ids)

    product_ids = [p.id for p, _ in rows]
    avg_costs = _batch_avg_costs(db, cid, product_ids, wh_ids)
    last_sold = {}
    if product_ids:
        ls_q = db.query(StockMovement.product_id, func.max(StockMovement.created_at)).filter(
            StockMovement.product_id.in_(product_ids), StockMovement.reference_type == "sale",
        )
        if wh_ids is not None:
            ls_q = ls_q.filter(StockMovement.warehouse_id.in_(wh_ids))
        last_sold = dict(ls_q.group_by(StockMovement.product_id).all())

    items = []
    for p, qty in rows:
        quantity = float(qty or 0)
        unit_cost = avg_costs.get(p.id, float(p.cost_price or 0))
        last = last_sold.get(p.id)
        items.append({
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku,
            "quantity": quantity,
            "cost_price": round(unit_cost, 2),
            "value": round(quantity * unit_cost, 2),
            "last_sold_at": last.isoformat() if last else None,
        })
    items.sort(key=lambda i: i["value"], reverse=True)

    return {
        "months": months,
        "total_items": len(items),
        "total_value": round(sum(i["value"] for i in items), 2),
        "items": items,
    }


# ─── Xarid hisoboti ───────────────────────────────────────────────────────────

@router.get("/purchases")
def purchases_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Xarid hisoboti — ta'minotchi bo'yicha, UZS da (chegirma ayirilgan).
    Qoralama va bekor qilingan buyurtmalar hisobga olinmaydi."""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1

    # PurchaseOrder.total_amount qatorlarning UZS tannarxidan yig'iladi
    net_amount = PurchaseOrder.total_amount - func.coalesce(PurchaseOrder.discount_amount, 0)
    q = (
        db.query(
            Supplier.id,
            Supplier.name,
            Supplier.phone,
            func.count(PurchaseOrder.id).label("po_count"),
            func.coalesce(func.sum(net_amount), 0).label("total_amount"),
        )
        .join(PurchaseOrder, PurchaseOrder.supplier_id == Supplier.id)
        .filter(
            PurchaseOrder.company_id == cid,
            PurchaseOrder.created_at >= start,
            PurchaseOrder.created_at < end,
            PurchaseOrder.status.notin_([POStatus.draft, POStatus.cancelled]),
        )
    )
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    if wh_ids is not None:
        q = q.filter(PurchaseOrder.warehouse_id.in_(wh_ids))
    rows = q.group_by(Supplier.id, Supplier.name, Supplier.phone).all()

    result = [
        {
            "supplier_id": r.id,
            "supplier_name": r.name,
            "phone": r.phone,
            "po_count": r.po_count,
            "total_amount": round(float(r.total_amount or 0), 2),
        }
        for r in rows
    ]
    result.sort(key=lambda r: r["total_amount"], reverse=True)
    return result


# ─── Mahsulotlar (Sotuv) hisoboti ──────────────────────────────────────────────

@router.get("/product-sales")
def product_sales_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Har bir mahsulot qancha sotilgani: sotilgan, qaytarilgan va sof miqdor;
    tushum va foyda UZS da, qaytarishlar ayirilgan ("Foyda" tabi bilan bir xil hisob)."""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1

    sold_qty = func.sum(case((is_return_doc(), 0), else_=SaleItem.quantity))
    returned_qty = func.sum(case((is_return_doc(), SaleItem.quantity), else_=0))
    revenue = func.sum(doc_sign() * item_revenue_uzs())
    cost = func.sum(doc_sign() * item_cost_uzs())

    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            sold_qty.label("sold_qty"),
            returned_qty.label("returned_qty"),
            revenue.label("revenue"),
            cost.label("cost"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= start,
            Sale.created_at < end,
            sale_or_return_filter(),
        )
    )
    if branch_id:  # T1.9: Sale.branch_id snapshot'i
        q = q.filter(sale_branch_filter(branch_id))
    rows = q.group_by(Product.id, Product.name, Product.sku).all()

    result = []
    for r in rows:
        sold = float(r.sold_qty or 0)
        returned = float(r.returned_qty or 0)
        rev = float(r.revenue or 0)
        cst = float(r.cost or 0)
        result.append({
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "sold_qty": round(sold, 3),
            "returned_qty": round(returned, 3),
            "total_qty": round(sold - returned, 3),
            "total_revenue": round(rev, 2),
            "total_profit": round(rev - cst, 2),
        })
    result.sort(key=lambda x: x["total_qty"], reverse=True)
    return result
