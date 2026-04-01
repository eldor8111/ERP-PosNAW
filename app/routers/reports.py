"""
Reports API — 3-bosqich: Kengaytirilgan hisobotlar, Dashboard KPI, 1C eksport
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import StockLevel, StockMovement
from app.models.moliya import Expense, Transaction
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, POItem
from app.models.sale import Sale, SaleItem, SaleStatus, SaleItemBatch
from app.models.batch import Batch
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.super_admin)


def _today_range():
    today = datetime.now(timezone.utc).date()
    return (
        datetime.combine(today, datetime.min.time()),
        datetime.combine(today + timedelta(days=1), datetime.min.time()),
    )


@router.get("/debug-sales")
def debug_sales(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    """Diagnostika: nimaga sotuv ko'rinmayapti"""
    from sqlalchemy import text
    _now = datetime.now(timezone.utc)
    today_start = datetime(_now.year, _now.month, _now.day, 0, 0, 0)
    month_start = datetime(_now.year, _now.month, 1, 0, 0, 0)

    all_count = db.query(func.count(Sale.id)).scalar()
    company_count = db.query(func.count(Sale.id)).filter(Sale.company_id == current_user.company_id).scalar()
    completed_count = db.query(func.count(Sale.id)).filter(Sale.status == SaleStatus.completed).scalar()
    company_completed = db.query(func.count(Sale.id)).filter(
        Sale.company_id == current_user.company_id, Sale.status == SaleStatus.completed
    ).scalar()
    today_completed = db.query(func.count(Sale.id)).filter(
        Sale.company_id == current_user.company_id,
        Sale.status == SaleStatus.completed,
        Sale.created_at >= today_start,
    ).scalar()
    month_completed = db.query(func.count(Sale.id)).filter(
        Sale.company_id == current_user.company_id,
        Sale.status == SaleStatus.completed,
        Sale.created_at >= month_start,
    ).scalar()
    # Oxirgi 5 ta sotuvni ko'rish
    last_sales = db.query(Sale.id, Sale.company_id, Sale.status, Sale.created_at).order_by(Sale.created_at.desc()).limit(5).all()
    return {
        "current_user_company_id": current_user.company_id,
        "today_start": str(today_start),
        "all_sales_in_db": all_count,
        "sales_with_company_id": company_count,
        "all_completed_sales": completed_count,
        "company_completed_sales": company_completed,
        "today_completed_sales": today_completed,
        "month_completed_sales": month_completed,
        "last_5_sales": [
            {"id": r[0], "company_id": r[1], "status": str(r[2]), "created_at": str(r[3])}
            for r in last_sales
        ],
    }


def _date_range(date_from: Optional[date], date_to: Optional[date]):
    start = datetime.combine(date_from, datetime.min.time()) if date_from else datetime(2000, 1, 1)
    end = datetime.combine(date_to + timedelta(days=1), datetime.min.time()) if date_to else datetime(2100, 1, 1)
    return start, end


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

    # Resolve branch → warehouse IDs
    branch_wh_ids = None
    if branch_id:
        branch_wh_ids = [wh.id for wh in db.query(Warehouse.id).filter(Warehouse.branch_id == branch_id).all()]

    def sale_filter(q, wh_id):
        """Sale querysiga ombor filtri qo'shish"""
        if current_user.company_id is not None:
            q = q.filter(Sale.company_id == current_user.company_id)
        if wh_id:
            q = q.filter(Sale.warehouse_id == wh_id)
        elif branch_wh_ids is not None:
            q = q.filter(Sale.warehouse_id.in_(branch_wh_ids))
        return q

    # Bugungi sotuv
    today_q = sale_filter(
        db.query(func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.created_at >= today_start, Sale.created_at < today_end, Sale.status == SaleStatus.completed),
        warehouse_id,
    )
    today_count, today_total = today_q.first()

    # Kecha sotuv (o'zgarish % uchun)
    yesterday_start = today_start - timedelta(days=1)
    yesterday_total = sale_filter(
        db.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.created_at >= yesterday_start, Sale.created_at < today_start, Sale.status == SaleStatus.completed),
        warehouse_id,
    ).scalar()
    today_f = float(today_total)
    yesterday_f = float(yesterday_total)
    today_change = round(float((today_f - yesterday_f) / yesterday_f * 100), 1) if yesterday_f > 0 else None  # type: ignore[call-overload]

    # Haftalik trend (7 kun)
    weekly_data = []
    for i in range(7):
        day = datetime.now(timezone.utc).date() - timedelta(days=6 - i)
        ds = datetime.combine(day, datetime.min.time())
        de = datetime.combine(day + timedelta(days=1), datetime.min.time())
        total = sale_filter(
            db.query(func.coalesce(func.sum(Sale.total_amount), 0))
            .filter(Sale.created_at >= ds, Sale.created_at < de, Sale.status == SaleStatus.completed),
            warehouse_id,
        ).scalar()
        count = sale_filter(
            db.query(func.count(Sale.id))
            .filter(Sale.created_at >= ds, Sale.created_at < de, Sale.status == SaleStatus.completed),
            warehouse_id,
        ).scalar()
        weekly_data.append({"date": day.strftime("%d.%m"), "amount": float(total), "count": count})

    # Oylik sotuv
    _now = datetime.now(timezone.utc)
    month_start = datetime(_now.year, _now.month, 1, 0, 0, 0)  # naive datetime, TZ muammosi yo'q
    month_count, month_total = sale_filter(
        db.query(func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.created_at >= month_start, Sale.status == SaleStatus.completed),
        warehouse_id,
    ).first()
    month_profit = sale_filter(
        db.query(func.coalesce(
            func.sum((SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity - SaleItem.discount), 0
        ))
        .join(Sale)
        .filter(Sale.created_at >= month_start, Sale.status == SaleStatus.completed),
        warehouse_id,
    ).scalar()

    # Top 10 mahsulotlar (bu oy)
    top_q = (
        db.query(Product.name, func.sum(SaleItem.subtotal).label("revenue"), func.sum(SaleItem.quantity).label("qty"))
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= month_start, Sale.status == SaleStatus.completed)
    )
    top_q = top_q.filter(Sale.company_id == current_user.company_id)
    if warehouse_id:
        top_q = top_q.filter(Sale.warehouse_id == warehouse_id)
    top_rows = top_q.group_by(Product.id, Product.name).order_by(func.sum(SaleItem.subtotal).desc()).limit(10).all()

    # Kam qoldiqli mahsulotlar: faqat min_stock > 0 bo'lgan va qoldig'i minimum dan PAST bo'lganlar
    low_q = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(
            Product.is_deleted == False,
            Product.min_stock > 0,
            StockLevel.quantity < Product.min_stock,
        )
    )
    low_q = low_q.filter(Product.company_id == current_user.company_id)
    if warehouse_id:
        low_q = low_q.filter(StockLevel.warehouse_id == warehouse_id)
    low_stock_rows = low_q.order_by(StockLevel.quantity).limit(20).all()

    # O'lik stok (6 oy sotilmagan)
    six_months_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=180)
    sold_ids = (
        db.query(SaleItem.product_id)
        .join(Sale)
        .filter(Sale.created_at >= six_months_ago, Sale.status == SaleStatus.completed)
        .distinct()
        .scalar_subquery()
    )
    dead_q = (
        db.query(func.count(StockLevel.id))
        .join(Product)
        .filter(Product.is_deleted == False, StockLevel.quantity > 0, Product.id.notin_(sold_ids))
    )
    dead_q = dead_q.filter(Product.company_id == current_user.company_id)
    if warehouse_id:
        dead_q = dead_q.filter(StockLevel.warehouse_id == warehouse_id)
    dead_stock_count = dead_q.scalar()

    # Kassir samaradorligi (bu oy)
    cashier_q = (
        db.query(User.name, func.count(Sale.id).label("cnt"), func.coalesce(func.sum(Sale.total_amount), 0).label("total"))
        .join(Sale, Sale.cashier_id == User.id)
        .filter(Sale.created_at >= month_start, Sale.status == SaleStatus.completed)
    )
    cashier_q = cashier_q.filter(Sale.company_id == current_user.company_id)
    if warehouse_id:
        cashier_q = cashier_q.filter(Sale.warehouse_id == warehouse_id)
    cashier_rows = cashier_q.group_by(User.id, User.name).order_by(func.sum(Sale.total_amount).desc()).limit(10).all()

    product_q = db.query(func.count(Product.id)).filter(Product.is_deleted == False)
    product_q = product_q.filter(Product.company_id == current_user.company_id)
    product_count = product_q.scalar()

    # Debitorlar (qarzdor mijozlar)
    debt_q = (
        db.query(func.count(Customer.id), func.coalesce(func.sum(Customer.debt_balance), 0))
        .filter(Customer.debt_balance > 0, Customer.company_id == current_user.company_id)
    )
    debtor_count, total_debt = debt_q.first()
    today_date = datetime.now(timezone.utc).date()
    overdue_debtor_count = (
        db.query(func.count(func.distinct(Sale.customer_id)))
        .filter(
            Sale.company_id == current_user.company_id,
            Sale.customer_id.isnot(None),
            Sale.paid_amount < Sale.total_amount,
            Sale.debt_due_date.isnot(None),
            Sale.debt_due_date < today_date,
        )
        .scalar()
    ) or 0

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
    }


# ─── Sotuvlar ro'yxati (Reports.jsx uchun) ───────────────────────────────────

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
    """Ombor qoldiqlari hisoboti"""
    q = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(Product.is_deleted == False)
    )
    q = q.filter(Product.company_id == current_user.company_id)
    rows = q.order_by(StockLevel.quantity).all()
    return [
        {
            "product_id": p.id,
            "product_name": p.name,
            "sku": p.sku,
            "quantity": float(s.quantity),
            "min_stock": p.min_stock,
            "value": float(s.quantity * p.cost_price),
            "is_low": s.quantity <= p.min_stock,
        }
        for s, p in rows
    ]


# ─── Xarajatlar hisoboti ──────────────────────────────────────────────────────

@router.get("/expenses")
def expenses_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Xarajatlar hisoboti"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(Expense)
        .filter(Expense.created_at >= start, Expense.created_at < end)
    )
    q = q.filter(Expense.company_id == current_user.company_id)
    items = q.order_by(Expense.created_at.desc()).all()
    total = sum(float(e.amount) for e in items)
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "category": e.category.name if e.category else "—",
                "amount": float(e.amount),
                "description": e.description,
                "created_at": e.created_at.isoformat(),
            }
            for e in items
        ],
    }


# ─── Foyda hisoboti (mahsulot/kategoriya bo'yicha) ───────────────────────────

@router.get("/profit")
def profit_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Mahsulot va kategoriya bo'yicha foyda hisoboti (gross margin)"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Category.name.label("category_name"),
            func.sum(SaleItem.quantity).label("qty_sold"),
            func.sum(SaleItem.subtotal).label("revenue"),
            func.sum(SaleItem.cost_price * SaleItem.quantity).label("cost"),
            func.sum(SaleItem.subtotal - SaleItem.cost_price * SaleItem.quantity).label("profit"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(Product.id, Product.name, Product.sku, Category.name)
        .order_by(func.sum(SaleItem.subtotal - SaleItem.cost_price * SaleItem.quantity).desc())
        .all()
    )
    return [
        {
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "category_name": r.category_name or "—",
            "qty_sold": float(r.qty_sold or 0),
            "revenue": float(r.revenue or 0),
            "cost": float(r.cost or 0),
            "profit": float(r.profit or 0),
            "margin_pct": round(float(float(r.profit or 0) / float(r.revenue or 1) * 100), 1) if r.revenue else 0,  # type: ignore[call-overload]
        }
        for r in rows
    ]


# ─── Partiyalar foydasi (FIFO) ────────────────────────────────────────────────

@router.get("/batches")
def batches_profit_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Partiyalar (Batch) bo'yicha sotuv va foyda hisoboti"""
    start, end = _date_range(date_from, date_to)
    
    sold_qty_expr = func.coalesce(func.sum(
        case((Sale.status == SaleStatus.completed, SaleItemBatch.quantity), else_=0)
    ), 0)
    revenue_expr = func.coalesce(func.sum(
        case((Sale.status == SaleStatus.completed, SaleItemBatch.quantity * SaleItem.unit_price), else_=0)
    ), 0)
    profit_expr = func.coalesce(func.sum(
        case((Sale.status == SaleStatus.completed, SaleItemBatch.quantity * (SaleItem.unit_price - SaleItemBatch.unit_cost)), else_=0)
    ), 0)

    q = (
        db.query(
            Batch.id,
            Product.name.label("product_name"),
            Batch.lot_number,
            Batch.initial_quantity,
            Batch.quantity.label("remaining_quantity"),
            Batch.purchase_price,
            sold_qty_expr.label("sold_qty"),
            revenue_expr.label("revenue"),
            profit_expr.label("profit")
        )
        .join(Product, Product.id == Batch.product_id)
        .outerjoin(SaleItemBatch, SaleItemBatch.batch_id == Batch.id)
        .outerjoin(SaleItem, SaleItem.id == SaleItemBatch.sale_item_id)
        .outerjoin(Sale, Sale.id == SaleItem.sale_id)
        .filter(Batch.created_at >= start, Batch.created_at < end)
    )
    
    q = q.filter(Batch.company_id == current_user.company_id)
        
    rows = q.group_by(Batch.id, Product.name).order_by(Batch.created_at.desc()).all()
    
    return [
        {
            "batch_id": r.id,
            "product_name": r.product_name,
            "lot_number": r.lot_number or "N/A",
            "initial_quantity": float(r.initial_quantity or 0),
            "remaining_quantity": float(r.remaining_quantity or 0),
            "purchase_price": float(r.purchase_price or 0),
            "sold_qty": float(r.sold_qty),
            "revenue": float(r.revenue),
            "profit": float(r.profit),
            "margin_pct": round(float(r.profit / r.revenue * 100), 1) if r.revenue and float(r.revenue) > 0 else 0
        }
        for r in rows
    ]


# ─── Kunlik sotuv agregatsiyasi ───────────────────────────────────────────────

@router.get("/daily-sales")
def daily_sales_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Kunlik sotuv hisoboti (agregatsiya)"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            func.date(Sale.created_at).label("day"),
            func.count(Sale.id).label("sales_count"),
            func.sum(Sale.total_amount).label("total_amount"),
            func.sum(Sale.discount_amount).label("total_discount"),
            func.avg(Sale.total_amount).label("avg_check"),
        )
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(func.date(Sale.created_at))
        .order_by(func.date(Sale.created_at).desc())
        .all()
    )
    return [
        {
            "date": str(r.day),
            "sales_count": r.sales_count,
            "total_amount": str(r.total_amount or 0),
            "total_discount": str(r.total_discount or 0),
            "avg_check": str(round(r.avg_check or 0, 2)),
        }
        for r in rows
    ]


# ─── Top mahsulotlar ──────────────────────────────────────────────────────────

@router.get("/top-products")
def top_products_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Eng ko'p sotilgan mahsulotlar"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            func.sum(SaleItem.quantity).label("total_qty"),
            func.sum(SaleItem.subtotal).label("total_revenue"),
            func.sum((SaleItem.unit_price - SaleItem.cost_price) * SaleItem.quantity).label("total_profit"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(Product.id, Product.name, Product.sku)
        .order_by(func.sum(SaleItem.subtotal).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "rank": idx + 1,
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "total_qty": str(r.total_qty),
            "total_revenue": str(r.total_revenue or 0),
            "total_profit": str(r.total_profit or 0),
        }
        for idx, r in enumerate(rows)
    ]


# ─── Kassir hisoboti ──────────────────────────────────────────────────────────

@router.get("/cashier-report")
def cashier_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Kassir bo'yicha sotuv hisoboti"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            User.id,
            User.name,
            func.count(Sale.id).label("sales_count"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total_amount"),
            func.coalesce(func.sum(Sale.discount_amount), 0).label("total_discount"),
            func.coalesce(func.avg(Sale.total_amount), 0).label("avg_check"),
        )
        .join(Sale, Sale.cashier_id == User.id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(User.id, User.name)
        .order_by(func.sum(Sale.total_amount).desc())
        .all()
    )
    return [
        {
            "cashier_id": r.id,
            "cashier_name": r.name,
            "sales_count": r.sales_count,
            "total_amount": float(r.total_amount),
            "total_discount": float(r.total_discount),
            "avg_check": round(float(float(r.avg_check)), 2),  # type: ignore[call-overload]
        }
        for r in rows
    ]


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
        .filter(Sale.created_at >= cutoff, Sale.status == SaleStatus.completed)
        .distinct()
        .scalar_subquery()
    )
    rows = (
        db.query(StockLevel, Product)
        .join(Product, Product.id == StockLevel.product_id)
        .filter(Product.is_deleted == False, StockLevel.quantity > 0, Product.id.notin_(sold_ids))
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


# ─── Debitor qarzdorlik (Mijozlar) ────────────────────────────────────────────

@router.get("/customer-debts")
def customer_debts_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Debitor qarzdorlik — mijozlar bo'yicha"""
    q = (
        db.query(Customer)
        .filter(Customer.debt_balance > 0)
    )
    q = q.filter(Customer.company_id == current_user.company_id)
    rows = q.order_by(Customer.debt_balance.desc()).all()
    total = sum(float(c.debt_balance) for c in rows)
    return {
        "total_debt": total,
        "count": len(rows),
        "items": [
            {
                "customer_id": c.id,
                "customer_name": c.name,
                "phone": c.phone,
                "debt_balance": float(c.debt_balance),
                "debt_limit": float(c.debt_limit),
                "usage_pct": round(float(float(c.debt_balance) / float(c.debt_limit) * 100), 1) if c.debt_limit else 0,  # type: ignore[call-overload]
            }
            for c in rows
        ],
    }


# ─── Kreditor qarzdorlik (Supplierlar) ───────────────────────────────────────

@router.get("/supplier-debts")
def supplier_debts_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Kreditor qarzdorlik — supplierlar bo'yicha"""
    q = (
        db.query(Supplier)
        .filter(Supplier.debt_balance > 0)
    )
    q = q.filter(Supplier.company_id == current_user.company_id)
    rows = q.order_by(Supplier.debt_balance.desc()).all()
    total = sum(float(s.debt_balance) for s in rows)
    return {
        "total_debt": total,
        "count": len(rows),
        "items": [
            {
                "supplier_id": s.id,
                "supplier_name": s.name,
                "phone": s.phone,
                "debt_balance": float(s.debt_balance),
                "payment_terms": s.payment_terms,
            }
            for s in rows
        ],
    }


# ─── ABC/XYZ tahlil ───────────────────────────────────────────────────────────

@router.get("/abc-xyz")
def abc_xyz_analysis(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """ABC/XYZ tahlil — mahsulotlarni qiymat va chastotaga ko'ra guruhlash"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            func.sum(SaleItem.subtotal).label("revenue"),
            func.count(SaleItem.id).label("frequency"),
            func.sum(SaleItem.quantity).label("qty"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = q.group_by(Product.id, Product.name, Product.sku).all()

    if not rows:
        return []

    # ABC — qiymat bo'yicha (A: 0-80%, B: 80-95%, C: 95-100%)
    total_revenue = sum(float(r.revenue or 0) for r in rows)
    sorted_rev = sorted(rows, key=lambda r: float(r.revenue or 0), reverse=True)
    cumulative = 0.0
    abc_map = {}
    for r in sorted_rev:
        cumulative += float(float(r.revenue or 0) / total_revenue * 100) if total_revenue else 0.0  # type: ignore[operator]
        abc_map[r.id] = "A" if cumulative <= 80 else ("B" if cumulative <= 95 else "C")

    # XYZ — chastota bo'yicha (X: tez, Y: o'rta, Z: sekin)
    max_freq = max(r.frequency for r in rows) or 1
    xyz_map = {}
    for r in rows:
        ratio = r.frequency / max_freq
        xyz_map[r.id] = "X" if ratio >= 0.7 else ("Y" if ratio >= 0.4 else "Z")

    return [
        {
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "revenue": float(r.revenue or 0),
            "frequency": r.frequency,
            "qty": float(r.qty or 0),
            "abc": abc_map.get(r.id, "C"),
            "xyz": xyz_map.get(r.id, "Z"),
            "group": f"{abc_map.get(r.id, 'C')}{xyz_map.get(r.id, 'Z')}",
        }
        for r in sorted_rev
    ]


# ─── 1C Buxgalteriya eksport ──────────────────────────────────────────────────

@router.get("/1c-export")
def export_1c(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    format: str = Query("csv", enum=["csv", "xml"]),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """1C Buxgalteriya uchun savdo ma'lumotlari eksporti (CSV yoki XML)"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(Sale, User)
        .join(User, User.id == Sale.cashier_id)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    sales = q.order_by(Sale.created_at).all()

    filename_date = date.today().isoformat()

    if format == "csv":
        lines = ["Raqam,Sana,Kassir,Jami summa,Chegirma,To'lov turi"]
        for s, u in sales:
            lines.append(
                f"{s.number},"
                f"{s.created_at.strftime('%Y-%m-%d %H:%M:%S')},"
                f"{u.name},"
                f"{float(s.total_amount):.2f},"
                f"{float(s.discount_amount):.2f},"
                f"{s.payment_type.value}"
            )
        content = "\n".join(lines)
        return Response(
            content=content.encode("utf-8-sig"),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=1c_export_{filename_date}.csv"},
        )
    else:
        lines = ['<?xml version="1.0" encoding="UTF-8"?>']
        lines.append(f'<Sales date_from="{start.date()}" date_to="{end.date()}">')
        for s, u in sales:
            lines.append(
                f'  <Sale number="{s.number}" '
                f'date="{s.created_at.strftime("%Y-%m-%d")}" '
                f'time="{s.created_at.strftime("%H:%M:%S")}" '
                f'cashier="{u.name}" '
                f'total="{float(s.total_amount):.2f}" '
                f'discount="{float(s.discount_amount):.2f}" '
                f'payment="{s.payment_type.value}"/>'
            )
        lines.append("</Sales>")
        content = "\n".join(lines)
        return Response(
            content=content.encode("utf-8"),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=1c_export_{filename_date}.xml"},
        )


# ─── Foyda va Zarar (P&L) ─────────────────────────────────────────────────────

@router.get("/profit-loss")
def profit_loss_statement(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Foyda va Zarar hisoboti"""
    start, end = _date_range(date_from, date_to)

    # Daromad (sotuvlardan)
    revenue = (
        db.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
        .scalar()
    )

    # COGS (sotilgan tovarlar tannarxi)
    cogs = (
        db.query(func.coalesce(func.sum(SaleItem.cost_price * SaleItem.quantity), 0))
        .join(Sale)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
        .scalar()
    )

    # Gross profit
    gross_profit = float(revenue) - float(cogs)

    # Xarajatlar
    total_expenses = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.created_at >= start, Expense.created_at < end)
        .scalar()
    )

    # Net foyda
    net_profit = gross_profit - float(total_expenses)

    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "revenue": float(revenue),
        "cogs": float(cogs),
        "gross_profit": gross_profit,
        "gross_margin_pct": round(float(gross_profit / float(revenue) * 100), 2) if revenue else 0,  # type: ignore[call-overload,operator]
        "total_expenses": float(total_expenses),
        "net_profit": net_profit,
        "net_margin_pct": round(float(net_profit / float(revenue) * 100), 2) if revenue else 0,  # type: ignore[call-overload,operator]
    }
