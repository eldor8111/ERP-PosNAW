"""Restoran hisobotlari API (12-bo'lim): GET /restaurant/reports/summary.

Ruxsat: hisobot rollari (admin, direktor, menejer, buxgalter) va filial doirasi — `report_scope_dep`
(cheklangan menejer faqat o'z filialini ko'radi). Faqat restoran korxonasi (`require_restaurant`).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.features import require_restaurant
from app.core.report_scope import ReportScope, report_scope_dep
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.document_numbers import tashkent_today
from app.services.restaurant_reports import build_report

router = APIRouter(prefix="/restaurant/reports", tags=["Restoran hisobotlari"],
                   dependencies=[Depends(require_restaurant)])


@router.get("/summary")
def summary(
    date_from: Optional[date] = Query(None, description="Toshkent sanasi (sukut: bugun)"),
    date_to: Optional[date] = Query(None, description="Toshkent sanasi (sukut: date_from)"),
    scope: ReportScope = Depends(report_scope_dep),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    d_from = date_from or tashkent_today()
    d_to = date_to or d_from
    return build_report(db, user.company_id, scope.branch_id, d_from, d_to)
