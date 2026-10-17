from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func  # type: ignore

from app.database import Base  # type: ignore


class FiscalDevice(Base):
    """T3.18: Hippo fiskal modul (`factory_id`) ning filial/kassaga serverdagi biriktirilishi.

    Avval `factory_id` faqat brauzer localStorage'ida turardi va server uni hech narsaga bog'lamasdi.
    `branch_id` NULL — korxonaning hamma filialida ishlatiladi; to'ldirilgan bo'lsa — faqat shu filialda.
    Korxonada kamida bitta faol qurilma bo'lsa, `PATCH /sales/{id}/fiscal` faqat ro'yxatdagi qurilmani qabul qiladi."""
    __tablename__ = "fiscal_devices"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True)
    factory_id = Column(String(64), nullable=False)
    label = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "factory_id", name="uq_fiscal_devices_company_factory"),
        Index("ix_fiscal_devices_company_branch", "company_id", "branch_id"),
    )
