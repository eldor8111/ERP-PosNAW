import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Index, text, \
    SmallInteger
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.mxik import VatRateType


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
    cost_currency = Column(String(3), nullable=False, server_default="UZS", default='UZS')
    wholesale_price = Column(Numeric(12, 2), nullable=True, default=None)
    wholesale_currency = Column(String(3), nullable=False, server_default="UZS", default='UZS')
    sale_price = Column(Numeric(12, 2), nullable=False, default=0)
    sale_currency = Column(String(3), nullable=False, server_default="UZS", default='UZS')
    min_stock = Column(Integer, default=0)
    max_stock = Column(Integer, nullable=True)
    bin_location = Column(String(100), nullable=True)
    image_url = Column(Text, nullable=True)
    images = Column(Text, nullable=True)
    brand = Column(String(200), nullable=True)
    extra_barcodes = Column(Text, nullable=True)
    extra_product_codes = Column(Text, nullable=True)
    weight = Column(Numeric(10, 3), nullable=True)
    dimensions = Column(String(100), nullable=True)
    status = Column(Enum(ProductStatus), default=ProductStatus.active)
    product_type = Column(String(10), nullable=False, default="stock")
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    category = relationship("Category", back_populates="products")
    stock_level = relationship("StockLevel", back_populates="product", uselist=False)
    stock_movements = relationship("StockMovement", back_populates="product")
    sale_items = relationship("SaleItem", back_populates="product")
    customer_prices = relationship("CustomerPrice", back_populates="product", cascade="all, delete-orphan")

    # MXIK / Fiskal
    mxik_code = Column(String(20), nullable=True, index=True)
    mxik_reference_id = Column(Integer, ForeignKey("mxik_references.id"), nullable=True, index=True)
    package_code = Column(Integer, nullable=True)  # operator tanlagan paket kodi
    parent_code = Column(Integer, nullable=True)
    unit_id = Column(Integer, nullable=True)

    # QQS — mxik_reference dan ko'chirib saqlanadi (tez kirish uchun)
    vat_rate_type = Column(Enum(VatRateType), nullable=True)
    vat_lgota_id = Column(Integer, nullable=True)
    vat_lgota_name = Column(Text, nullable=True)
    vat_checked_at = Column(DateTime, nullable=True)

    mxik_reference = relationship("MxikReference", foreign_keys=[mxik_reference_id])

    # Bu mahsulot sell bo'lsa, uning konversiyasi (1 ta)
    conversion = relationship(
        "ProductConversion",
        foreign_keys="ProductConversion.sell_product_id",
        back_populates="sell_product",
        uselist=False,
    )
    # Bu mahsulot stock bo'lsa, unga bog'langan tarkibiy qismlar (ko'p)
    sell_conversions = relationship(
        "ProductConversion",
        foreign_keys="ProductConversion.source_product_id",
        back_populates="source_product",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index('ix_product_company_status_deleted', 'company_id', 'status', 'is_deleted'),
        Index('ix_product_company_name', 'company_id', 'name'),
        Index('uq_products_sku_active', 'company_id', 'sku', unique=True,
              postgresql_where=text('is_deleted = false')),
        Index('uq_products_barcode_active', 'company_id', 'barcode', unique=True,
              postgresql_where=text('is_deleted = false')),
    )


class ProductConversion(Base):
    """
    Virtual Products: sell mahsulot (masalan Dumba) -> stock mahsulot (masalan Butun qo'y) konversiyasi.
    ratio = sotilgan 1 birlik uchun asosiy mahsulotdan qancha yechilishi kerak.
    Masalan: 1 kg Dumba sotilsa -> 1.0 kg Butun qo'ydan yechiladi (ratio=1.0)
    """
    __tablename__ = "product_conversions"

    id = Column(Integer, primary_key=True, index=True)
    sell_product_id = Column(Integer, ForeignKey("products.id"), nullable=False, unique=True, index=True)
    source_product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    ratio = Column(Numeric(10, 4), nullable=False, default=1.0)

    sell_product = relationship("Product", foreign_keys=[sell_product_id], back_populates="conversion")
    source_product = relationship("Product", foreign_keys=[source_product_id], back_populates="sell_conversions")
