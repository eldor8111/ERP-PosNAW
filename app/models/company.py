from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, JSON, CheckConstraint
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

    # True bolsa: buyurtma "yetkazildi" bolganda avtomatik Sale yaratiladi
    # (ombor kamayadi, kassa/qarz yoziladi). Standart False - qolda POS.
    orders_auto_create_sale = Column(Boolean, default=False)

    # ── Ixtiyoriy modullar (oddiy do'konlarga ko'rinmasligi uchun) ──
    # manufacturing — Ishlab chiqarish (retseptura, buyurtma, tannarx)
    # distribution — Distribyutorlar, Logistika, sotuvdan yetkazib berish
    manufacturing_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    distribution_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    marketplace_agents_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    # T0.36: Mir-maza buyurtmalari tushadigan asosiy filial (mijozda filial bo'lmasa).
    # DB darajasida FK bor (migratsiya t0_36: fk_companies_mp_default_branch, ondelete SET NULL).
    # ORM'da ForeignKey() berilmagan: companies <-> branches o'rtasida ikkinchi FK yo'li
    # Branch.company / Company.branches relationship'larini noaniq (AmbiguousForeignKeys) qiladi;
    # Branch.company ga foreign_keys=[company_id] qo'shilgach ORM FK ham qo'yish mumkin.
    marketplace_default_branch_id = Column(Integer, nullable=True)
    # T3.13: Telegram Mini App / bot buyurtmalari va yangi bot mijozlari uchun standart filial.
    # ORM'da ForeignKey() yo'q (yuqoridagi sabab); DB da FK bor (migratsiya t3_13, ondelete SET NULL).
    shop_default_branch_id = Column(Integer, nullable=True)

    # ── POS sozlamalari ──
    # True (standart) — mavjud xatti-harakat: qoldiq yetarli bo'lmasa ham
    # sotish mumkin (qoldiq minusga tushadi). False — sotuvda minus
    # qoldiq bloklanadi.
    pos_allow_negative_stock = Column(Boolean, default=True)
    # T1.11: True bo'lsa ochiq smenasiz sotuv backendda ham rad etiladi (POST /sales, kutilayotgan sotuv).
    pos_require_shift = Column(Boolean, nullable=False, default=False, server_default="false")
    # T2.12: kredit limit kimga qo'llanadi: "distributor" (faqat distribyutor mijoz, sukut) yoki "all" (hamma mijoz)
    credit_limit_scope = Column(String(20), nullable=False, default="distributor", server_default="distributor")
    # T4.3: True bo'lsa server `promotion_id`siz sotuv qatoriga eng yaxshi mos aksiyani o'zi qo'llaydi (sukut o'chiq)
    promotions_auto_apply = Column(Boolean, nullable=False, default=False, server_default="false")
    # C4.1 (T4.2): QQS turi belgilanmagan (NULL) mahsulot fiskallanganda ishlatiladigan foiz; NULL -> 12%
    fiscal_default_vat = Column(Integer, nullable=True)

    # ── Mahsulot qoldig‘iga ta’sir qilish bosqichi ──
    # 'order_confirmed' (standart) — buyurtma/sotuv tasdiqlanganda
    # 'loaded' — tovarlar mashinaga yuklanganda (omborchi load-confirm)
    # 'delivered' — kuryer tovarlarni do'konga yetkazib topshirganda
    stock_deduct_stage = Column(String(30), nullable=False, default="order_confirmed", server_default="order_confirmed")

    # ── Agent va Kuryer geo-radius sozlamalari ──
    agent_order_geo_radius_check = Column(Boolean, nullable=False, default=True, server_default="true")
    default_delivery_radius_m = Column(Integer, nullable=False, default=250, server_default="250")

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

    __table_args__ = (
        CheckConstraint("credit_limit_scope IN ('distributor','all')", name="ck_companies_credit_limit_scope"),
    )
