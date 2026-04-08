"""
Dashboard Summary Endpoint — barcha dashboard ma'lumotlari bitta so'rovda
Frontend 6 ta parallel so'rov o'rniga shu 1 ta so'rovni ishlatadi.
"""
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.sale import Sale, SaleItem  # type: ignore
from app.models.moliya import Transaction  # type: ignore
from app.models.inventory import StockLevel  # type: ignore
from app.models.product import Product  # type: ignore

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

MGMT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)


@router.get("/summary")
def dashboard_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MGMT_ROLES)),
):
    """
    Barcha dashboard widget ma'lumotlari bitta so'rovda.
    Oldin 6+ alohida API so'rovi kerak edi — endi 1 ta.
    """
    today = date.today()
    cid = current_user.company_id

    # ── Sana filtr ────────────────────────────────────────────
    if date_from:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
    else:
        dt_from = datetime(today.year, today.month, today.day)

    if date_to:
        dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    else:
        dt_to = dt_from + timedelta(days=1)

    # ── Branch/Warehouse Filters ──────────────────────────────
    from app.models.warehouse import Warehouse
    branch_wh_ids = None
    if branch_id:
        branch_wh_ids = [wh.id for wh in db.query(Warehouse.id).filter(Warehouse.branch_id == branch_id).all()]

    def filter_sales(q):
        if warehouse_id:
            return q.filter(Sale.warehouse_id == warehouse_id)
        if branch_wh_ids is not None:
            return q.filter(Sale.warehouse_id.in_(branch_wh_ids))
        return q

    # ── 1. Sotuvlar statistikasi (bitta query) ────────────────
    sale_q = db.query(
        func.coalesce(func.count(Sale.id), 0).label("sale_count"),
        func.coalesce(func.sum(Sale.total_amount), 0).label("total_revenue"),
        func.coalesce(func.sum(Sale.paid_amount), 0).label("total_paid"),
        func.coalesce(func.sum(Sale.total_amount - Sale.paid_amount), 0).label("total_debt"),
    ).filter(
        Sale.company_id == cid,
        Sale.created_at >= dt_from,
        Sale.created_at < dt_to,
    )
    sale_stats = filter_sales(sale_q).first()

    # ── 2. Kassa balansi — bitta query bilan income/expense (CASE ifodalari)
    from sqlalchemy import case as sa_case
    tx_q = db.query(
        func.coalesce(
            func.sum(sa_case((Transaction.type == "income", Transaction.amount), else_=0)), 0
        ).label("income"),
        func.coalesce(
            func.sum(sa_case((Transaction.type == "expense", Transaction.amount), else_=0)), 0
        ).label("expense"),
    ).filter(Transaction.company_id == cid)
    if branch_id:
        tx_q = tx_q.filter(Transaction.branch_id == branch_id)
    tx_row = tx_q.first()
    cash_balance = float(tx_row.income) - float(tx_row.expense)

    # ── 3. Kam qolgan mahsulotlar soni ────────────────────────
    low_stock_q = db.query(func.count(StockLevel.id)).filter(
        StockLevel.quantity <= Product.min_stock,
        StockLevel.product_id == Product.id,
        Product.company_id == cid,
        Product.is_deleted == False,
    )
    if warehouse_id:
        low_stock_q = low_stock_q.filter(StockLevel.warehouse_id == warehouse_id)
    elif branch_wh_ids is not None:
        low_stock_q = low_stock_q.filter(StockLevel.warehouse_id.in_(branch_wh_ids))
    low_stock_count = low_stock_q.scalar() or 0

    # ── 4. Eng ko'p sotilgan 5 ta mahsulot ────────────────────
    top_q = (
        db.query(
            Product.name,
            func.coalesce(func.sum(SaleItem.quantity), 0).label("qty"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= dt_from,
            Sale.created_at < dt_to,
        )
    )
    top_q = filter_sales(top_q)
    top_products = top_q.group_by(Product.id, Product.name).order_by(func.sum(SaleItem.quantity).desc()).limit(5).all()

    return {
        "period": {"from": dt_from.date().isoformat(), "to": (dt_to - timedelta(days=1)).date().isoformat()},
        "sales": {
            "count":    int(sale_stats.sale_count),
            "revenue":  float(sale_stats.total_revenue),
            "paid":     float(sale_stats.total_paid),
            "debt":     float(sale_stats.total_debt),
        },
        "cash_balance": cash_balance,
        "low_stock_count": int(low_stock_count),
        "top_products": [
            {"name": r.name, "qty": float(r.qty)} for r in top_products
        ],
    }
