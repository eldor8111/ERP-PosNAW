"""
Moliya hisobotlari: xarajatlar, foyda, partiyalar, qarzdorliklar, P&L.
reports.py dan ajratilgan.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.batch import Batch
from app.models.category import Category
from app.models.customer import Customer
from app.models.moliya import Expense
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleStatus, SaleItemBatch
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.utils.report_utils import _date_range

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.super_admin)


@router.get("/expenses")
def expenses_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Xarajatlar hisoboti"""
    start, end = _date_range(date_from, date_to)
    q = db.query(Expense).filter(Expense.created_at >= start, Expense.created_at < end)
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


@router.get("/profit")
def profit_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Mahsulot va kategoriya bo'yicha foyda hisoboti (FIFO, vazvratlar chegirilgan)"""
    start, end = _date_range(date_from, date_to)

    qty_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed, SaleItem.quantity),
            (Sale.status == SaleStatus.refunded, -SaleItem.quantity),
            else_=0,
        )
    )
    revenue_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed, SaleItem.subtotal),
            (Sale.status == SaleStatus.refunded, -SaleItem.subtotal),
            else_=0,
        )
    )
    cost_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed, SaleItem.cost_price * SaleItem.quantity),
            (Sale.status == SaleStatus.refunded, -SaleItem.cost_price * SaleItem.quantity),
            else_=0,
        )
    )
    profit_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed,
             SaleItem.subtotal - SaleItem.cost_price * SaleItem.quantity),
            (Sale.status == SaleStatus.refunded,
             -(SaleItem.subtotal - SaleItem.cost_price * SaleItem.quantity)),
            else_=0,
        )
    )

    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Category.name.label("category_name"),
            qty_expr.label("qty_sold"),
            revenue_expr.label("revenue"),
            cost_expr.label("cost"),
            profit_expr.label("profit"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .filter(
            Sale.created_at >= start,
            Sale.created_at < end,
            Sale.status.in_([SaleStatus.completed, SaleStatus.refunded]),
        )
    )
    q = q.filter(Sale.company_id == current_user.company_id)
    rows = (
        q.group_by(Product.id, Product.name, Product.sku, Category.name)
        .order_by(profit_expr.desc())
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
            "margin_pct": round(
                float(r.profit or 0) / float(r.revenue or 1) * 100, 1
            ) if r.revenue and float(r.revenue) > 0 else 0,
        }
        for r in rows
    ]


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
            profit_expr.label("profit"),
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
            "margin_pct": round(float(r.profit / r.revenue * 100), 1) if r.revenue and float(r.revenue) > 0 else 0,
        }
        for r in rows
    ]


@router.get("/customer-debts")
def customer_debts_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Debitor qarzdorlik — mijozlar bo'yicha"""
    q = db.query(Customer).filter(Customer.debt_balance > 0)
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
                "usage_pct": round(float(c.debt_balance) / float(c.debt_limit) * 100, 1) if c.debt_limit else 0,
            }
            for c in rows
        ],
    }


@router.get("/supplier-debts")
def supplier_debts_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Kreditor qarzdorlik — supplierlar bo'yicha"""
    q = db.query(Supplier).filter(Supplier.debt_balance > 0)
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


@router.get("/profit-loss")
def profit_loss_statement(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Foyda va Zarar hisoboti (FIFO, vazvratlar chegirilgan, company filtered)"""
    from app.models.moliya import ExpenseCategory

    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

    gross_revenue = float(
        db.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
        .scalar()
    )

    total_returns = float(
        db.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.refunded)
        .scalar()
    )

    net_revenue = gross_revenue - total_returns

    cogs = float(
        db.query(func.coalesce(
            func.sum(
                case(
                    (Sale.status == SaleStatus.completed, SaleItem.cost_price * SaleItem.quantity),
                    (Sale.status == SaleStatus.refunded, -SaleItem.cost_price * SaleItem.quantity),
                    else_=0,
                )
            ), 0
        ))
        .join(Sale)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= start, Sale.created_at < end,
            Sale.status.in_([SaleStatus.completed, SaleStatus.refunded]),
        )
        .scalar()
    )

    gross_profit = net_revenue - cogs

    exp_rows = (
        db.query(
            func.coalesce(ExpenseCategory.name, "Boshqa").label("cat"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .outerjoin(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
        .filter(Expense.company_id == cid, Expense.created_at >= start, Expense.created_at < end)
        .group_by(ExpenseCategory.name)
        .all()
    )
    expenses_by_cat = [{"name": r.cat, "total": float(r.total)} for r in exp_rows]
    total_expenses = sum(r["total"] for r in expenses_by_cat)

    net_profit = gross_profit - total_expenses
    safe_revenue = net_revenue if net_revenue else 1

    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "revenue": net_revenue,
        "gross_revenue": gross_revenue,
        "returns": total_returns,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": round(gross_profit / safe_revenue * 100, 2),
        "expenses": {
            "total": total_expenses,
            "by_category": expenses_by_cat,
        },
        "net_profit": net_profit,
        "net_margin_pct": round(net_profit / safe_revenue * 100, 2),
    }
