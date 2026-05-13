"""
PaymeTransaction — Payme Merchant API orqali kelgan to'lovlar tarixi.

state:  1 = yaratilgan (CreateTransaction)
        2 = bajarildi (PerformTransaction)
       -1 = bekor qilindi (CancelTransaction)
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base  # type: ignore


class PaymeTransaction(Base):
    __tablename__ = "payme_transactions"

    id               = Column(Integer, primary_key=True, index=True)
    company_id       = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    payme_id         = Column(String(25), unique=True, nullable=False, index=True)
    amount           = Column(BigInteger, nullable=False)          # tiyinda (so'm × 100)
    state            = Column(Integer, nullable=False, default=1)  # 1 | 2 | -1
    reason           = Column(Integer, nullable=True)              # bekor qilish sababi
    create_time      = Column(BigInteger, nullable=True)           # ms timestamp
    perform_time     = Column(BigInteger, nullable=True)
    cancel_time      = Column(BigInteger, nullable=True)
    account_org_code = Column(String(20), nullable=True)           # qaysi org_code uchun
    log_id           = Column(Integer, ForeignKey("balance_logs.id"), nullable=True)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", foreign_keys=[company_id])
    log     = relationship("BalanceLog", foreign_keys=[log_id])
