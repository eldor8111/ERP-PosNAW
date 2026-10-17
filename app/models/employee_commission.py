"""T4.7: sotuvchi (xodim) uchun sotuvdan foiz (komissiya) stavkasi.

Faqat hisobot uchun: to'lov yoki maosh yozuvi yaratilmaydi. Korxona + xodim bo'yicha bitta qator.
"""
from datetime import datetime, timezone

from sqlalchemy import (  # type: ignore
    CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint,
)

from app.database import Base  # type: ignore


class EmployeeCommission(Base):
    __tablename__ = "employee_commissions"
    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_employee_commissions_company_user"),
        CheckConstraint("percent BETWEEN 0 AND 100", name="ck_employee_commissions_percent"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    percent = Column(Numeric(5, 2), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
