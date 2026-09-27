from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class BOM(Base):
    """Retseptura (Bill of Materials) — bitta tayyor mahsulot uchun qancha va
    qaysi xom ashyo kerakligini belgilaydi. Bir mahsulot uchun bir nechta BOM
    versiyasi bo'lishi mumkin, lekin bittasi is_active=True bo'ladi."""
    __tablename__ = "boms"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    name = Column(String(150), nullable=False)
    is_active = Column(Boolean, default=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", foreign_keys=[product_id])
    variant = relationship("ProductVariant", foreign_keys=[variant_id])
    items = relationship("BOMItem", back_populates="bom", cascade="all, delete-orphan")


class BOMItem(Base):
    """BOM tarkibidagi bitta xom ashyo qatori."""
    __tablename__ = "bom_items"

    id = Column(Integer, primary_key=True, index=True)
    bom_id = Column(Integer, ForeignKey("boms.id"), nullable=False, index=True)
    component_product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    component_variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    # 1 dona (yoki 1 birlik) tayyor mahsulot uchun kerak bo'ladigan xom ashyo miqdori
    quantity_per_unit = Column(Numeric(14, 4), nullable=False)

    bom = relationship("BOM", back_populates="items")
    component_product = relationship("Product", foreign_keys=[component_product_id])
    component_variant = relationship("ProductVariant", foreign_keys=[component_variant_id])
