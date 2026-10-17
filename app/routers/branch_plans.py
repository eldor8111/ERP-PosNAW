"""
Filial va sotuvchi savdo rejasi, bajarilish foizi va filiallar reytingi (T4.7).

Fakt = oyning sof savdosi (sotuv hujjatlari - qaytarishlar, bekor/kutilayotgan kirmaydi), UZS.
Hisob qoidasi `/sales-report/cashier-report` bilan bir xil (`report_utils.net_sales_by_branch`).
Filial kesimi: `Sale.branch_id` snapshot'i, bo'lmasa ombor filiali.
"""
import re
from datetime import date
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import require_roles
from app.core.report_scope import ReportScope, report_scope_dep
from app.core.roles import REPORT_ROLES
from app.database import get_db
from app.models.branch import Branch
from app.models.sales_target import SalesTarget
from app.models.user import User, UserRole
from app.models.user_branch import UserBranch
from app.models.user_company import UserCompany
from app.utils.report_utils import (
    days_in_month, local_today, month_range, net_sales_by_branch, plan_percent,
)

router = APIRouter(prefix="/branch-plans", tags=["Branch plans"])

PLAN_WRITE_ROLES = (UserRole.admin, UserRole.director)
_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

BRANCH_NOT_FOUND = "Filial topilmadi"
USER_NOT_FOUND = "Xodim topilmadi"
TARGET_NOT_FOUND = "Reja topilmadi"


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def parse_month(value: Optional[str]) -> date:
    """'YYYY-MM' -> oyning 1-kuni; bo'sh -> joriy oy (Toshkent); noto'g'ri format -> 422."""
    if value is None or str(value).strip() == "":
        return local_today().replace(day=1)
    m = _MONTH_RE.match(str(value).strip())
    if not m:
        raise HTTPException(status_code=422, detail="Oy formati noto'g'ri: YYYY-MM ko'rinishida kiriting")
    return date(int(m.group(1)), int(m.group(2)), 1)


def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def scope_branch_ids(scope: ReportScope, explicit_branch_id: Optional[int]) -> Optional[List[int]]:
    """Hisobot doirasi -> filial ro'yxati (None - butun korxona).

    Cheklangan menejer filial tanlamasa - ruxsat etilgan filiallari; aks holda tanlangan filial."""
    if scope.restricted and not explicit_branch_id:
        return list(scope.allowed_branch_ids or ())
    if scope.branch_id:
        return [scope.branch_id]
    return None


def _month_label(d: date) -> str:
    return d.strftime("%Y-%m")


def _target_out(t: SalesTarget) -> dict:
    return {
        "id": t.id,
        "branch_id": t.branch_id,
        "user_id": t.user_id,
        "month": _month_label(t.period_month),
        "revenue_target": float(t.revenue_target or 0),
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _month_clock(month_start: date):
    """Oy o'tish ko'rsatkichlari: (oydagi kunlar, o'tgan kunlar, qolgan kunlar). Kelajak oyida o'tgan = 0."""
    dim = days_in_month(month_start)
    today = local_today()
    cur = today.replace(day=1)
    if month_start < cur:
        return dim, dim, 0
    if month_start > cur:
        return dim, 0, dim
    return dim, today.day, dim - today.day


def _user_works_in_branch(db: Session, user: User, branch_id: int, company_id: int) -> bool:
    """Xodim shu filialda ishlaydimi: asosiy filial (users/user_companies) yoki qo'shimcha (user_branches)."""
    if user.branch_id == branch_id:
        return True
    if db.query(UserCompany.id).filter(
        UserCompany.user_id == user.id, UserCompany.company_id == company_id,
        UserCompany.branch_id == branch_id,
    ).first():
        return True
    return db.query(UserBranch.id).filter(
        UserBranch.user_id == user.id, UserBranch.company_id == company_id,
        UserBranch.branch_id == branch_id,
    ).first() is not None


# ─── Sxemalar ────────────────────────────────────────────────────────────────

class TargetIn(BaseModel):
    branch_id: int
    month: str
    revenue_target: Decimal = Field(..., ge=0, max_digits=20, decimal_places=2)
    user_id: Optional[int] = None

    @field_validator("month")
    @classmethod
    def _check_month(cls, v: str) -> str:
        if not _MONTH_RE.match((v or "").strip()):
            raise ValueError("Oy formati noto'g'ri: YYYY-MM ko'rinishida kiriting")
        return v.strip()


# ─── Rejalar ─────────────────────────────────────────────────────────────────

@router.put("/targets")
def upsert_target(
    data: TargetIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PLAN_WRITE_ROLES)),
):
    """Filial (yoki sotuvchi) oylik rejasini kiritish: (filial, [sotuvchi], oy) bo'yicha mavjud bo'lsa yangilanadi."""
    cid = _company_id(current_user)
    month_start = parse_month(data.month)
    branch = db.query(Branch).filter(Branch.id == data.branch_id, Branch.company_id == cid).first()
    if not branch:
        raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
    if data.user_id is not None:
        seller = db.query(User).filter(User.id == data.user_id).first()
        in_company = seller is not None and (
            seller.company_id == cid
            or db.query(UserCompany.id).filter(
                UserCompany.user_id == seller.id, UserCompany.company_id == cid).first() is not None
        )
        if not in_company:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        if not _user_works_in_branch(db, seller, data.branch_id, cid):
            raise HTTPException(status_code=400, detail="Bu xodim tanlangan filialda ishlamaydi")

    def _find() -> Optional[SalesTarget]:
        q = db.query(SalesTarget).filter(
            SalesTarget.company_id == cid, SalesTarget.branch_id == data.branch_id,
            SalesTarget.period_month == month_start,
        )
        if data.user_id is None:
            q = q.filter(SalesTarget.user_id.is_(None))
        else:
            q = q.filter(SalesTarget.user_id == data.user_id)
        return q.first()

    target = _find()
    old_value = float(target.revenue_target) if target else None
    if target:
        target.revenue_target = data.revenue_target
    else:
        target = SalesTarget(
            company_id=cid, branch_id=data.branch_id, user_id=data.user_id, period_month=month_start,
            revenue_target=data.revenue_target, created_by=current_user.id,
        )
        try:
            with db.begin_nested():
                db.add(target)
                db.flush()
        except IntegrityError:
            # Parallel so'rov oldin yozib qo'ygan: unikal indeks buzilsa 500 emas, mavjudini yangilaymiz
            target = _find()
            if not target:
                raise
            old_value = float(target.revenue_target)
            target.revenue_target = data.revenue_target
    log_action(
        db, "SALES_TARGET_SET", "sales_target", target.id, user_id=current_user.id,
        old_values={"revenue_target": old_value} if old_value is not None else None,
        new_values={"branch_id": data.branch_id, "user_id": data.user_id, "month": data.month,
                    "revenue_target": float(data.revenue_target)},
        company_id=cid, branch_id=data.branch_id,
    )
    db.commit()
    db.refresh(target)
    return _target_out(target)


@router.get("/targets")
def list_targets(
    month: Optional[str] = Query(None, description="YYYY-MM (bo'sh - joriy oy)"),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Oy rejalari ro'yxati (filial va sotuvchi rejalari)."""
    cid = _company_id(current_user)
    month_start = parse_month(month)
    q = db.query(SalesTarget).filter(SalesTarget.company_id == cid, SalesTarget.period_month == month_start)
    ids = scope_branch_ids(scope, branch_id)
    if ids is not None:
        q = q.filter(SalesTarget.branch_id.in_(ids))
    rows = q.order_by(SalesTarget.branch_id, SalesTarget.user_id).all()
    return [_target_out(t) for t in rows]


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(
    target_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*PLAN_WRITE_ROLES)),
):
    cid = _company_id(current_user)
    target = db.query(SalesTarget).filter(SalesTarget.id == target_id, SalesTarget.company_id == cid).first()
    if not target:
        raise HTTPException(status_code=404, detail=TARGET_NOT_FOUND)
    log_action(
        db, "SALES_TARGET_DELETE", "sales_target", target.id, user_id=current_user.id,
        old_values={"branch_id": target.branch_id, "user_id": target.user_id,
                    "month": _month_label(target.period_month),
                    "revenue_target": float(target.revenue_target or 0)},
        company_id=cid, branch_id=target.branch_id,
    )
    db.delete(target)
    db.commit()
    return Response(status_code=204)


# ─── Bajarilish va reyting ───────────────────────────────────────────────────

@router.get("/progress")
def plan_progress(
    month: Optional[str] = Query(None, description="YYYY-MM (bo'sh - joriy oy)"),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Filiallar rejasining bajarilishi: reja, fakt, foiz, qolgan, prognoz va reyting.

    Reyting - reja qo'yilgan filiallar orasida bajarilish foizi bo'yicha (1 - eng yaxshi);
    reja yo'q filialda `target`, `percent`, `rank` = null. `forecast = fact / o'tgan_kunlar * oydagi_kunlar`."""
    cid = _company_id(current_user)
    month_start = parse_month(month)
    start, end = month_range(month_start)
    dim, elapsed, days_left = _month_clock(month_start)

    bq = db.query(Branch).filter(Branch.company_id == cid, Branch.is_active.is_(True))
    ids = scope_branch_ids(scope, branch_id)
    if ids is not None:
        bq = bq.filter(Branch.id.in_(ids))
    branches = bq.order_by(Branch.name).all()

    targets = {
        t.branch_id: float(t.revenue_target or 0)
        for t in db.query(SalesTarget).filter(
            SalesTarget.company_id == cid, SalesTarget.period_month == month_start,
            SalesTarget.user_id.is_(None),
        ).all()
    }
    facts = net_sales_by_branch(db, cid, start, end)

    rows = []
    for b in branches:
        fact = round(facts.get(b.id, 0.0), 2)
        target = targets.get(b.id)
        rows.append({
            "branch_id": b.id,
            "branch_name": b.name,
            "target": target,
            "fact": fact,
            "percent": plan_percent(fact, target),
            "remaining": round(max(target - fact, 0), 2) if target is not None else None,
            "days_left": days_left,
            "forecast": round(fact / elapsed * dim, 2) if elapsed else None,
            "rank": None,
        })
    ranked = sorted((r for r in rows if r["percent"] is not None), key=lambda r: (-r["percent"], r["branch_name"]))
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["branch_name"] or ""))
    return rows


@router.get("/sellers")
def sellers_progress(
    month: Optional[str] = Query(None, description="YYYY-MM (bo'sh - joriy oy)"),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Sotuvchilar rejasi va fakti (`Sale.cashier_id` bo'yicha): reja yoki savdosi bor xodimlar."""
    cid = _company_id(current_user)
    month_start = parse_month(month)
    start, end = month_range(month_start)
    ids = scope_branch_ids(scope, branch_id)

    tq = db.query(SalesTarget).filter(
        SalesTarget.company_id == cid, SalesTarget.period_month == month_start,
        SalesTarget.user_id.isnot(None),
    )
    if ids is not None:
        tq = tq.filter(SalesTarget.branch_id.in_(ids))
    targets = {(t.branch_id, t.user_id): float(t.revenue_target or 0) for t in tq.all()}

    facts = {
        k: v for k, v in net_sales_by_branch(db, cid, start, end, by_seller=True).items()
        if k[0] is not None and k[1] is not None and (ids is None or k[0] in ids)
    }
    keys = set(targets) | set(facts)
    if not keys:
        return []
    branch_names = {b.id: b.name for b in db.query(Branch.id, Branch.name).filter(
        Branch.company_id == cid, Branch.id.in_({k[0] for k in keys})).all()}
    user_names = {u.id: u.name for u in db.query(User.id, User.name).filter(
        User.id.in_({k[1] for k in keys})).all()}

    rows = []
    for (bid, uid) in keys:
        if bid not in branch_names:  # boshqa korxona filiali ko'rinmaydi
            continue
        fact = round(facts.get((bid, uid), 0.0), 2)
        target = targets.get((bid, uid))
        rows.append({
            "branch_id": bid,
            "branch_name": branch_names[bid],
            "user_id": uid,
            "user_name": user_names.get(uid),
            "target": target,
            "fact": fact,
            "percent": plan_percent(fact, target),
            "remaining": round(max(target - fact, 0), 2) if target is not None else None,
        })
    rows.sort(key=lambda r: (r["branch_name"] or "", -r["fact"]))
    return rows
