"""
Dashboard Summary Endpoint — barcha dashboard ma'lumotlari bitta so'rovda
Frontend 6 ta parallel so'rov o'rniga shu 1 ta so'rovni ishlatadi.

T2.4: endpoint DEPRECATED (hech bir klient chaqirmaydi; asosiy dashboard — GET /reports/dashboard).
Har chaqiruv logga yoziladi — iste'molchi bor-yo'qligini bilish uchun. Raqamlar hisobotlar bilan mos:
Toshkent kuni, sotuv/qaytarish hujjatlari, UZS ekvivalent.
"""
import logging
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func, case as sa_case  # type: ignore

from app.database import get_db  # type: ignore
from app.core.branch_context import BranchContext, get_branch_context  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.core.report_scope import effective_ctx  # type: ignore
from app.core.roles import DASHBOARD_ROLES  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.sale import Sale, SaleItem  # type: ignore
from app.models.moliya import Transaction  # type: ignore
from app.models.warehouse import Warehouse  # type: ignore
from app.utils.report_utils import (  # type: ignore
    tx_cash_flow_filter, _date_range, local_today, sales_summary, resolve_dashboard_scope,
    sale_or_return_filter, doc_sign, sale_branch_filter, plan_summary,
)
from app.models.inventory import StockLevel  # type: ignore
from app.models.product import Product  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _parse_day(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana formati noto'g'ri (YYYY-MM-DD)")


@router.get("/summary", deprecated=True)
def dashboard_summary(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*DASHBOARD_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """
    DEPRECATED — /reports/dashboard dan foydalaning.
    Barcha dashboard widget ma'lumotlari bitta so'rovda.
    """
    logger.warning("deprecated /dashboard/summary user_id=%s", current_user.id)
    cid = current_user.company_id
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches

    # ── Sana filtr (Toshkent kuni; standart — bugun) ──────────
    d_from = _parse_day(date_from) or local_today()
    d_to = _parse_day(date_to) or d_from
    dt_from, dt_to = _date_range(d_from, d_to)

    # ── Branch/Warehouse Filters ──────────────────────────────
    eff_branch, branch_wh_ids = resolve_dashboard_scope(db, current_user, ctx, branch_id)
    wh_ids = branch_wh_ids
    sale_wh_ids = None if eff_branch else branch_wh_ids
    sale_flt = sale_branch_filter(eff_branch, db, cid) if eff_branch else None  # T1.9: filial snapshot'i
    if warehouse_id:
        wh_ok = db.query(Warehouse.id).filter(Warehouse.id == warehouse_id, Warehouse.company_id == cid).first()
        if not wh_ok:
            raise HTTPException(status_code=404, detail="Ombor topilmadi")
        if branch_wh_ids is not None and warehouse_id not in branch_wh_ids:
            wh_ids = []  # tanlangan ombor tanlangan filialniki emas
        else:
            wh_ids = [warehouse_id]
        sale_wh_ids, sale_flt = wh_ids, None  # aniq ombor filial snapshot'idan ustun

    # ── 1. Sotuvlar statistikasi: sotuv hujjatlari − qaytarishlar, UZS ──
    s = sales_summary(db, cid, dt_from, dt_to, wh_ids=sale_wh_ids, sale_filter=sale_flt)

    # ── 2. Kassa balansi — valyuta bo'yicha (CASE ifodalari) ──
    # Kassa filialga bog'liq, omborga emas: warehouse_id balansga ta'sir qilmaydi
    cur = func.coalesce(Transaction.currency_code, "UZS")
    tx_q = db.query(
        cur.label("cur"),
        func.coalesce(
            func.sum(sa_case((Transaction.type == "income", Transaction.amount), else_=0)), 0
        ).label("income"),
        func.coalesce(
            func.sum(sa_case((Transaction.type == "expense", Transaction.amount), else_=0)), 0
        ).label("expense"),
    ).filter(Transaction.company_id == cid, Transaction.voided_at.is_(None), tx_cash_flow_filter())
    cash_scope = "company"
    if eff_branch:
        tx_q = tx_q.filter(Transaction.branch_id == eff_branch)
        cash_scope = "branch"
    elif ctx.allowed_branch_ids is not None:
        tx_q = tx_q.filter(Transaction.branch_id.in_(list(ctx.allowed_branch_ids)))
        cash_scope = "branch"
    by_currency = {
        (r.cur or "UZS").upper(): float(r.income) - float(r.expense)
        for r in tx_q.group_by(cur).all()
    }
    # T2.7: umumiy kassa balansi — valyutalar UZS ekvivalentida (korxona kursi); valyuta bo'yicha qismi alohida qoladi
    from app.services.currency_service import rate_map, to_uzs
    _rates = rate_map(db, cid)
    cash_balance = float(sum((to_uzs(v, c, _rates) for c, v in by_currency.items()), 0))

    # ── 3. Kam qolgan mahsulotlar soni (T2.3 ta'rifi; T4.4: ombor bo'yicha min_qty hisobga olinadi) ──
    from app.utils.stock_utils import low_stock_count as _low_stock_count
    low_stock_count = _low_stock_count(db, cid, wh_ids)

    # ── 4. Eng ko'p sotilgan 5 ta mahsulot (qaytarilgan miqdor ayirilgan) ──
    net_qty = func.sum(doc_sign() * SaleItem.quantity)
    top_q = (
        db.query(
            Product.name,
            func.coalesce(net_qty, 0).label("qty"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == cid,
            Sale.created_at >= dt_from,
            Sale.created_at < dt_to,
            sale_or_return_filter(),
        )
    )
    if sale_wh_ids is not None:
        top_q = top_q.filter(Sale.warehouse_id.in_(sale_wh_ids))
    if sale_flt is not None:
        top_q = top_q.filter(sale_flt)
    top_products = top_q.group_by(Product.id, Product.name).order_by(net_qty.desc()).limit(5).all()

    # ── 5. Joriy oy savdo rejasi (T4.7): filial rejasi yig'indisi va sof sotuv fakti ──
    if eff_branch:
        plan_branches = [eff_branch]
    elif ctx.allowed_branch_ids is not None:
        plan_branches = list(ctx.allowed_branch_ids)
    else:
        plan_branches = None
    plan = plan_summary(db, cid, local_today().replace(day=1), plan_branches)

    return {
        "period": {"from": d_from.isoformat(), "to": d_to.isoformat()},
        "sales": {
            "count":    s["count"],
            "revenue":  s["net"],
            "paid":     s["cash"] + s["card"],
            "debt":     s["debt"],
        },
        "cash_balance": cash_balance,
        "cash_balance_by_currency": by_currency,
        "cash_balance_scope": cash_scope,
        "low_stock_count": int(low_stock_count),
        "top_products": [
            {"name": r.name, "qty": float(r.qty)} for r in top_products
        ],
        "plan": plan,
    }
