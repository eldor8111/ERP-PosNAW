from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, func

from app.database import Base


class LabelTemplate(Base):
    """T3.7: yorliq (shtrix-kod) shabloni — serverda, korxona va ixtiyoriy filial bo'yicha.

    `branch_id` NULL — korxonaning hamma filialida ko'rinadi; to'ldirilgan bo'lsa — faqat shu filialda.
    `kind`: `product` (mahsulot yorlig'i) | `customer` (mijoz kartasi yorlig'i)."""
    __tablename__ = "label_templates"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(20), nullable=False, default="product", server_default="product")
    name = Column(String(100), nullable=False)
    config = Column(JSON, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_label_templates_company_kind", "company_id", "kind"),
        # Oddiy UniqueConstraint NULL branch_id ni takrorlashga yo'l qo'yadi — shu sabab COALESCE
        Index("uq_label_templates_scope", company_id, kind, name, func.coalesce(branch_id, 0), unique=True),
    )
