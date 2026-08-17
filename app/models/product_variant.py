from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    name = Column(String(100), nullable=True) # e.g. "XL Red"
    sku = Column(String(50), nullable=True, index=True)
    barcode = Column(String(50), nullable=True, index=True)
    
    cost_price = Column(Numeric(16, 4), nullable=True)
    sale_price = Column(Numeric(16, 4), nullable=True)
    wholesale_price = Column(Numeric(16, 4), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="variants")
    attribute_values = relationship("VariantAttributeValue", back_populates="variant", cascade="all, delete-orphan")
