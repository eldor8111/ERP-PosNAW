"""T4.2: fiskal qamrov hisoboti — qaysi filial/fiskal modul orqali nechta chek fiskallangan va nechtasi fiskallanmagan.

Fiskal modullar reyestri T3.18 da `fiscal_devices` (`/fiscal-devices`) sifatida yaratilgan; bu router faqat
o'qish hisobotlarini beradi. Sotuv hujjatlari (`sale_doc_filter`) va qaytarish hujjatlari (`is_return_doc`, R...)
alohida hisoblanadi: qaytarish hujjati fiskallanmagan chek hisoblanmaydi."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.fiscal_device import FiscalDevice
from app.models.sale import Sale
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.utils.report_utils import (
    date_bounds, is_return_doc, resolve_dashboard_scope, return_doc_filter, sale_doc_filter,
)

router = APIRouter(prefix="/fiscal", tags=["Fiscal"])

FISCAL_REPORT_ROLES = (UserRole.admin, UserRole.director, UserRole.accountant)
NO_BRANCH_NAME = "Filialsiz"


def _scoped_sales(db: Session, user: User, ctx: BranchContext, branch_id, date_from, date_to):
    """Korxona + sana + filial doirasi bo'yicha sotuv so'rovi uchun (filter ro'yxati, effektiv filial ifodasi).
    Effektiv filial: `Sale.branch_id` snapshot'i, bo'sh eski sotuvlarda ombor filiali."""
    cid = user.company_id
    scope_branch, _wh = resolve_dashboard_scope(db, user, ctx, branch_id)   # begona filial 404, ruxsatsiz 403
    start, end = date_bounds(date_from, date_to)
    eff_branch = func.coalesce(Sale.branch_id, Warehouse.branch_id)
    conds = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end]
    if scope_branch:
        conds.append(eff_branch == scope_branch)
    elif getattr(ctx, "allowed_branch_ids", None) is not None:
        conds.append(eff_branch.in_(list(ctx.allowed_branch_ids)))
    return conds, eff_branch


@router.get("/coverage")
def fiscal_coverage(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FISCAL_REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Filial va fiskal modul bo'yicha: jami sotuv, fiskallangan, fiskallanmagan (+ alohida qaytarish hujjatlari).
    `fiscalized` = `fiscal_sign` bor sotuvlar; fiskallanmagan chekda modul noma'lum (`factory_id` NULL)."""
    conds, eff_branch = _scoped_sales(db, user, ctx, branch_id, date_from, date_to)
    sale_doc = sale_doc_filter()
    rows = (
        db.query(
            eff_branch.label("bid"),
            Sale.fiscal_factory_id.label("fid"),
            func.sum(case((sale_doc, 1), else_=0)).label("total"),
            func.sum(case((sale_doc & Sale.fiscal_sign.isnot(None), 1), else_=0)).label("fiscalized"),
            func.sum(case((return_doc_filter(), 1), else_=0)).label("returns"),
        )
        .outerjoin(Warehouse, Warehouse.id == Sale.warehouse_id)
        .filter(*conds)
        .group_by(eff_branch, Sale.fiscal_factory_id)
        .all()
    )
    branch_names = {
        b.id: b.name for b in db.query(Branch.id, Branch.name).filter(Branch.company_id == user.company_id).all()
    }
    device_ids = {
        d.factory_id: d.id
        for d in db.query(FiscalDevice.id, FiscalDevice.factory_id).filter(FiscalDevice.company_id == user.company_id)
    }
    out = []
    for r in rows:
        total, fiscalized, returns = int(r.total or 0), int(r.fiscalized or 0), int(r.returns or 0)
        if not total and not returns:
            continue
        out.append({
            "branch_id": r.bid,
            "branch_name": branch_names.get(r.bid) if r.bid else NO_BRANCH_NAME,
            "terminal_id": device_ids.get(r.fid) if r.fid else None,
            "factory_id": r.fid,
            "total_sales": total,
            "fiscalized": fiscalized,
            "unfiscalized": total - fiscalized,
            "returns": returns,
        })
    out.sort(key=lambda x: (x["branch_name"] or "", x["factory_id"] or ""))
    return out


@router.get("/unfiscalized")
def fiscal_unfiscalized(
    response: Response,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    branch_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FISCAL_REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Fiskallanmagan (`fiscal_sign IS NULL`) sotuv cheklari ro'yxati; jami soni `X-Total-Count` headerida."""
    conds, eff_branch = _scoped_sales(db, user, ctx, branch_id, date_from, date_to)
    conds += [sale_doc_filter(), Sale.fiscal_sign.is_(None)]
    base = db.query(Sale.id).outerjoin(Warehouse, Warehouse.id == Sale.warehouse_id).filter(*conds)
    response.headers["X-Total-Count"] = str(base.count())
    rows = (
        db.query(
            Sale.id, Sale.number, Sale.created_at, Sale.total_amount, Sale.payment_type,
            eff_branch.label("bid"), User.name.label("cashier_name"),
        )
        .outerjoin(Warehouse, Warehouse.id == Sale.warehouse_id)
        .outerjoin(User, User.id == Sale.cashier_id)
        .filter(*conds)
        .order_by(Sale.created_at.desc(), Sale.id.desc())
        .offset(skip).limit(limit).all()
    )
    branch_names = {
        b.id: b.name for b in db.query(Branch.id, Branch.name).filter(Branch.company_id == user.company_id).all()
    }
    return [
        {
            "id": r.id, "number": r.number, "created_at": r.created_at,
            "total_amount": r.total_amount,
            "payment_type": getattr(r.payment_type, "value", r.payment_type),
            "branch_id": r.bid, "branch_name": branch_names.get(r.bid) if r.bid else NO_BRANCH_NAME,
            "cashier_name": r.cashier_name,
        }
        for r in rows
    ]
