"""
Reports API — asosiy hisobotlar: Dashboard, Sotuvlar, Qaytarishlar, Ombor,
Stok ogohlantirishlari, O'lik stok, Xaridlar, Mahsulotlar (Sotuv).
Moliya hisobotlari → finance_report.py
Sotuv tahlili → sales_report.py
Valyuta, qaytarish hujjatlari va vaqt qoidalari → app/utils/report_utils.py
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case, cast, Date as DateType
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.customer import Customer
from app.models.inventory import StockLevel, StockMovement
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, POStatus
from app.models.sale import Sale, SaleItem
from app.models.batch import Batch
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.utils.report_utils import (
    _today_range, _date_range, local_today, local_day_start,
    is_return_doc, sale_doc_filter, return_doc_filter, sale_or_return_filter, doc_sign,
    sale_rate, item_revenue_uzs, item_cost_uzs,
    branch_warehouse_ids, currency_code_map, load_debtors,
)

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.super_admin)


def _code(codes: dict, currency_id) -> str:
    return codes.get(currency_id, "UZS") if currency_id else "UZS"


# ─── O'lik stok (Dashboard va hisobot uchun umumiy) ──────────────────────────

def _dead_stock_rows(db: Session, company_id: int, months: int, wh_ids: Optional[list]):
    """N oy davomida sotilmagan, qoldig'i bor mahsulotlar: [(Product, qty)].

    "Sotilgan" — ombordan sotuv bilan chiqqan (StockMovement): tarkibiy (sell)
    mahsulot sotilganda manba mahsulot shu yerda ko'rinadi. SaleItem ham
    hisobga olinadi. Oynadan keyin qo'shilgan yangi mahsulotlar kirmaydi.
    """
    cutoff = local_day_start(local_today()) - timedelta(days=months * 30)
    sold_by_movement = (
        db.query(StockMovement.product_id)
        .join(Product, Product.id == StockMovement.product_id)
        .filter(
            Product.company_id == company_id,
            StockMovement.reference_type == "sale",
            StockMovement.created_at >= cutoff,
        )
        .distinct()
        .scalar_subquery()
    )
    sold_by_items = (
        db.query(SaleItem.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.company_id == company_id, sale_doc_filter(), Sale.created_at >= cutoff)
        .distinct()
        .scalar_subquery()
    )
    qty_sum = func.sum(StockLevel.quantity)
    q = (
        db.query(Product, qty_sum.label("qty"))
        .join(StockLevel, StockLevel.product_id == Product.id)
        .filter(
            Product.company_id == company_id,
            Product.is_deleted == False,
            StockLevel.quantity > 0,
            (Product.created_at.is_(None)) | (Product.created_at < cutoff),
            Product.id.notin_(sold_by_movement),
            Product.id.notin_(sold_by_items),
        )
    )
    if wh_ids is not None:
        q = q.filter(StockLevel.warehouse_id.in_(wh_ids))
    return q.group_by(Product.id).having(qty_sum > 0).all()


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


# ─── Dashboard ───────────────────────────────────────────────────────────────

@router.get("/dashboard")
def get_dashboard(
    warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filtr (None = hammasi)"),
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager, UserRole.super_admin)),
):
    """Direktor uchun asosiy ko'rsatkichlar"""
    today_start, today_end = _today_range()
    today = local_today()
    cid = current_user.company_id

    wh_ids = [warehouse_id] if warehouse_id else branch_warehouse_ids(db, cid, branch_id)
    base = [Sale.company_id == cid]
    if wh_ids is not None:
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

    low_q = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(
            Product.company_id == cid,
            Product.is_deleted == False,
            Product.min_stock > 0,
            StockLevel.quantity < Product.min_stock,
        )
    )
    if wh_ids is not None:
        low_q = low_q.filter(StockLevel.warehouse_id.in_(wh_ids))
    low_stock_count = low_q.count()
    low_stock_rows = low_q.order_by(StockLevel.quantity).limit(20).all()

    dead_stock_count = len(_dead_stock_rows(db, cid, 6, wh_ids))

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
        entry = cashier_map.setdefault(uid, {"name": name, "count": 0, "totals": {}, "_uzs": 0.0})
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
            {"product_id": p.id, "name": p.name, "qty": float(s.quantity), "min_stock": p.min_stock}
            for s, p in low_stock_rows
        ],
        "inventory": {
            "product_count": product_count,
            "low_stock_count": low_stock_count,
            "dead_stock_count": dead_stock_count,
        },
        "cashier_performance": cashier_perf,
        "debts": {
            "total_debt": debt_by_currency,
            "debtor_count": len(debtors),
            "overdue_count": overdue_debtor_count,
        },
        "monthly_trend": monthly_trend,
    }


# ─── Sotuvlar ro'yxati ────────────────────────────────────────────────────────

@router.get("/sales")
def sales_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    include_returns: bool = Query(True, description="Qaytarish hujjatlarini ham ko'rsatish"),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Sotuvlar ro'yxati. Qisman/to'liq qaytarilgan sotuvlar ham kiradi (status bilan);
    qaytarish hujjatlari manfiy summa bilan. Summalar sotuv valyutasida."""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

    base_filters = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end]
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    if wh_ids is not None:
        base_filters.append(Sale.warehouse_id.in_(wh_ids))
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
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Qaytarish hujjatlari ro'yxati va xulosa (sotuv valyutasida)"""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

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
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    if wh_ids is not None:
        q = q.filter(Sale.warehouse_id.in_(wh_ids))
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Ombor qoldiqlari hisoboti — qiymat haqiqiy batch narxida (FIFO)"""
    q = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(Product.is_deleted == False)
    )
    q = q.filter(Product.company_id == current_user.company_id)
    rows = q.order_by(StockLevel.quantity).all()

    batch_value_sq = (
        db.query(
            Batch.product_id,
            func.sum(Batch.quantity * Batch.purchase_price).label("total_cost"),
            func.sum(Batch.quantity).label("total_qty"),
        )
        .filter(Batch.company_id == current_user.company_id, Batch.quantity > 0)
        .group_by(Batch.product_id)
        .all()
    )
    batch_avg_cost: dict = {}
    for row in batch_value_sq:
        if row.total_qty and float(row.total_qty) > 0:
            batch_avg_cost[row.product_id] = float(row.total_cost) / float(row.total_qty)

    result = []
    for s, p in rows:
        qty = float(s.quantity)
        unit_cost = batch_avg_cost.get(p.id, float(p.cost_price))
        result.append({
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku,
            "quantity": qty,
            "min_stock": p.min_stock,
            "cost_price": unit_cost,
            "sale_price": float(p.sale_price),
            "value": round(qty * unit_cost, 2),
            "is_low": qty <= p.min_stock,
        })
    return result


# ─── Kam qoldiq ogohlantirish ─────────────────────────────────────────────────

@router.get("/stock-alert")
def stock_alert(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Minimal qoldiqqa yetgan mahsulotlar"""
    q = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(Product.is_deleted == False, StockLevel.quantity <= Product.min_stock)
    )
    q = q.filter(Product.company_id == current_user.company_id)
    rows = q.order_by(StockLevel.quantity).all()
    return [
        {
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku,
            "barcode": p.barcode,
            "current_qty": str(s.quantity),
            "min_stock": p.min_stock,
            "shortage": str(p.min_stock - s.quantity),
        }
        for s, p in rows
    ]


# ─── O'lik stok ───────────────────────────────────────────────────────────────

@router.get("/dead-stock")
def dead_stock_report(
    months: int = Query(6, ge=1, le=24),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """O'lik stok: N oy davomida sotilmagan mahsulotlar (qiymat UZS, partiya tannarxida)"""
    cid = current_user.company_id
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    rows = _dead_stock_rows(db, cid, months, wh_ids)

    product_ids = [p.id for p, _ in rows]
    avg_costs = _batch_avg_costs(db, cid, product_ids, wh_ids)
    last_sold = {}
    if product_ids:
        last_sold = dict(
            db.query(StockMovement.product_id, func.max(StockMovement.created_at))
            .filter(StockMovement.product_id.in_(product_ids), StockMovement.reference_type == "sale")
            .group_by(StockMovement.product_id)
            .all()
        )

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
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Xarid hisoboti — ta'minotchi bo'yicha, UZS da (chegirma ayirilgan).
    Qoralama va bekor qilingan buyurtmalar hisobga olinmaydi."""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

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
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Har bir mahsulot qancha sotilgani: sotilgan, qaytarilgan va sof miqdor;
    tushum va foyda UZS da, qaytarishlar ayirilgan ("Foyda" tabi bilan bir xil hisob)."""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

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
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    if wh_ids is not None:
        q = q.filter(Sale.warehouse_id.in_(wh_ids))
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
