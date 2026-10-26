# -*- coding: utf-8 -*-
"""
UzumTransaction — Uzum Bank Merchant API orqali kelgan to'lovlar tarixi.

Rasmiy hujjat: https://developer.uzumbank.uz/merchant-api/
Statuslar:
  CREATED   - tranzaksiya yaratildi (/create)
  CONFIRMED - to'lov tasdiqlandi va qabul qilindi (/confirm)
  REVERSED  - to'lov bekor qilindi / qaytarildi (/reverse)
  FAILED    - xatolik yoki 30 daqiqalik vaqt tugagan tranzaksiya
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database import Base  # type: ignore


class UzumTransaction(Base):
    __tablename__ = "uzum_transactions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    trans_id = Column(String(64), unique=True, nullable=False, index=True)  # Uzum Bank UUID
    service_id = Column(BigInteger, nullable=False)
    amount = Column(BigInteger, nullable=False)  # tiyinda (so'm x 100)
    status = Column(String(20), nullable=False, default="CREATED", index=True)  # CREATED | CONFIRMED | REVERSED | FAILED
    account_identifier = Column(String(100), nullable=True, index=True)  # order_id / org_code / user_id
    
    # Uzum Bank /confirm ma'lumotlari
    payment_source = Column(String(50), nullable=True)  # UZCARD, HUMO, INSTALLMENT, etc.
    tariff = Column(String(50), nullable=True)  # masalan: "003", "15-0-4"
    processing_ref = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    card_type = Column(Integer, nullable=True)  # 1 - yuridik, 2 - jismoniy
    
    # Timestamps (unix ms)
    trans_time = Column(BigInteger, nullable=True)
    confirm_time = Column(BigInteger, nullable=True)
    reverse_time = Column(BigInteger, nullable=True)
    
    # Moliyaviy log bilan bog'lanish
    log_id = Column(Integer, ForeignKey("balance_logs.id"), nullable=True)
    raw_params = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", foreign_keys=[company_id])
    log = relationship("BalanceLog", foreign_keys=[log_id])
