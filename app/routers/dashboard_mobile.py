from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore

from app.database import get_db  # type: ignore
from app.core.branch_context import BranchContext, get_branch_context  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.core.report_scope import effective_ctx  # type: ignore
from app.core.roles import DASHBOARD_ROLES  # type: ignore
from app.models.user import User  # type: ignore
from app.models.sale import Sale, SaleItem  # type: ignore
from app.models.product import Product  # type: ignore
from app.utils.report_utils import (  # type: ignore
    _today_range, local_today, local_day_start, sales_summary, resolve_dashboard_scope,
    sale_or_return_filter, doc_sign, item_revenue_uzs, sale_branch_filter,
)

router = APIRouter(prefix="/mobile/dashboard", tags=["Mobile Dashboard"])


@router.get("/summary")
def get_mobile_summary(
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr (None = joriy kontekst / hammasi)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*DASHBOARD_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Bugungi xulosa (Toshkent kuni, UZS): sotuvlar − qaytarishlar. Hujjat/status filtri va kurs
    `sales_summary` da. `cash_in_register` — faqat naqd to'lovlar (karta alohida)."""
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi
    eff_branch, wh_ids = resolve_dashboard_scope(db, current_user, ctx, branch_id)
    start, end = _today_range()
    # T1.9: aniq filial — Sale.branch_id snapshot'i; aks holda (ruxsat etilgan filiallar) ombor ro'yxati
    s = sales_summary(
        db, current_user.company_id, start, end,
        wh_ids=None if eff_branch else wh_ids,
        sale_filter=sale_branch_filter(eff_branch, db, current_user.company_id) if eff_branch else None,
    )
    return {
        "today_sales": s["net"],
        "cash_in_register": s["cash"],
        "debt_sales": s["debt"],
        "gross": s["gross"],
        "returns": s["returns"],
        "count": s["count"],
        "card": s["card"],
        "date": local_today().isoformat(),
        "branch_id": eff_branch,
        "currency": "UZS",
    }


@router.get("/top-products")
def get_top_products(
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr"),
    days: int = Query(30, ge=1, le=365, description="Oxirgi necha kun (bugun kiradi)"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*DASHBOARD_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Eng ko'p sotilgan mahsulotlar — oxirgi `days` kun, qaytarilgan miqdor ayirilgan (JOIN bilan bir so'rov)."""
    ctx = effective_ctx(current_user, ctx)  # T2.1: reports.all_branches huquqi
    eff_branch, wh_ids = resolve_dashboard_scope(db, current_user, ctx, branch_id)
    start = local_day_start(local_today() - timedelta(days=days - 1))
    net_qty = func.sum(doc_sign() * SaleItem.quantity)
    q = (
        db.query(
            Product.id,
            Product.name,
            func.coalesce(net_qty, 0).label("total_qty"),
            func.coalesce(func.sum(doc_sign() * item_revenue_uzs()), 0).label("revenue"),
        )
        .join(SaleItem, SaleItem.product_id == Product.id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .filter(
            Sale.company_id == current_user.company_id,
            Product.company_id == current_user.company_id,
            Sale.created_at >= start,
            sale_or_return_filter(),
        )
    )
    if eff_branch:
        q = q.filter(sale_branch_filter(eff_branch, db, current_user.company_id))
    elif wh_ids is not None:
        q = q.filter(Sale.warehouse_id.in_(wh_ids))
    rows = q.group_by(Product.id, Product.name).order_by(net_qty.desc()).limit(limit).all()
    return [
        {"id": r.id, "name": r.name, "sold_quantity": float(r.total_qty), "revenue_uzs": float(r.revenue)}
        for r in rows
    ]
