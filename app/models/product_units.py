"""Quti, blister va dona bitta kartochkada (D2.4): mahsulotning sotuv/kirim birliklari.

Qoldiq doim mahsulotning ASOSIY birligida (eng kichik sotiladigan, masalan dona) saqlanadi.
`ProductUnit.ratio` — shu birlikda asosiy birlikdan nechta borligi (quti = 30, blister = 10, dona = 1).
Faqat dorixona moduli yoqilgan korxonada ishlatiladi; oddiy do'konda bu jadvallar bo'sh qoladi.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ProductUnit(Base):
    """Mahsulotning bitta sotuv/kirim birligi (quti, blister, dona, ampula, ...)."""
    __tablename__ = "product_units"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)

    name = Column(String(50), nullable=False)                  # "quti", "blister", "dona"
    ratio = Column(Numeric(14, 3), nullable=False)             # asosiy birlikda nechta
    sale_price = Column(Numeric(16, 4), nullable=True)         # shu birlikdagi sotuv narxi (NULL = hisoblanadi)
    barcode = Column(String(100), nullable=True)               # birlik shtrix-kodi (korxona ichida noyob)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", foreign_keys=[product_id])

    __table_args__ = (
        UniqueConstraint("company_id", "barcode", name="uq_product_units_company_barcode"),
        UniqueConstraint("product_id", "name", name="uq_product_units_product_name"),
        Index("ix_product_units_company_barcode", "company_id", "barcode"),
    )


class SaleItemUnit(Base):
    """Sotuv qatori qaysi birlikda sotilgani (birlik nomi va nisbati o'sha paytdagi holatda saqlanadi).

    `SaleItem.quantity` doim asosiy birlikda (qaytarish va hisobotlar o'zgarishsiz ishlashi uchun);
    bu yerda — kassir ko'rgan miqdor (`unit_qty` quti) va narx (`unit_price` — bir quti narxi).
    """
    __tablename__ = "sale_item_units"

    id = Column(Integer, primary_key=True, index=True)
    sale_item_id = Column(Integer, ForeignKey("sale_items.id", ondelete="CASCADE"), nullable=False, unique=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("product_units.id", ondelete="SET NULL"), nullable=True)

    unit_name = Column(String(50), nullable=False)
    unit_ratio = Column(Numeric(14, 3), nullable=False)
    unit_qty = Column(Numeric(14, 3), nullable=False)
    unit_price = Column(Numeric(16, 4), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sale_item = relationship("SaleItem", foreign_keys=[sale_item_id])
