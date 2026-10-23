"""Markirovka (Data Matrix) kodlari (D3.2): dorixona rejimida kirimdan sotuvgacha kuzatiladi.

Faqat dorixona moduli yoqilgan korxonada yoziladi; oddiy do'konda jadval bo'sh qoladi.
Holatlar: in_stock (omborda) -> sold (sotildi) -> in_stock (qaytarildi); written_off — hisobdan chiqarilgan.
`code` — GS1 asosiy kodi: `01<GTIN>21<seriya>` (kripto dum 91/92 saqlanmaydi), tahlil bo'lmasa — toza matn.
"""
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base

MARKING_STATUSES = ("in_stock", "sold", "returned", "written_off")


class MarkingCode(Base):
    __tablename__ = "marking_codes"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(300), nullable=False)
    gtin = Column(String(14), nullable=True)
    serial = Column(String(100), nullable=True)
    lot_number = Column(String(100), nullable=True)
    expiry_date = Column(Date, nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id", ondelete="SET NULL"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    status = Column(String(20), nullable=False, default="in_stock", server_default="in_stock")
    sale_item_id = Column(Integer, ForeignKey("sale_items.id", ondelete="SET NULL"), nullable=True, index=True)
    received_po_id = Column(Integer, ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    product = relationship("Product", foreign_keys=[product_id])
    batch = relationship("Batch", foreign_keys=[batch_id])

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_marking_codes_company_code"),
        Index("ix_marking_codes_company_status", "company_id", "status"),
    )
