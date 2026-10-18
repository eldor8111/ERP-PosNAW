from datetime import datetime, timezone

from sqlalchemy import Column, Integer, BigInteger, String, Numeric, ForeignKey, UniqueConstraint, CheckConstraint, Index, JSON, DateTime, Boolean, true  # type: ignore
from sqlalchemy.orm import relationship

from app.database import Base  # type: ignore

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), nullable=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
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
    receipt_format = Column(String(20), nullable=True, default=None)

    debt_edited = Column(JSON, nullable=False, server_default='[]', default=list)

    # Distribyutor: "retail" (oddiy mijoz) yoki "distributor". Distribyutorda
    # debt_limit sotuvda majburiy tekshiriladi, bitta hududda bitta faol
    # distribyutor bo'ladi.
    customer_type = Column(String(20), nullable=False, default="retail", server_default="retail", index=True)
    territory = Column(String(100), nullable=True)

    # Manzil va joylashuv (kuryer/agent uchun). location_source: map | telegram | manual
    region = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    address = Column(String(500), nullable=True)
    lat = Column(Numeric(10, 7), nullable=True)
    lng = Column(Numeric(10, 7), nullable=True)
    location_source = Column(String(20), nullable=True)

    extra_phones = Column(JSON, nullable=False, server_default='[]', default=list)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    work_days = Column(JSON, nullable=False, server_default='[]', default=list)  # 1=Du ... 7=Ya
    visit_radius_m = Column(Integer, nullable=True)
    photo_url = Column(String(300), nullable=True)

    # T0.26: tarixi (sotuv/buyurtma) bor mijoz jismonan o'chirilmaydi — arxivlanadi.
    # Arxivlanganda phone/card_number/tg_chat_id/agent_id NULL qilinadi (unique
    # cheklovlar bilan to'qnashmasligi uchun), eski qiymatlar deleted_meta'da qoladi.
    is_active = Column(Boolean, nullable=False, default=True, server_default=true())
    deleted_at = Column(DateTime, nullable=True)
    deleted_meta = Column(JSON, nullable=True)

    branch = relationship("Branch", back_populates="customers")
    orders = relationship("Order", back_populates="customer")

    __table_args__ = (
        UniqueConstraint('company_id', 'phone', name='uq_company_customer_phone'),
        UniqueConstraint('company_id', 'tg_chat_id', name='uq_company_customer_tg_chat_id'),
        UniqueConstraint('company_id', 'card_number', name='uq_company_customer_card_number'),
        CheckConstraint("price_type IN ('sale', 'wholesale', 'cost')", name='ck_customers_price_type'),
        CheckConstraint("cashback_percent >= 0 AND cashback_percent <= 100", name='ck_customers_cashback_0_100'),
        CheckConstraint("loyalty_points >= 0", name='ck_customers_loyalty_nonneg'),
        Index('ix_customers_company_active', 'company_id', 'is_active'),
    )

    @property
    def tier(self):
        # Sukut chegaralar (1000/5000/10000); korxona sozlamasidagi chegaralar API darajasida
        # loyalty_service.tier_for(points, rules) bilan hisoblanadi (T2.12).
        from app.services.loyalty_service import tier_for, DEFAULT_TIERS
        return tier_for(self.loyalty_points or 0, DEFAULT_TIERS)
