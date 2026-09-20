from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, JSON
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    org_code = Column(String(10), unique=True, nullable=True, index=True)
    region = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    address = Column(String(250), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(100), nullable=True)
    tg_bot_token = Column(String(100), nullable=True)
    tg_bot_username = Column(String(100), nullable=True)
    # Dostavchik (kuryer) boti — mijoz/admin botlaridan alohida
    courier_bot_token = Column(String(100), nullable=True)
    courier_bot_username = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    balance = Column(Numeric(18, 2), default=0, nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    receipt_templates = Column(JSON, default=lambda: {"r58": {}, "r80": {}, "nak": {}})
    daily_report_time = Column(String(10), default="17:30")  # Kunlik hisobot yuborilish vaqti
    
    # ── Bildirishnomalar (Push Notifications) ──
    low_stock_alert = Column(Boolean, default=True)
    expiration_alert = Column(Boolean, default=True)
    debt_deadline_alert = Column(Boolean, default=True)
    daily_report_enabled = Column(Boolean, default=True)
    daily_report_recipients = Column(String(50), default="owners_and_admins")

    # ── Mijoz do'koni (Telegram Mini App) sozlamalari ──
    # True (standart) — mavjud xatti-harakat: qoldig'i 0/manfiy bo'lgan
    # mahsulotlar ham ko'rsatiladi va ularga buyurtma berish mumkin
    # (do'kon xodimi keyin tasdiqlash/rad etish orqali hal qiladi).
    shop_allow_out_of_stock_orders = Column(Boolean, default=True)

    # Yetkazib berish haqi (Mini App buyurtmalarida 'delivery' tanlansa
    # buyurtma summasiga qo'shiladi). 0 = bepul yetkazish.
    delivery_fee = Column(Numeric(14, 2), default=0)

    # ── POS sozlamalari ──
    # True (standart) — mavjud xatti-harakat: qoldiq yetarli bo'lmasa ham
    # sotish mumkin (qoldiq minusga tushadi). False — sotuvda minus
    # qoldiq bloklanadi.
    pos_allow_negative_stock = Column(Boolean, default=True)

    # bot = relationship("CompanyBot", back_populates="company", uselist=False)
    # ── Billing ──────────────────────────────────────────────
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=True)
    subscription_starts_at = Column(DateTime, nullable=True)  # obuna boshlanish vaqti
    subscription_ends_at = Column(DateTime, nullable=True)  # obuna tugash vaqti
    purchased_at = Column(DateTime, nullable=True)  # to'lov qilingan vaqt
    is_trial = Column(Boolean, default=False)  # sinov muddatimi?

    branches = relationship("Branch", back_populates="company")
    agent = relationship("Agent")
    tariff = relationship("Tariff", foreign_keys=[tariff_id])
    # Multi-korxona bog'lanish
    user_companies = relationship("UserCompany", back_populates="company", lazy="dynamic")
