"""Sodiqlik dasturi sozlamalari (T2.12): korxona va filial bo'yicha.

Sozlama qatori bo'lmasa `loyalty_service.get_loyalty_rules` bugungi qattiq qiymatlarni qaytaradi
(1% ball, 1 ball = 1 so'm, daraja 1000/5000/10000, to'liq sarflash, limit faqat distribyutorga).
"""
from datetime import datetime, timezone

from sqlalchemy import (  # type: ignore
    Column, Integer, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, true,
)

from app.database import Base  # type: ignore


class LoyaltySettings(Base):
    __tablename__ = "loyalty_settings"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, unique=True)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default=true())
    # Sotuv summasining necha foizi ball sifatida yig'iladi
    points_percent = Column(Numeric(5, 2), nullable=False, default=1, server_default="1.00")
    # 1 ball necha so'm (sarflashda)
    point_value = Column(Numeric(14, 2), nullable=False, default=1, server_default="1")
    # Yangi mijozga sukut keshbek foizi
    default_cashback_percent = Column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    # Chekning ko'pi bilan necha foizini keshbek/ball bilan to'lash mumkin
    max_redeem_percent = Column(Numeric(5, 2), nullable=False, default=100, server_default="100")
    # False bo'lsa keshbek/ball faqat to'langan qismga hisoblanadi (nasiya qismiga yo'q)
    accrue_on_unpaid = Column(Boolean, nullable=False, default=True, server_default=true())
    # POS "Vazvrat" mijozning keshbek/ball/total_spent ini ham qaytaradi
    return_reverses_loyalty = Column(Boolean, nullable=False, default=True, server_default=true())
    tier_bronze = Column(Integer, nullable=False, default=1000, server_default="1000")
    tier_silver = Column(Integer, nullable=False, default=5000, server_default="5000")
    tier_gold = Column(Integer, nullable=False, default=10000, server_default="10000")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint(
            "points_percent BETWEEN 0 AND 100 AND default_cashback_percent BETWEEN 0 AND 100 "
            "AND max_redeem_percent BETWEEN 0 AND 100",
            name="ck_loyalty_settings_percents",
        ),
        CheckConstraint("point_value > 0", name="ck_loyalty_settings_point_value"),
        CheckConstraint("tier_bronze < tier_silver AND tier_silver < tier_gold", name="ck_loyalty_settings_tiers"),
    )


class LoyaltyBranchRule(Base):
    __tablename__ = "loyalty_branch_rules"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    # False — filial sodiqlik dasturidan chiqarilgan (yig'ish ham, sarflash ham yo'q)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default=true())
    # Berilsa — shu filialdagi sotuvlarda mijozning shaxsiy foizi o'rniga ishlatiladi
    cashback_percent_override = Column(Numeric(5, 2), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("company_id", "branch_id", name="uq_loyalty_branch_rule"),
        CheckConstraint(
            "cashback_percent_override IS NULL OR cashback_percent_override BETWEEN 0 AND 100",
            name="ck_loyalty_branch_rules_cashback",
        ),
    )
