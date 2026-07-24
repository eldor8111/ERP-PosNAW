from datetime import datetime, timezone

from sqlalchemy import Column, Integer, BigInteger, String, Numeric, ForeignKey, UniqueConstraint, JSON, DateTime  # type: ignore
from sqlalchemy.orm import relationship

from app.database import Base  # type: ignore

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    debt_balance = Column(Numeric(14, 2), default=0)
    debt_currency = Column(String(3), nullable=False, server_default="UZS", default='UZS')
    debt_balances = Column(JSON, nullable=False, server_default='{}')
    debt_limit = Column(Numeric(14, 2), default=0)
    loyalty_points = Column(BigInteger, default=0)
    tg_chat_id = Column(String(50), index=True, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    price_types = Column(Integer, default=0, server_default='0', nullable=False)

    # Skidka (sotuvda avtomatik qo'llaniladi)
    discount_percent = Column(Numeric(5, 2), default=0)
    price_type = Column(String(20), default="sale", server_default='sale')
    custom_prices = relationship("CustomerPrice", back_populates="customer")

    # Keshbek va Sodiqlik kartasi
    card_number = Column(String(20), index=True, nullable=True)
    cashback_percent = Column(Numeric(5, 2), default=0)
    bonus_balance = Column(Numeric(14, 2), default=0)
    total_spent = Column(Numeric(14, 2), default=0)

    debt_edited = Column(JSON, nullable=False, server_default='[]', default=list)

    __table_args__ = (
        UniqueConstraint('company_id', 'phone', name='uq_company_customer_phone'),
        UniqueConstraint('company_id', 'tg_chat_id', name='uq_company_customer_tg_chat_id'),
        UniqueConstraint('company_id', 'card_number', name='uq_company_customer_card_number'),
    )

    @property
    def tier(self):
        if self.loyalty_points >= 10000:
            return "Gold"
        elif self.loyalty_points >= 5000:
            return "Silver"
        elif self.loyalty_points >= 1000:
            return "Bronze"
        return "Standard"
