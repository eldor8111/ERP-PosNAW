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
from app.models.currency import Currency
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

    er = func.coalesce(func.nullif(SaleItem.exchange_rate, 0), 1)

    qty_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed, SaleItem.quantity),
            (Sale.status == SaleStatus.refunded, -SaleItem.quantity),
            else_=0,
        )
    )
    revenue_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed, SaleItem.subtotal / er),
            (Sale.status == SaleStatus.refunded, -SaleItem.subtotal / er),
            else_=0,
        )
    )
    cost_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed, (SaleItem.cost_price * SaleItem.quantity) / er),
            (Sale.status == SaleStatus.refunded, -(SaleItem.cost_price * SaleItem.quantity) / er),
            else_=0,
        )
    )
    profit_expr = func.sum(
        case(
            (Sale.status == SaleStatus.completed,
             (SaleItem.subtotal - SaleItem.cost_price * SaleItem.quantity) / er),
            (Sale.status == SaleStatus.refunded,
             -(SaleItem.subtotal - SaleItem.cost_price * SaleItem.quantity) / er),
            else_=0,
        )
    )

    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Category.name.label("category_name"),
            func.coalesce(func.nullif(Product.wholesale_currency, 'UZS'), func.nullif(Product.cost_currency, 'UZS'), func.nullif(Product.sale_currency, 'UZS'), 'UZS').label("currency"),
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
        q.group_by(Product.id, Product.name, Product.sku, Category.name, func.coalesce(func.nullif(Product.wholesale_currency, 'UZS'), func.nullif(Product.cost_currency, 'UZS'), func.nullif(Product.sale_currency, 'UZS'), 'UZS'))
        .order_by(profit_expr.desc())
        .all()
    )

    # Merge currencies
    prod_map = {}
    for r in rows:
        pid = r.id
        if pid not in prod_map:
            prod_map[pid] = {
                "product_id": r.id,
                "product_name": r.name,
                "sku": r.sku,
                "category_name": r.category_name or "—",
                "qty_sold": 0.0,
                "revenue": {},
                "cost": {},
                "profit": {}
            }
        
        curr = r.currency
        prod_map[pid]["qty_sold"] += float(r.qty_sold or 0)
        prod_map[pid]["revenue"][curr] = float(r.revenue or 0)
        prod_map[pid]["cost"][curr] = float(r.cost or 0)
        prod_map[pid]["profit"][curr] = float(r.profit or 0)
        
    for p in prod_map.values():
        total_rev = sum(p["revenue"].values())
        total_profit = sum(p["profit"].values())
        p["margin_pct"] = round(total_profit / total_rev * 100, 1) if total_rev > 0 else 0
        
    return list(prod_map.values())


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
            func.coalesce(SaleItem.currency_code, 'UZS').label("currency"),
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
    rows = q.group_by(Batch.id, Product.name, func.coalesce(SaleItem.currency_code, 'UZS')).order_by(Batch.created_at.desc()).all()


    # Merge currencies
    batch_map = {}
    for r in rows:
        bid = r.id
        if bid not in batch_map:
            batch_map[bid] = {
                "batch_id": r.id,
                "product_name": r.product_name,
                "lot_number": r.lot_number or "N/A",
                "initial_quantity": float(r.initial_quantity or 0),
                "remaining_quantity": float(r.remaining_quantity or 0),
                "purchase_price": float(r.purchase_price or 0),
                "sold_qty": 0.0,
                "revenue": {},
                "profit": {}
            }
        
        curr = r.currency
        batch_map[bid]["sold_qty"] += float(r.sold_qty)
        batch_map[bid]["revenue"][curr] = float(r.revenue)
        batch_map[bid]["profit"][curr] = float(r.profit)
        
    for b in batch_map.values():
        total_rev = sum(b["revenue"].values())
        total_profit = sum(b["profit"].values())
        b["margin_pct"] = round(total_profit / total_rev * 100, 1) if total_rev > 0 else 0
        
    return list(batch_map.values())


@router.get("/customer-debts")
def customer_debts_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Debitor qarzdorlik — mijozlar bo'yicha"""
    q = db.query(Customer).filter(Customer.debt_balance > 0)
    q = q.filter(Customer.company_id == current_user.company_id)
    rows = q.order_by(Customer.debt_balance.desc()).all()
    # Valyuta bo'yicha guruhlash
    debt_by_currency = {}
    for c in rows:
        curr = c.debt_currency or 'UZS'
        debt_by_currency[curr] = debt_by_currency.get(curr, 0) + float(c.debt_balance)
    return {
        "total_debt": debt_by_currency,
        "count": len(rows),
        "items": [
            {
                "customer_id": c.id,
                "customer_name": c.name,
                "phone": c.phone,
                "debt_balance": float(c.debt_balance),
                "debt_currency": c.debt_currency or 'UZS',
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
    # Valyuta bo'yicha guruhlash
    debt_by_currency = {}
    for s in rows:
        curr = getattr(s, 'debt_currency', None) or 'UZS'
        debt_by_currency[curr] = debt_by_currency.get(curr, 0) + float(s.debt_balance)
    return {
        "total_debt": debt_by_currency,
        "count": len(rows),
        "items": [
            {
                "supplier_id": s.id,
                "supplier_name": s.name,
                "phone": s.phone,
                "debt_balance": float(s.debt_balance),
                "debt_currency": getattr(s, 'debt_currency', None) or 'UZS',
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
    """Foyda va Zarar hisoboti"""
    from app.models.moliya import ExpenseCategory

    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

    def get_sales_by_currency(status):
        rows = (
            db.query(func.coalesce(Currency.code, 'UZS').label("currency"), func.coalesce(func.sum(Sale.total_amount / func.coalesce(func.nullif(Sale.exchange_rate, 0), 1)), 0).label("amount"))
            .outerjoin(Currency, Currency.id == Sale.currency_id)
            .filter(Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end, Sale.status == status)
            .group_by(func.coalesce(Currency.code, 'UZS'))
            .all()
        )
        return {r.currency: float(r.amount) for r in rows}

    gross_revenue = get_sales_by_currency(SaleStatus.completed)
    total_returns = get_sales_by_currency(SaleStatus.refunded)
    
    net_revenue = {}
    for c, amt in gross_revenue.items():
        net_revenue[c] = amt - total_returns.get(c, 0)

    # COGS from SaleItems
    cogs_rows = (
        db.query(
            func.coalesce(SaleItem.currency_code, 'UZS').label("currency"),
            func.coalesce(func.sum(
                case(
                    (Sale.status == SaleStatus.completed, SaleItem.cost_price * SaleItem.quantity),
                    (Sale.status == SaleStatus.refunded, -SaleItem.cost_price * SaleItem.quantity),
                    else_=0,
                )
            ), 0).label("cogs")
        )
        .join(Sale)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= start, Sale.created_at < end,
            Sale.status.in_([SaleStatus.completed, SaleStatus.refunded]),
        )
        .group_by(func.coalesce(SaleItem.currency_code, 'UZS'))
        .all()
    )
    cogs = {r.currency: float(r.cogs) for r in cogs_rows}

    gross_profit = {}
    for c, rev in net_revenue.items():
        gross_profit[c] = rev - cogs.get(c, 0)
        
    for c, cost in cogs.items():
        if c not in gross_profit:
            gross_profit[c] = -cost

    # Expenses (only UZS)
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
    expenses_by_cat = [{"name": r.cat, "total": {"UZS": float(r.total)}} for r in exp_rows]
    total_expenses = {"UZS": sum(r["total"]["UZS"] for r in expenses_by_cat)}

    net_profit = {}
    for c, gp in gross_profit.items():
        net_profit[c] = gp - total_expenses.get(c, 0)
        
    for c, exp in total_expenses.items():
        if c not in net_profit:
            net_profit[c] = gross_profit.get(c, 0) - exp

    uzs_net_rev = net_revenue.get("UZS", 0)
    uzs_gp = gross_profit.get("UZS", 0)
    uzs_np = net_profit.get("UZS", 0)
    
    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "revenue": net_revenue,
        "gross_revenue": gross_revenue,
        "returns": total_returns,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": round(uzs_gp / (uzs_net_rev if uzs_net_rev else 1) * 100, 2),
        "expenses": {
            "total": total_expenses,
            "by_category": expenses_by_cat,
        },
        "net_profit": net_profit,
        "net_margin_pct": round(uzs_np / (uzs_net_rev if uzs_net_rev else 1) * 100, 2),
    }
