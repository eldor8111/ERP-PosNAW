import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Index, text
from sqlalchemy.orm import relationship

from app.database import Base


class ProductStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    archived = "archived"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), nullable=False, index=True)
    barcode = Column(String(50), nullable=False, index=True)
    product_code = Column(String(100), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    name_ru = Column(String(200), nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    unit = Column(String(20), default="dona")
    cost_price = Column(Numeric(12, 2), nullable=False, default=0)
    wholesale_price = Column(Numeric(12, 2), nullable=True, default=None)
    sale_price = Column(Numeric(12, 2), nullable=False, default=0)
    min_stock = Column(Integer, default=0)
    max_stock = Column(Integer, nullable=True)
    # TZ: Ombor joylashuvi (bin location)
    bin_location = Column(String(100), nullable=True)
    # TZ: Rasmlar (product image URL — primary)
    image_url = Column(Text, nullable=True)
    # TZ: Rasmlar — multiple images (JSON array of URLs)
    images = Column(Text, nullable=True)
    brand = Column(String(200), nullable=True)
    # Qo'shimcha shtrix kodlar — JSON array of barcode strings
    extra_barcodes = Column(Text, nullable=True)
    # Qo'shimcha maxsus kodlar — JSON array of product_code strings
    extra_product_codes = Column(Text, nullable=True)
    # TZ: Vazn va o'lchamlar
    weight = Column(Numeric(10, 3), nullable=True)       # kg
    dimensions = Column(String(100), nullable=True)      # MxBxH sm
    status = Column(Enum(ProductStatus), default=ProductStatus.active)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    category = relationship("Category", back_populates="products")
    stock_level = relationship("StockLevel", back_populates="product", uselist=False)
    stock_movements = relationship("StockMovement", back_populates="product")
    sale_items = relationship("SaleItem", back_populates="product")

    __table_args__ = (
        Index('ix_product_company_status_deleted', 'company_id', 'status', 'is_deleted'),
        Index('ix_product_company_name', 'company_id', 'name'),
        # Partial unique: faqat o'chirilmagan mahsulotlarda SKU va barcode unique
        Index('uq_products_sku_active', 'sku', unique=True,
              postgresql_where=text('is_deleted = false')),
        Index('uq_products_barcode_active', 'barcode', unique=True,
              postgresql_where=text('is_deleted = false')),
    )
