"""T4.7: filial va sotuvchi uchun oylik savdo rejasi.

`user_id` NULL bo'lsa — filial rejasi, to'lgan bo'lsa — shu sotuvchining rejasi.
`period_month` — oyning 1-kuni (Date). Bir (filial, oy) uchun bitta filial rejasi va
bir (filial, sotuvchi, oy) uchun bitta sotuvchi rejasi (qisman unikal indekslar).
Oyning 1-kuni ekanligi migratsiyada CHECK bilan, ilovada esa `branch_plans._month_start` bilan ta'minlanadi.
"""
from datetime import datetime, timezone

from sqlalchemy import (  # type: ignore
    CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, text,
)

from app.database import Base  # type: ignore


class SalesTarget(Base):
    __tablename__ = "sales_targets"
    __table_args__ = (
        CheckConstraint("revenue_target >= 0", name="ck_sales_targets_nonneg"),
        Index("ix_sales_targets_company_month", "company_id", "period_month"),
        Index(
            "uq_sales_targets_branch", "branch_id", "period_month", unique=True,
            postgresql_where=text("user_id IS NULL"),
            sqlite_where=text("user_id IS NULL"),
        ),
        Index(
            "uq_sales_targets_user", "branch_id", "user_id", "period_month", unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
            sqlite_where=text("user_id IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    period_month = Column(Date, nullable=False)
    revenue_target = Column(Numeric(20, 2), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
