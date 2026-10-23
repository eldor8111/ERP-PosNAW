"""Retsept ma'lumotlari (D2.5): retseptli / nazoratdagi dori sotuvi uchun.

Faqat dorixona moduli yoqilgan korxonada yoziladi; oddiy do'konda jadval bo'sh qoladi.
Bitta qator ikki xil bo'lishi mumkin:
  - retsept qatori: number, issued_at, doctor, clinic, blank_type to'ldirilgan;
  - retseptsiz sotuv sababi (rx_mode="warn"): faqat reason_without_rx to'ldirilgan (qolgan maydonlar NULL).
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base

BLANK_TYPES = ("simple", "form_107", "form_148", "special")


class SalePrescription(Base):
    __tablename__ = "sale_prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_item_id = Column(Integer, ForeignKey("sale_items.id", ondelete="SET NULL"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)

    number = Column(String(100), nullable=True)
    issued_at = Column(Date, nullable=True)
    doctor = Column(String(200), nullable=True)
    clinic = Column(String(200), nullable=True)
    patient = Column(String(200), nullable=True)
    blank_type = Column(String(20), nullable=True)  # simple, form_107, form_148, special
    reason_without_rx = Column(String(500), nullable=True)  # retseptsiz sotilgan bo'lsa — sabab

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sale = relationship("Sale", foreign_keys=[sale_id])
    sale_item = relationship("SaleItem", foreign_keys=[sale_item_id])

    __table_args__ = (
        Index("ix_sale_prescriptions_sale_item_id", "sale_item_id"),
    )
