"""
Moliya hisobotlari: xarajatlar, foyda, partiyalar, qarzdorliklar, P&L.
reports.py dan ajratilgan. Umumiy qoidalar → app/utils/report_utils.py

Foyda/tannarx hisobotlari asosiy valyutada (UZS): sotuv qatori tushumi
SaleItem.subtotal * SaleItem.exchange_rate, tannarx SaleItem.cost_price (UZS).
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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
    branch_warehouse_ids, sale_branch_filter, currency_rate_map, load_debtors, date_bounds,
)
from app.services.pnl_service import branch_condition, compute_pnl
from app.core.branch_context import BranchContext, get_branch_context
from app.core.report_scope import ReportScope, effective_ctx, report_scope_dep
from app.core.roles import REPORT_ROLES

router = APIRouter(prefix="/reports", tags=["Reports"])


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 2) if whole > 0 else 0.0


@router.get("/expenses")
def expenses_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Xarajatlar hisoboti (UZS)"""
    branch_id = scope.branch_id  # T2.1: cheklangan menejer uchun majburan o'z filiali
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(Expense)
        .options(joinedload(Expense.category), joinedload(Expense.branch))
        .filter(
            Expense.company_id == current_user.company_id,
            Expense.created_at >= start,
            Expense.created_at < end,
            Expense.voided_at.is_(None),
        )
    )
    if branch_id:  # -1 — filialsiz guruh (T2.2)
        q = q.filter(branch_condition(Expense.branch_id, current_user.company_id, branch_id))
    items = q.order_by(Expense.created_at.desc()).all()
    # T2.7: UZS ekvivalent (amount_uzs); eski yozuvlarda NULL -> amount
    def _uzs(e) -> float:
        return float(e.amount_uzs if e.amount_uzs is not None else e.amount)

    total = sum(_uzs(e) for e in items)
    return {
        "total": round(total, 2),
        "items": [
            {
                "id": e.id,
                "branch_id": e.branch_id,
                "branch_name": e.branch.name if e.branch else None,
                "wallet_id": e.wallet_id,
                "category": e.category.name if e.category else "—",
                "amount": _uzs(e),
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
    scope: ReportScope = Depends(report_scope_dep),
):
    """Mahsulot bo'yicha foyda (UZS, FIFO tannarx, qaytarishlar ayirilgan)"""
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1

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
    if branch_id:  # T1.9: Sale.branch_id snapshot'i
        q = q.filter(sale_branch_filter(branch_id, db, cid))
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Partiyalar (Batch) bo'yicha sotuv va foyda (UZS).

    Davr — sotuv sanasi: shu davrda sotilgan yoki shu davrda kelgan partiyalar
    ko'rsatiladi. Qisman qaytarilgan miqdor (SaleItem.returned_quantity)
    sotilgan miqdordan ayiriladi. Tushumda qator chegirmasi hisobga olinadi.
    """
    start, end = _date_range(date_from, date_to)
    cid = current_user.company_id
    branch_id = scope.branch_id  # T2.1

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


def _branch_name_map(db: Session, company_id: int) -> dict:
    from app.models.branch import Branch
    return {b.id: b.name for b in db.query(Branch.id, Branch.name).filter(Branch.company_id == company_id).all()}


def _scoped_debts_response(rows: list, build_item, names: dict, bid) -> dict:
    """Filial doirasidagi qarz hisoboti: har bir (kontragent, filial) alohida qator."""
    total: dict = {}
    items = []
    seen = set()
    for r in rows:
        for code, amt in r["debts"].items():
            total[code] = total.get(code, 0.0) + amt
        item = build_item(r, r["debts"], r["debt_uzs"])
        item["branch_id"] = r["branch_id"]
        item["branch_name"] = names.get(r["branch_id"]) if r["branch_id"] is not None else None
        items.append(item)
        seen.add(item.get("customer_id") or item.get("supplier_id"))
    return {
        "total_debt": {code: round(amt, 2) for code, amt in total.items()},
        "total_debt_uzs": round(sum(i["debt_uzs"] for i in items), 2),
        "count": len(seen),
        "items": items,
        "branch_id": bid,
        "scope": "branch",
    }


@router.get("/customer-debts")
def customer_debts_report(
    branch_id: Optional[int] = Query(None, description="Filial (-1 — filialsiz); bo'sh — butun korxona"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Debitor qarzdorlik — mijozlar bo'yicha (Mijozlar sahifasi bilan bir xil manba).

    T2.6: `branch_id` berilsa shu filial jurnali (`customer_debt_log`) bo'yicha sof qarz; berilmasa butun korxona
    va qo'shimcha `by_branch` + `unassigned` (filiallar yig'indisi `total_debt_uzs` ga teng)."""
    from app.services import customer_ledger as cl

    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches
    cid = current_user.company_id
    names = _branch_name_map(db, cid) if cid is not None else {}

    def _item(c, balances, debt_uzs):
        scoped = isinstance(c, dict)
        cust = c["customer"] if scoped else c
        limit = float(cust.debt_limit or 0)
        full_uzs = float(cust.debt_balance or 0) if scoped else debt_uzs
        return {
            "customer_id": cust.id,
            "customer_name": cust.name,
            "phone": cust.phone,
            "debts": balances,
            "debt_uzs": debt_uzs,
            "debt_limit": limit,
            "usage_pct": round(full_uzs / limit * 100, 1) if limit > 0 else None,
            "branch_id": cust.branch_id,
            "branch_name": names.get(cust.branch_id),
        }

    if cid is None:
        return _debts_report(db, Customer, cid, _item)
    bid, allowed = cl.check_branch_scope(db, current_user, ctx, branch_id)
    if bid or allowed is not None:
        data = cl.debt_by_branch(db, cid, bid, allowed)
        return _scoped_debts_response(data["customers"], _item, names, bid)
    out = _debts_report(db, Customer, cid, _item)
    data = cl.debt_by_branch(db, cid)
    out["by_branch"] = data["by_branch"]
    out["unassigned"] = data["unassigned"]
    out["scope"] = "company"
    return out


@router.get("/supplier-debts")
def supplier_debts_report(
    branch_id: Optional[int] = Query(None, description="Filial (-1 — filialsiz); bo'sh — butun korxona"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Kreditor qarzdorlik — ta'minotchilar bo'yicha (Moliya sahifasi bilan bir xil manba).

    T2.6: `branch_id` berilsa — shu filial omborlariga olingan xaridlar bo'yicha kreditorlik
    (`supplier_ledger.debt_by_branch`); `unallocated_payments` — xaridlarga bog'lanmagan to'lovlar."""
    from app.services import customer_ledger as cl
    from app.services import supplier_ledger as sl

    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches
    cid = current_user.company_id

    def _item(s, balances, debt_uzs):
        sup = s["supplier"] if isinstance(s, dict) else s
        return {
            "supplier_id": sup.id,
            "supplier_name": sup.name,
            "phone": sup.phone,
            "debts": balances,
            "debt_uzs": debt_uzs,
            "payment_terms": sup.payment_terms,
        }

    if cid is None:
        return _debts_report(db, Supplier, cid, _item)
    names = _branch_name_map(db, cid)
    bid, allowed = cl.check_branch_scope(db, current_user, ctx, branch_id)
    data = sl.debt_by_branch(db, cid, bid, allowed)
    if bid or allowed is not None:
        out = _scoped_debts_response(data["suppliers"], _item, names, bid)
    else:
        out = _debts_report(db, Supplier, cid, _item)
        out["scope"] = "company"
    out["by_branch"] = data["by_branch"]
    out["unassigned"] = data["unassigned"]
    out["unallocated_payments"] = data["unallocated_payments"]
    out["unallocated_payments_uzs"] = data["unallocated_payments_uzs"]
    return out


@router.get("/debt-collections")
def debt_collections_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None, description="Filial (kassa yoki qarz egasi); -1 — filialsiz"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Undirilgan qarzlar filial kesimida (T2.6): pul qaysi filial kassasiga tushgan (`cash_branch_id`) va
    qarz qaysi filialga tegishli (`branch_id`) — "A filialda olingan qarzni B undirdi".
    Manba: `customer_debt_log` (`payment` va ularning bekor qilinishi — `reversal`)."""
    from app.models.customer_debt_log import CustomerDebtLog as L
    from app.services import customer_ledger as cl

    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches
    cid = current_user.company_id
    bid, allowed = cl.check_branch_scope(db, current_user, ctx, branch_id)
    start, end = date_bounds(date_from, date_to)
    q = db.query(L.cash_branch_id, L.branch_id, L.currency, func.sum(L.delta), func.sum(L.delta_uzs)).filter(
        L.company_id == cid, L.kind.in_(cl.PAYMENT_KINDS), L.created_at >= start, L.created_at < end,
    )
    if bid == -1:
        q = q.filter(or_(L.cash_branch_id.is_(None), L.branch_id.is_(None)))
    elif bid:
        q = q.filter(or_(L.cash_branch_id == bid, L.branch_id == bid))
    elif allowed is not None:
        q = q.filter(or_(L.cash_branch_id.in_(list(allowed)), L.branch_id.in_(list(allowed))))
    rows = q.group_by(L.cash_branch_id, L.branch_id, L.currency).all()

    names = _branch_name_map(db, cid)

    def _name(b):
        return names.get(b) if b is not None else None

    matrix: dict = {}
    by_cash: dict = {}
    by_debt: dict = {}
    total_uzs = cross_uzs = 0.0

    def _add(bucket: dict, key, code, amt, uzs):
        e = bucket.setdefault(key, {"collected": {}, "collected_uzs": 0.0})
        e["collected"][code] = round(e["collected"].get(code, 0.0) + amt, 2)
        e["collected_uzs"] = round(e["collected_uzs"] + uzs, 2)

    for cash_b, debt_b, code, delta, delta_uzs in rows:
        code = (code or "UZS").upper()
        amt, uzs = -float(delta or 0), -float(delta_uzs or 0)
        _add(matrix, (cash_b, debt_b), code, amt, uzs)
        _add(by_cash, cash_b, code, amt, uzs)
        _add(by_debt, debt_b, code, amt, uzs)
        total_uzs += uzs
        if cash_b != debt_b:
            cross_uzs += uzs

    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "branch_id": bid,
        "total_uzs": round(total_uzs, 2),
        "cross_branch_uzs": round(cross_uzs, 2),
        "by_cash_branch": [
            {"branch_id": k, "branch_name": _name(k), **v}
            for k, v in sorted(by_cash.items(), key=lambda kv: -kv[1]["collected_uzs"])
        ],
        "by_debt_branch": [
            {"branch_id": k, "branch_name": _name(k), **v}
            for k, v in sorted(by_debt.items(), key=lambda kv: -kv[1]["collected_uzs"])
        ],
        "matrix": [
            {"cash_branch_id": k[0], "cash_branch_name": _name(k[0]), "debt_branch_id": k[1],
             "debt_branch_name": _name(k[1]), "cross_branch": k[0] != k[1], **v}
            for k, v in sorted(matrix.items(), key=lambda kv: -kv[1]["collected_uzs"])
        ],
    }


@router.get("/profit-loss")
def profit_loss_statement(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Foyda va Zarar hisoboti (UZS).

    Tushum — sotuv hujjatlari (Sale.total_amount, UZS), qaytarishlar — qaytarish
    hujjatlari; tannarx — sotilgan qatorlarning FIFO tannarxi (qaytarilgani ayirilgan).
    """
    start, end = _date_range(date_from, date_to)
    # T2.2: /finance/profit-loss va /reports/pnl-compare bilan bir xil servis; branch_id=-1 — filialsiz guruh
    p = compute_pnl(db, current_user.company_id, start, end, scope.branch_id)  # T2.1: cheklangan menejer — o'z filiali

    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "currency": "UZS",
        "gross_revenue": p["gross_revenue"],
        "returns": p["returns"],
        "revenue": p["net_revenue"],
        "cogs": p["net_cogs"],
        "gross_profit": p["gross_profit"],
        "gross_margin_pct": p["gross_margin_pct"],
        "other_income": p["other_income"],
        "other_income_note": p["other_income_note"],
        "expenses": p["expenses"],
        "net_profit": p["net_profit"],
        "net_margin_pct": p["net_margin_pct"],
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


@router.get("/pnl-compare")
def pnl_compare_report(
    p1_from: date = Query(..., description="1-davr boshlanishi"),
    p1_to: date = Query(..., description="1-davr tugashi"),
    p2_from: date = Query(..., description="2-davr boshlanishi"),
    p2_to: date = Query(..., description="2-davr tugashi"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
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
    if not has_access:
        # T2.5: tarif cheklovi API darajasida — ma'lumot qaytmaydi (frontend upgrade bannerini ko'rsatadi)
        raise HTTPException(
            status_code=403,
            detail={"code": "feature_not_in_tariff", "feature": "pnl_compare",
                    "message": "Bu hisobot tarifingizda yo'q"},
        )

    s1, e1 = _date_range(p1_from, p1_to)
    s2, e2 = _date_range(p2_from, p2_to)

    # T2.2: har ikki davr ham /profit-loss bilan bir xil servisdan (compute_pnl)
    d1 = compute_pnl(db, cid, s1, e1, scope.branch_id)  # T2.1
    d2 = compute_pnl(db, cid, s2, e2, scope.branch_id)
    e1_cats = {c["name"]: c["total"] for c in d1["expenses"]["by_category"]}
    e2_cats = {c["name"]: c["total"] for c in d2["expenses"]["by_category"]}

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
        "total_indirect_expenses": _diff_metric(d1["expenses"]["total"], d2["expenses"]["total"], is_income=False),
        "net_profit": _diff_metric(d1["net_profit"], d2["net_profit"], is_income=True),
        "net_margin_pct": _diff_metric(d1["net_margin_pct"], d2["net_margin_pct"], is_income=True),
    }

    # Barcha xarajat moddalarini birlashtirish
    all_cats = sorted(set(e1_cats) | set(e2_cats))
    expense_categories = []
    for cat in all_cats:
        v1 = e1_cats.get(cat, 0.0)
        v2 = e2_cats.get(cat, 0.0)
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

