"""
Billing modellari: Tariff, BalanceLog
Company modeliga qo'shimcha ustunlar migration orqali qo'shiladi.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text, Float, JSON
from sqlalchemy.orm import relationship
from app.database import Base  # type: ignore


class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # "Boshlang'ich", "Pro", "Enterprise"
    description = Column(Text, nullable=True)
    price_per_month = Column(Numeric(12, 2), default=0)  # oylik narx (so'm)
    duration_days = Column(Integer, default=30)  # obuna muddati (kun)
    max_users = Column(Integer, default=5)
    max_branches = Column(Integer, default=1)
    max_warehouses = Column(Integer, default=1)
    max_products = Column(Integer, nullable=True)  # tovar/shtrixkod limiti (masalan 700 ta)
    max_agents = Column(Integer, default=0)  # savdo agentlari limiti
    max_couriers = Column(Integer, default=0)  # dastavchiklar limiti
    max_monthly_orders = Column(Integer, nullable=True)  # oylik buyurtmalar kvotasi
    max_production_orders = Column(Integer, nullable=True)  # oylik ishlab chiqarish kvotasi
    min_duration_months = Column(Integer, default=1)  # kamida necha oylik sotiladi (1 yoki 3)
    has_pnl_compare = Column(Boolean, default=False)  # 2 davrli P&L solishtirish huquqi
    has_manufacturing = Column(Boolean, default=False)  # ishlab chiqarish moduli
    has_distribution = Column(Boolean, default=False)  # distribyutsiya moduli
    period_discounts = Column(JSON, nullable=True)  # muddat bo'yicha chegirmalar: {"3": 0, "6": 10, "12": 20}
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    bhm_percent = Column(Float, nullable=True)  # BHM ning necha foizini tashkil qiladi
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class BalanceLog(Base):
    """Balans o'zgarishlari tarixi (audit log)"""
    __tablename__ = "balance_logs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)  # + kirim, - chiqim
    log_type = Column(String(30), nullable=False)  # top_up | subscription | trial | refund
    note = Column(String(255), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", foreign_keys=[company_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class FeaturePackage(Base):
    """
    Qo'shimcha pullik paketlar katalogi (Ishlab chiqarish, Distribyutorlar va logistika, Yetkazib berish avtomatikasi).
    BHM foizi orqali narx avtomatik hisoblanadi.
    """
    __tablename__ = "feature_packages"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)  # manufacturing, distribution, delivery_automation
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    bhm_percent = Column(Float, nullable=True)  # Masalan 25.0
    price_per_month = Column(Numeric(12, 2), default=0)  # Agar bhm_percent bo'lmasa qat'iy narx
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class CompanyPackage(Base):
    """
    Kompaniyaning sotib olingan / berilgan pullik paketlari (modullari).
    Muddat tugasa modul yopiladi, lekin ma'lumotlar saqlanadi.
    """
    __tablename__ = "company_packages"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    package_code = Column(String(50), nullable=False, index=True)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    is_trial = Column(Boolean, default=False)
    purchased_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", foreign_keys=[company_id])

