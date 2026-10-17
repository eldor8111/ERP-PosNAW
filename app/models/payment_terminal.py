from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, func  # type: ignore

from app.database import Base  # type: ignore

# Qo'llab-quvvatlanadigan provayderlar (CheckConstraint va router validatsiyasi uchun)
TERMINAL_PROVIDERS = ("payme", "click", "uzum", "uzcard", "humo")


class PaymentTerminal(Base):
    """T3.18: filial to'lov terminali / merchant (Payme, Click, Uzum, Uzcard, Humo).

    Faqat ichki yozuv: sirli kalitlar (secret) SAQLANMAYDI. Sotuvda to'lov shu terminal va tranzaksiya
    raqami (`SalePayment.reference`) bilan bog'lanadi, so'ng provayder ko'chirmasi bilan solishtiriladi.
    `branch_id` NULL — butun korxona terminali."""
    __tablename__ = "payment_terminals"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True)
    provider = Column(String(20), nullable=False)
    label = Column(String(100), nullable=True)
    merchant_id = Column(String(64), nullable=True)
    terminal_id = Column(String(64), nullable=True)
    require_reference = Column(Boolean, nullable=False, default=True, server_default="true")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now())

    __table_args__ = (
        CheckConstraint("provider IN ('payme','click','uzum','uzcard','humo')", name="ck_payment_terminals_provider"),
        Index("ix_payment_terminals_company_branch_provider", "company_id", "branch_id", "provider"),
    )
