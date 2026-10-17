"""
Xodimlar hisobotlari (T4.7): kassirlar ish soati (`shifts` jadvalidan) va sotuvdan foiz (komissiya).

Faqat hisobot: to'lov yoki maosh yozuvi yaratilmaydi. To'liq davomat/grafik/maosh moduli bu yerda yo'q.
`shifts` faqat kassirlar uchun yuritiladi - omborchi/sotuvchi ish soati hisoblanmaydi.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import require_roles
from app.core.report_scope import ReportScope, report_scope_dep
from app.core.roles import REPORT_ROLES
from app.database import get_db
from app.models.employee_commission import EmployeeCommission
from app.models.sale import Sale
from app.models.shift import Shift
from app.models.user import User, UserRole
from app.models.user_company import UserCompany
from app.routers.branch_plans import scope_branch_ids
from app.utils.report_utils import (
    _date_range, currency_code_map, doc_sign, sale_branch_filter, sale_or_return_filter, sale_rate,
)

router = APIRouter(prefix="/staff-reports", tags=["Staff reports"])

RATE_WRITE_ROLES = (UserRole.admin, UserRole.director)
LONG_SHIFT_HOURS = 16      # shundan uzun smena "uzun" deb belgilanadi
OPEN_SHIFT_CAP_HOURS = 24  # yopilmay qolgan smena soati shu chegaradan oshib ketmaydi


def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def _naive_utc(dt: datetime) -> datetime:
    """`Shift.opened_at/closed_at` timezone'siz UTC saqlanadi: tz-aware qiymat UTC ga o'tkazilib tz olib tashlanadi."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _check_range(date_from: Optional[date], date_to: Optional[date]) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Boshlanish sanasi tugash sanasidan keyin bo'la olmaydi")


# ─── Ish soati ───────────────────────────────────────────────────────────────

@router.get("/work-hours")
def work_hours(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    cashier_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Kassirlar ish soati: smena soni, jami/o'rtacha soat, ochiq smena va uzun (>16 soat) smenalar.

    Soat = `closed_at - opened_at`; ochiq smenada hozirgi UTC vaqtgacha (24 soatdan oshmaydi).
    Smena `opened_at` bo'yicha davrga kiradi (kun chegarasi - Toshkent vaqti)."""
    cid = _company_id(current_user)
    _check_range(date_from, date_to)
    start, end = _date_range(date_from, date_to)
    q = (
        db.query(Shift, User.name)
        .join(User, User.id == Shift.cashier_id)
        .filter(Shift.company_id == cid,
                Shift.opened_at >= _naive_utc(start), Shift.opened_at < _naive_utc(end))
    )
    ids = scope_branch_ids(scope, branch_id)
    if ids is not None:
        q = q.filter(Shift.branch_id.in_(ids))
    if cashier_id:
        q = q.filter(Shift.cashier_id == cashier_id)

    now = _naive_utc(datetime.now(timezone.utc))
    result = {}
    for shift, name in q.order_by(Shift.opened_at).all():
        opened = _naive_utc(shift.opened_at)
        is_open = shift.closed_at is None
        finish = now if is_open else _naive_utc(shift.closed_at)
        hours = max((finish - opened).total_seconds() / 3600, 0.0)
        if is_open:
            hours = min(hours, OPEN_SHIFT_CAP_HOURS)
        entry = result.setdefault(shift.cashier_id, {
            "cashier_id": shift.cashier_id,
            "cashier_name": name,
            "shifts_count": 0,
            "total_hours": 0.0,
            "avg_shift_hours": 0.0,
            "open_shift": None,
            "long_shifts": [],
        })
        entry["shifts_count"] += 1
        entry["total_hours"] += hours
        if is_open:
            entry["open_shift"] = {
                "shift_id": shift.id, "branch_id": shift.branch_id,
                "opened_at": opened.isoformat(), "hours": round(hours, 2),
            }
        if hours > LONG_SHIFT_HOURS:
            entry["long_shifts"].append({
                "shift_id": shift.id, "branch_id": shift.branch_id,
                "opened_at": opened.isoformat(),
                "closed_at": None if is_open else _naive_utc(shift.closed_at).isoformat(),
                "hours": round(hours, 2), "is_open": is_open,
            })

    rows = list(result.values())
    for e in rows:
        e["avg_shift_hours"] = round(e["total_hours"] / e["shifts_count"], 2) if e["shifts_count"] else 0.0
        e["total_hours"] = round(e["total_hours"], 2)
    rows.sort(key=lambda e: e["total_hours"], reverse=True)
    return rows


# ─── Komissiya ───────────────────────────────────────────────────────────────

class CommissionRateIn(BaseModel):
    percent: Decimal = Field(..., ge=0, le=100, max_digits=5, decimal_places=2)


@router.get("/commissions")
def commissions(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    scope: ReportScope = Depends(report_scope_dep),
):
    """Sotuvchi bo'yicha sof sotuv (qaytarishlar ayirilgan) va foizdan komissiya (faqat hisobot).

    `net_sales`, `commission` - UZS ekvivalent; `by_currency` - sotuv valyutasi bo'yicha (cashier-report kabi)."""
    cid = _company_id(current_user)
    _check_range(date_from, date_to)
    start, end = _date_range(date_from, date_to)
    filters = [Sale.company_id == cid, Sale.created_at >= start, Sale.created_at < end, sale_or_return_filter()]
    ids = scope_branch_ids(scope, branch_id)
    if ids is not None:
        flt = [sale_branch_filter(b, db, cid) for b in ids]
        filters.append(or_(*flt) if flt else Sale.id.is_(None))
    rows = (
        db.query(
            User.id, User.name, Sale.currency_id,
            func.coalesce(func.sum(doc_sign() * Sale.total_amount / sale_rate()), 0).label("net_cur"),
            func.coalesce(func.sum(doc_sign() * Sale.total_amount), 0).label("net_uzs"),
        )
        .join(Sale, Sale.cashier_id == User.id)
        .filter(*filters)
        .group_by(User.id, User.name, Sale.currency_id)
        .all()
    )
    rates = {r.user_id: float(r.percent or 0) for r in db.query(EmployeeCommission).filter(
        EmployeeCommission.company_id == cid).all()}
    codes = currency_code_map(db, cid)

    sellers = {}
    for r in rows:
        e = sellers.setdefault(r.id, {
            "user_id": r.id, "user_name": r.name, "percent": rates.get(r.id, 0.0),
            "net_sales": 0.0, "commission": 0.0, "by_currency": {},
        })
        code = codes.get(r.currency_id, "UZS") if r.currency_id else "UZS"
        pct = e["percent"]
        net_cur = float(r.net_cur or 0)
        net_uzs = float(r.net_uzs or 0)
        e["net_sales"] += net_uzs
        e["commission"] += net_uzs * pct / 100
        cur = e["by_currency"].setdefault(code, {"net_sales": 0.0, "commission": 0.0})
        cur["net_sales"] += net_cur
        cur["commission"] += net_cur * pct / 100

    out = list(sellers.values())
    for e in out:
        e["net_sales"] = round(e["net_sales"], 2)
        e["commission"] = round(e["commission"], 2)
        for cur in e["by_currency"].values():
            cur["net_sales"] = round(cur["net_sales"], 2)
            cur["commission"] = round(cur["commission"], 2)
    out.sort(key=lambda e: e["net_sales"], reverse=True)
    return out


@router.put("/commission-rates/{user_id}")
def set_commission_rate(
    user_id: int,
    data: CommissionRateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*RATE_WRITE_ROLES)),
):
    """Xodimning sotuvdan foiz stavkasi (0-100). Boshqa korxona xodimi uchun 404."""
    cid = _company_id(current_user)
    target = db.query(User).filter(User.id == user_id).first()
    in_company = target is not None and (
        target.company_id == cid
        or db.query(UserCompany.id).filter(
            UserCompany.user_id == target.id, UserCompany.company_id == cid).first() is not None
    )
    if not in_company:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    row = db.query(EmployeeCommission).filter(
        EmployeeCommission.company_id == cid, EmployeeCommission.user_id == user_id).first()
    old = float(row.percent) if row else None
    if row:
        row.percent = data.percent
    else:
        row = EmployeeCommission(company_id=cid, user_id=user_id, percent=data.percent)
        db.add(row)
    db.flush()
    log_action(
        db, "COMMISSION_RATE_SET", "employee_commission", row.id, user_id=current_user.id,
        old_values={"percent": old} if old is not None else None,
        new_values={"user_id": user_id, "percent": float(data.percent)}, company_id=cid,
    )
    db.commit()
    return {"user_id": user_id, "percent": float(data.percent)}
