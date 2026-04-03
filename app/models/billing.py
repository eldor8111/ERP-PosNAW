"""
Billing modellari: Tariff, BalanceLog
Company modeliga qo'shimcha ustunlar migration orqali qo'shiladi.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from app.database import Base  # type: ignore


class Tariff(Base):
    __tablename__ = "tariffs"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100), nullable=False)           # "Boshlang'ich", "Pro", "Enterprise"
    description   = Column(Text, nullable=True)
    price_per_month = Column(Numeric(12, 2), default=0)           # oylik narx (so'm)
    duration_days = Column(Integer, default=30)                   # obuna muddati (kun)
    max_users     = Column(Integer, default=5)
    max_branches  = Column(Integer, default=1)
    is_active     = Column(Boolean, default=True)
    sort_order    = Column(Integer, default=0)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BalanceLog(Base):
    """Balans o'zgarishlari tarixi (audit log)"""
    __tablename__ = "balance_logs"

    id            = Column(Integer, primary_key=True, index=True)
    company_id    = Column(Integer, ForeignKey("companies.id"), nullable=False)
    amount        = Column(Numeric(18, 2), nullable=False)        # + kirim, - chiqim
    log_type      = Column(String(30), nullable=False)            # top_up | subscription | trial | refund
    note          = Column(String(255), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company       = relationship("Company", foreign_keys=[company_id])
    created_by    = relationship("User", foreign_keys=[created_by_id])
