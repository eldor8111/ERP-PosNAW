"""
Moliya hisobotlari: xarajatlar, foyda, partiyalar, qarzdorliklar, P&L.
reports.py dan ajratilgan. Umumiy qoidalar → app/utils/report_utils.py

Foyda/tannarx hisobotlari asosiy valyutada (UZS): sotuv qatori tushumi
SaleItem.subtotal * SaleItem.exchange_rate, tannarx SaleItem.cost_price (UZS).
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.batch import Batch
from app.models.category import Category
from app.models.customer import Customer
from app.models.moliya import Expense, ExpenseCategory
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.utils.report_utils import (
    _date_range,
    sale_doc_filter, return_doc_filter, sale_or_return_filter, doc_sign,
    item_rate, item_revenue_uzs, item_cost_uzs,
    branch_warehouse_ids, currency_rate_map, load_debtors,
)

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.super_admin)


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 2) if whole > 0 else 0.0


@router.get("/expenses")
def expenses_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Xarajatlar hisoboti (UZS)"""
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(Expense)
        .options(joinedload(Expense.category))
        .filter(
            Expense.company_id == current_user.company_id,
            Expense.created_at >= start,
            Expense.created_at < end,
        )
    )
    if branch_id:
        q = q.filter(Expense.branch_id == branch_id)
    items = q.order_by(Expense.created_at.desc()).all()
    total = sum(float(e.amount) for e in items)
    return {
        "total": round(total, 2),
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
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Mahsulot bo'yicha foyda (UZS, FIFO tannarx, qaytarishlar ayirilgan)"""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

    q = (
        db.query(
            Product.id,
            Product.name,
            Product.sku,
            Category.name.label("category_name"),
            func.sum(doc_sign() * SaleItem.quantity).label("qty_sold"),
            func.sum(doc_sign() * item_revenue_uzs()).label("revenue"),
            func.sum(doc_sign() * item_cost_uzs()).label("cost"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .outerjoin(Category, Category.id == Product.category_id)
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
    rows = q.group_by(Product.id, Product.name, Product.sku, Category.name).all()

    result = []
    for r in rows:
        revenue = float(r.revenue or 0)
        cost = float(r.cost or 0)
        profit = revenue - cost
        result.append({
            "product_id": r.id,
            "product_name": r.name,
            "sku": r.sku,
            "category_name": r.category_name or "—",
            "qty_sold": round(float(r.qty_sold or 0), 3),
            "revenue": round(revenue, 2),
            "cost": round(cost, 2),
            "profit": round(profit, 2),
            "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
        })
    result.sort(key=lambda p: p["profit"], reverse=True)
    return result


@router.get("/batches")
def batches_profit_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Partiyalar (Batch) bo'yicha sotuv va foyda (UZS).

    Davr — sotuv sanasi: shu davrda sotilgan yoki shu davrda kelgan partiyalar
    ko'rsatiladi. Qisman qaytarilgan miqdor (SaleItem.returned_quantity)
    sotilgan miqdordan ayiriladi. Tushumda qator chegirmasi hisobga olinadi.
    """
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

    net_ratio = (SaleItem.quantity - func.coalesce(SaleItem.returned_quantity, 0)) / func.nullif(SaleItem.quantity, 0)
    sold_qty = SaleItemBatch.quantity * net_ratio
    unit_revenue_uzs = SaleItem.subtotal / func.nullif(SaleItem.quantity, 0) * item_rate()
    sold = (
        db.query(
            SaleItemBatch.batch_id.label("batch_id"),
            func.sum(sold_qty).label("sold_qty"),
            func.sum(sold_qty * unit_revenue_uzs).label("revenue"),
            func.sum(sold_qty * SaleItemBatch.unit_cost).label("cost"),
        )
        .join(SaleItem, SaleItem.id == SaleItemBatch.sale_item_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= start,
            Sale.created_at < end,
            sale_doc_filter(),
        )
        .group_by(SaleItemBatch.batch_id)
        .subquery()
    )

    q = (
        db.query(
            Batch.id,
            Product.name.label("product_name"),
            Batch.lot_number,
            Batch.initial_quantity,
            Batch.quantity.label("remaining_quantity"),
            Batch.purchase_price,
            Batch.created_at,
            sold.c.sold_qty,
            sold.c.revenue,
            sold.c.cost,
        )
        .join(Product, Product.id == Batch.product_id)
        .outerjoin(sold, sold.c.batch_id == Batch.id)
        .filter(
            Batch.company_id == cid,
            or_(sold.c.batch_id.isnot(None), and_(Batch.created_at >= start, Batch.created_at < end)),
        )
    )
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    if wh_ids is not None:
        q = q.filter(Batch.warehouse_id.in_(wh_ids))
    rows = q.order_by(Batch.created_at.desc()).all()

    result = []
    for r in rows:
        revenue = float(r.revenue or 0)
        cost = float(r.cost or 0)
        profit = revenue - cost
        result.append({
            "batch_id": r.id,
            "product_name": r.product_name,
            "lot_number": r.lot_number or "—",
            "initial_quantity": float(r.initial_quantity or 0),
            "remaining_quantity": float(r.remaining_quantity or 0),
            "purchase_price": float(r.purchase_price or 0),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "sold_qty": round(float(r.sold_qty or 0), 3),
            "revenue": round(revenue, 2),
            "cost": round(cost, 2),
            "profit": round(profit, 2),
            "margin_pct": round(profit / revenue * 100, 1) if revenue > 0 else 0,
        })
    return result


def _debts_report(db: Session, model, company_id: int, build_item):
    """Qarzdorlar ro'yxati: valyuta bo'yicha qarz (debt_balances) va UZS ekvivalenti."""
    rates = currency_rate_map(db, company_id)
    total: dict = {}
    items = []
    for obj, balances in load_debtors(db, model, company_id):
        for code, amt in balances.items():
            total[code] = total.get(code, 0.0) + amt
        debt_uzs = sum(amt * rates.get(code, 1.0) for code, amt in balances.items())
        items.append(build_item(obj, balances, round(debt_uzs, 2)))
    items.sort(key=lambda i: i["debt_uzs"], reverse=True)
    return {
        "total_debt": {code: round(amt, 2) for code, amt in total.items()},
        "total_debt_uzs": round(sum(i["debt_uzs"] for i in items), 2),
        "count": len(items),
        "items": items,
    }


@router.get("/customer-debts")
def customer_debts_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Debitor qarzdorlik — mijozlar bo'yicha (Mijozlar sahifasi bilan bir xil manba)"""
    def _item(c, balances, debt_uzs):
        limit = float(c.debt_limit or 0)
        return {
            "customer_id": c.id,
            "customer_name": c.name,
            "phone": c.phone,
            "debts": balances,
            "debt_uzs": debt_uzs,
            "debt_limit": limit,
            "usage_pct": round(debt_uzs / limit * 100, 1) if limit > 0 else None,
        }
    return _debts_report(db, Customer, current_user.company_id, _item)


@router.get("/supplier-debts")
def supplier_debts_report(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Kreditor qarzdorlik — ta'minotchilar bo'yicha (Moliya sahifasi bilan bir xil manba)"""
    def _item(s, balances, debt_uzs):
        return {
            "supplier_id": s.id,
            "supplier_name": s.name,
            "phone": s.phone,
            "debts": balances,
            "debt_uzs": debt_uzs,
            "payment_terms": s.payment_terms,
        }
    return _debts_report(db, Supplier, current_user.company_id, _item)


@router.get("/profit-loss")
def profit_loss_statement(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """Foyda va Zarar hisoboti (UZS).

    Tushum — sotuv hujjatlari (Sale.total_amount, UZS), qaytarishlar — qaytarish
    hujjatlari; tannarx — sotilgan qatorlarning FIFO tannarxi (qaytarilgani ayirilgan).
    """
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id

    sale_filters = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end]
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    if wh_ids is not None:
        sale_filters.append(Sale.warehouse_id.in_(wh_ids))

    def _sum_total(doc_filter) -> float:
        value = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(*sale_filters, doc_filter).scalar()
        return float(value or 0)

    gross_revenue = _sum_total(sale_doc_filter())
    returns = _sum_total(return_doc_filter())
    revenue = gross_revenue - returns

    cogs = float(
        db.query(func.coalesce(func.sum(doc_sign() * item_cost_uzs()), 0))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*sale_filters, sale_or_return_filter())
        .scalar() or 0
    )
    gross_profit = revenue - cogs

    exp_q = (
        db.query(ExpenseCategory.name.label("cat"), func.coalesce(func.sum(Expense.amount), 0).label("total"))
        .select_from(Expense)
        .outerjoin(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
        .filter(Expense.company_id == cid, Expense.created_at >= start, Expense.created_at < end)
    )
    if branch_id:
        exp_q = exp_q.filter(Expense.branch_id == branch_id)
    by_category = [
        {"name": r.cat or "Boshqa", "total": round(float(r.total or 0), 2)}
        for r in exp_q.group_by(ExpenseCategory.name).all()
    ]
    by_category.sort(key=lambda c: c["total"], reverse=True)
    total_expenses = sum(c["total"] for c in by_category)
    net_profit = gross_profit - total_expenses

    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "currency": "UZS",
        "gross_revenue": round(gross_revenue, 2),
        "returns": round(returns, 2),
        "revenue": round(revenue, 2),
        "cogs": round(cogs, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_margin_pct": _pct(gross_profit, revenue),
        "expenses": {
            "total": round(total_expenses, 2),
            "by_category": by_category,
        },
        "net_profit": round(net_profit, 2),
        "net_margin_pct": _pct(net_profit, revenue),
    }
