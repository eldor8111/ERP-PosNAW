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
from app.models.moliya import Expense, ExpenseCategory, Transaction
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


def _diff_metric(p1_val: float, p2_val: float, is_income: bool = True) -> dict:
    p1 = round(float(p1_val or 0), 2)
    p2 = round(float(p2_val or 0), 2)
    diff = round(p2 - p1, 2)

    if p1 != 0:
        pct = round((diff / abs(p1)) * 100, 1)
    else:
        pct = None

    if diff == 0:
        status = "neutral"
    elif is_income:
        status = "good" if diff > 0 else "bad"
    else:
        status = "good" if diff < 0 else "bad"

    return {
        "p1": p1,
        "p2": p2,
        "diff": diff,
        "diff_pct": pct,
        "status": status,
    }


def _calc_pnl_data(db: Session, cid: int, start, end, branch_id: Optional[int]) -> dict:
    wh_ids = branch_warehouse_ids(db, cid, branch_id)
    sale_filters = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end]
    if wh_ids is not None:
        sale_filters.append(Sale.warehouse_id.in_(wh_ids))

    def _sum_sales(flt) -> float:
        val = db.query(func.coalesce(func.sum(Sale.total_amount), 0)).filter(*sale_filters, flt).scalar()
        return float(val or 0)

    gross_revenue = _sum_sales(sale_doc_filter())
    returns = _sum_sales(return_doc_filter())
    net_revenue = gross_revenue - returns

    # COGS for sales
    cogs_sales = float(
        db.query(func.coalesce(func.sum(item_cost_uzs()), 0))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*sale_filters, sale_doc_filter())
        .scalar() or 0
    )

    # Returns cost
    returns_cost = float(
        db.query(func.coalesce(func.sum(item_cost_uzs()), 0))
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(*sale_filters, return_doc_filter())
        .scalar() or 0
    )

    net_cogs = cogs_sales - returns_cost
    gross_profit = net_revenue - net_cogs
    gross_margin_pct = _pct(gross_profit, net_revenue)

    # Boshqa daromadlar (asosiy savdodan tashqari kirimlar)
    tx_filters = [
        Transaction.company_id == cid,
        Transaction.created_at >= start,
        Transaction.created_at < end,
        Transaction.type == "income",
        or_(
            Transaction.reference_type.is_(None),
            Transaction.reference_type.notin_(["sale", "sale_payment", "customer_debt_payment", "customer_payment"])
        )
    ]
    if branch_id:
        tx_filters.append(Transaction.branch_id == branch_id)
    other_income = float(
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(*tx_filters)
        .scalar() or 0
    )

    # Bilvosita xarajatlar (ExpenseCategories)
    exp_q = (
        db.query(
            ExpenseCategory.id.label("cat_id"),
            ExpenseCategory.name.label("cat_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total")
        )
        .select_from(Expense)
        .outerjoin(ExpenseCategory, ExpenseCategory.id == Expense.category_id)
        .filter(Expense.company_id == cid, Expense.created_at >= start, Expense.created_at < end)
    )
    if branch_id:
        exp_q = exp_q.filter(Expense.branch_id == branch_id)
    exp_rows = exp_q.group_by(ExpenseCategory.id, ExpenseCategory.name).all()

    expenses_by_cat = {
        (r.cat_name or "Boshqa xarajatlar"): round(float(r.total or 0), 2)
        for r in exp_rows
    }
    total_indirect_expenses = sum(expenses_by_cat.values())

    net_profit = gross_profit + other_income - total_indirect_expenses
    net_margin_pct = _pct(net_profit, net_revenue)

    return {
        "gross_revenue": gross_revenue,
        "cogs": cogs_sales,
        "returns": returns,
        "returns_cost": returns_cost,
        "net_revenue": net_revenue,
        "net_cogs": net_cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "other_income": other_income,
        "expenses_by_cat": expenses_by_cat,
        "total_indirect_expenses": total_indirect_expenses,
        "net_profit": net_profit,
        "net_margin_pct": net_margin_pct,
    }


@router.get("/pnl-compare")
def pnl_compare_report(
    p1_from: date = Query(..., description="1-davr boshlanishi"),
    p1_to: date = Query(..., description="1-davr tugashi"),
    p2_from: date = Query(..., description="2-davr boshlanishi"),
    p2_to: date = Query(..., description="2-davr tugashi"),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
):
    """
    Foyda va Zarar (P&L) Ikki davrni solishtirish hisoboti (Linko analitika modeli).
    Ustunlar: Birinchi davr, Ikkinchi davr, Farq (summa va foizda).
    Rang indikatsiyasi: Daromad oshsa yashil, xarajat oshsa qizil.
    """
    cid = current_user.company_id

    # Tarif ruxsatini tekshirish
    from app.services.tariff_guard import get_company_tariff
    tariff = get_company_tariff(db, cid)
    has_access = bool(tariff and tariff.has_pnl_compare) if tariff else True

    s1, e1 = _date_range(p1_from, p1_to)
    s2, e2 = _date_range(p2_from, p2_to)

    d1 = _calc_pnl_data(db, cid, s1, e1, branch_id)
    d2 = _calc_pnl_data(db, cid, s2, e2, branch_id)

    # Asosiy P&L qatorlari
    rows = {
        "gross_revenue": _diff_metric(d1["gross_revenue"], d2["gross_revenue"], is_income=True),
        "cogs": _diff_metric(d1["cogs"], d2["cogs"], is_income=False),
        "returns": _diff_metric(d1["returns"], d2["returns"], is_income=False),
        "returns_cost": _diff_metric(d1["returns_cost"], d2["returns_cost"], is_income=False),
        "net_revenue": _diff_metric(d1["net_revenue"], d2["net_revenue"], is_income=True),
        "gross_profit": _diff_metric(d1["gross_profit"], d2["gross_profit"], is_income=True),
        "gross_margin_pct": _diff_metric(d1["gross_margin_pct"], d2["gross_margin_pct"], is_income=True),
        "other_income": _diff_metric(d1["other_income"], d2["other_income"], is_income=True),
        "total_indirect_expenses": _diff_metric(d1["total_indirect_expenses"], d2["total_indirect_expenses"], is_income=False),
        "net_profit": _diff_metric(d1["net_profit"], d2["net_profit"], is_income=True),
        "net_margin_pct": _diff_metric(d1["net_margin_pct"], d2["net_margin_pct"], is_income=True),
    }

    # Barcha xarajat moddalarini birlashtirish
    all_cats = sorted(set(d1["expenses_by_cat"].keys()) | set(d2["expenses_by_cat"].keys()))
    expense_categories = []
    for cat in all_cats:
        v1 = d1["expenses_by_cat"].get(cat, 0.0)
        v2 = d2["expenses_by_cat"].get(cat, 0.0)
        diff_info = _diff_metric(v1, v2, is_income=False)
        expense_categories.append({
            "name": cat,
            **diff_info
        })
    expense_categories.sort(key=lambda c: max(c["p1"], c["p2"]), reverse=True)

    # Yuqori tablar (kartalar)
    tabs = {
        "gross_revenue": rows["gross_revenue"],
        "returns": rows["returns"],
        "net_revenue": rows["net_revenue"],
        "gross_profit": rows["gross_profit"],
    }

    return {
        "period1": {"from": str(p1_from), "to": str(p1_to)},
        "period2": {"from": str(p2_from), "to": str(p2_to)},
        "has_access": has_access,
        "currency": "UZS",
        "tabs": tabs,
        "rows": rows,
        "expense_categories": expense_categories,
    }

