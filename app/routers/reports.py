"""
Reports API — asosiy hisobotlar: Dashboard, Sotuvlar, Ombor, Stok ogohlantirishlari, Xaridlar.
Moliya hisobotlari → finance_report.py
Sotuv tahlili → sales_report.py
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case, cast, Date as DateType
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.batch import Batch
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.utils.report_utils import _today_range, _date_range

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.super_admin)


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
    cid = current_user.company_id

    branch_wh_ids = None
    if branch_id:
        branch_wh_ids = db.query(Warehouse.id).filter(Warehouse.branch_id == branch_id).with_entities(Warehouse.id).all()
        branch_wh_ids = [wh[0] for wh in branch_wh_ids]

    def get_warehouse_filter(w_id):
        if w_id:
            return [Sale.warehouse_id == w_id]
        if branch_wh_ids:
            return [Sale.warehouse_id.in_(branch_wh_ids)]
        return []

    wh_filter = get_warehouse_filter(warehouse_id)
    today_q = db.query(func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0)).filter(
        Sale.company_id == cid,
        Sale.created_at >= today_start,
        Sale.created_at < today_end,
        Sale.status == SaleStatus.completed,
        *wh_filter
    )
    today_count, today_total = today_q.first()

    yesterday_start = today_start - timedelta(days=1)
    yesterday_total = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(
        Sale.company_id == cid,
        Sale.created_at >= yesterday_start,
        Sale.created_at < today_start,
        Sale.status == SaleStatus.completed,
        *wh_filter
    ).scalar()
    today_f = float(today_total)
    yesterday_f = float(yesterday_total)
    today_change = round(float((today_f - yesterday_f) / yesterday_f * 100), 1) if yesterday_f > 0 else None

    week_start = datetime.combine(
        datetime.now(timezone.utc).date() - timedelta(days=6), datetime.min.time()
    )
    week_rows = db.query(
        cast(Sale.created_at, DateType).label("day"),
        func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
        func.count(Sale.id).label("count"),
    ).filter(
        Sale.company_id == cid,
        Sale.created_at >= week_start,
        Sale.status == SaleStatus.completed,
        *wh_filter
    ).group_by(cast(Sale.created_at, DateType)).all()
    week_map = {str(r.day): (float(r.total), r.count) for r in week_rows}
    weekly_data = []
    for i in range(7):
        day = datetime.now(timezone.utc).date() - timedelta(days=6 - i)
        total, count = week_map.get(str(day), (0.0, 0))
        weekly_data.append({"date": day.strftime("%d.%m"), "amount": total, "count": count})

    _now = datetime.now(timezone.utc)
    month_start = datetime(_now.year, _now.month, 1, 0, 0, 0)
    month_count, month_total = db.query(func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0)).filter(
        Sale.company_id == cid,
        Sale.created_at >= month_start,
        Sale.status == SaleStatus.completed,
        *wh_filter
    ).first()
    month_profit = db.query(func.coalesce(
        func.sum(
            case(
                (Sale.status == SaleStatus.completed,
                 (SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity - SaleItem.discount),
                (Sale.status == SaleStatus.refunded,
                 -((SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity - SaleItem.discount)),
                else_=0,
            )
        ), 0
    )).join(Sale, Sale.id == SaleItem.sale_id).filter(
        Sale.company_id == cid,
        Sale.created_at >= month_start,
        Sale.status.in_([SaleStatus.completed, SaleStatus.refunded]),
        *wh_filter
    ).scalar()

    top_q = (
        db.query(Product.name, func.sum(SaleItem.subtotal).label("revenue"), func.sum(SaleItem.quantity).label("qty"))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.company_id == cid, Sale.created_at >= month_start, Sale.status == SaleStatus.completed, *wh_filter)
    )
    top_rows = top_q.group_by(Product.id, Product.name).order_by(func.sum(SaleItem.subtotal).desc()).limit(10).all()

    low_q = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(Product.is_deleted == False, Product.min_stock > 0, StockLevel.quantity < Product.min_stock)
    )
    low_q = low_q.filter(Product.company_id == cid)
    if warehouse_id:
        low_q = low_q.filter(StockLevel.warehouse_id == warehouse_id)
    low_stock_rows = low_q.order_by(StockLevel.quantity).limit(20).all()

    six_months_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=180)
    sold_ids = (
        db.query(SaleItem.product_id)
        .join(Sale)
        .filter(Sale.company_id == cid, Sale.created_at >= six_months_ago, Sale.status == SaleStatus.completed)
        .distinct()
        .scalar_subquery()
    )
    dead_q = (
        db.query(func.count(StockLevel.id))
        .join(Product)
        .filter(Product.is_deleted == False, StockLevel.quantity > 0, Product.id.notin_(sold_ids))
    )
    dead_q = dead_q.filter(Product.company_id == cid)
    if warehouse_id:
        dead_q = dead_q.filter(StockLevel.warehouse_id == warehouse_id)
    dead_stock_count = dead_q.scalar()

    cashier_q = (
        db.query(User.name, func.count(Sale.id).label("cnt"), func.coalesce(func.sum(Sale.total_amount), 0).label("total"))
        .join(Sale, Sale.cashier_id == User.id)
        .filter(Sale.company_id == cid, Sale.created_at >= month_start, Sale.status == SaleStatus.completed, *wh_filter)
    )
    cashier_rows = cashier_q.group_by(User.id, User.name).order_by(func.sum(Sale.total_amount).desc()).limit(10).all()

    product_count = db.query(func.count(Product.id)).filter(Product.is_deleted == False, Product.company_id == cid).scalar()

    debt_q = (
        db.query(func.count(Customer.id), func.coalesce(func.sum(Customer.debt_balance), 0))
        .filter(Customer.debt_balance > 0, Customer.company_id == cid)
    )
    debtor_count, total_debt = debt_q.first()
    today_date = datetime.now(timezone.utc).date()
    overdue_debtor_count = (
        db.query(func.count(func.distinct(Sale.customer_id)))
        .filter(Sale.company_id == cid, Sale.customer_id.isnot(None), Sale.paid_amount < Sale.total_amount, Sale.debt_due_date.isnot(None), Sale.debt_due_date < today_date)
        .scalar()
    ) or 0

    month30_start = datetime.combine(
        datetime.now(timezone.utc).date() - timedelta(days=29), datetime.min.time()
    )
    month30_rows = db.query(
        cast(Sale.created_at, DateType).label("day"),
        func.coalesce(func.sum(Sale.total_amount), 0).label("total"),
    ).filter(
        Sale.company_id == cid,
        Sale.created_at >= month30_start,
        Sale.status == SaleStatus.completed,
        *wh_filter
    ).group_by(cast(Sale.created_at, DateType)).all()
    month30_map = {str(r.day): float(r.total) for r in month30_rows}
    monthly_trend = []
    for i in range(30):
        day = datetime.now(timezone.utc).date() - timedelta(days=29 - i)
        monthly_trend.append({"date": day.strftime("%d.%m"), "amount": month30_map.get(str(day), 0.0)})

    return {
        "warehouse_id": warehouse_id,
        "today": {
            "sales": str(today_total),
            "orders": today_count,
            "change_pct": today_change,
        },
        "weekly_trend": weekly_data,
        "monthly": {
            "sales": str(month_total),
            "orders": month_count,
            "profit": str(month_profit),
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
            "low_stock_count": len(low_stock_rows),
            "dead_stock_count": dead_stock_count,
        },
        "cashier_performance": [
            {"name": r.name, "count": r.cnt, "total": float(r.total)}
            for r in cashier_rows
        ],
        "debts": {
            "total_debt": float(total_debt or 0),
            "debtor_count": debtor_count or 0,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Sotuvlar ro'yxati"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(Sale, User)
        .join(User, User.id == Sale.cashier_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    if branch_id:
        branch_wh_ids = [wh.id for wh in db.query(Warehouse.id).filter(Warehouse.branch_id == branch_id).all()]
        q = q.filter(Sale.warehouse_id.in_(branch_wh_ids))
    rows = q.order_by(Sale.created_at.desc()).limit(500).all()
    return [
        {
            "id": s.id,
            "number": s.number,
            "cashier_name": u.name,
            "total_amount": float(s.total_amount),
            "discount_amount": float(s.discount_amount),
            "payment_type": s.payment_type,
            "status": s.status,
            "created_at": s.created_at.isoformat(),
        }
        for s, u in rows
    ]


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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """O'lik stok: N oy davomida sotilmagan mahsulotlar"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    sold_ids = (
        db.query(SaleItem.product_id)
        .join(Sale)
        .filter(Sale.company_id == current_user.company_id, Sale.created_at >= cutoff, Sale.status == SaleStatus.completed)
        .distinct()
        .scalar_subquery()
    )
    rows = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(Product.company_id == current_user.company_id, Product.is_deleted == False, StockLevel.quantity > 0, Product.id.notin_(sold_ids))
        .order_by((StockLevel.quantity * Product.cost_price).desc())
        .all()
    )
    total_value = sum(float(s.quantity * p.cost_price) for s, p in rows)
    return {
        "months": months,
        "total_items": len(rows),
        "total_value": total_value,
        "items": [
            {
                "product_id": p.id,
                "product_name": p.name,
                "sku": p.sku,
                "quantity": float(s.quantity),
                "cost_price": float(p.cost_price),
                "value": float(s.quantity * p.cost_price),
            }
            for s, p in rows
        ],
    }


# ─── Xarid hisoboti ───────────────────────────────────────────────────────────

@router.get("/purchases")
def purchases_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Xarid hisoboti — supplier bo'yicha"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            Supplier.id,
            Supplier.name,
            Supplier.phone,
            func.count(PurchaseOrder.id).label("po_count"),
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0).label("total_amount"),
        )
        .join(PurchaseOrder, PurchaseOrder.supplier_id == Supplier.id)
        .filter(PurchaseOrder.created_at >= start, PurchaseOrder.created_at < end)
    )
    q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    rows = (
        q.group_by(Supplier.id, Supplier.name, Supplier.phone)
        .order_by(func.sum(PurchaseOrder.total_amount).desc())
        .all()
    )
    return [
        {
            "supplier_id": r.id,
            "supplier_name": r.name,
            "phone": r.phone,
            "po_count": r.po_count,
            "total_amount": float(r.total_amount),
        }
        for r in rows
    ]
