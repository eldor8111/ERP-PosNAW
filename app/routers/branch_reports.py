"""
Filiallarni taqqoslash va konsolidatsiya hisoboti (T2.5).
Qoida va hisob-kitob → app/services/pnl_service.py (yagona P&L qoidasi, T2.2).
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.roles import REPORT_ROLES
from app.database import get_db
from app.models.user import User, UserRole
from app.services.pnl_service import build_branch_summary
from app.utils.report_utils import _date_range

router = APIRouter(prefix="/reports", tags=["Reports"])

DEBT_NOTE = "Qarz ustuni hozircha qo'shilmagan: qarz modeli filial kesimida yuritilmaydi"


@router.get("/branch-summary")
def branch_summary_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Filiallar kesimidagi jamlanma (UZS): har filial, "Filialsiz" guruhi va "Jami" qatori.

    Hammasi `/reports/profit-loss` bilan bir xil servisdan; `reconciled` — qatorlar yig'indisi
    butun korxona P&L ga tengligi. Cheklangan foydalanuvchi (T2.1) faqat o'z filiali(lari) qatorini
    oladi; "Filialsiz" va "Jami" ularga qaytmaydi (korxona jami ochilib qolmasligi uchun).
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Boshlanish sanasi tugash sanasidan keyin bo'la olmaydi")
    start, end = _date_range(date_from, date_to)
    data = build_branch_summary(db, current_user.company_id, start, end, ctx.allowed_branch_ids)
    return {
        "period": {"from": str(start.date()), "to": str((end - timedelta(days=1)).date())},
        "currency": "UZS",
        **data,
        "debt_note": DEBT_NOTE,
    }
