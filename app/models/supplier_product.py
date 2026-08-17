from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    
    supplier_code = Column(String(100), nullable=True) # Yetkazib beruvchining o'zidagi kodi
    purchase_price = Column(Numeric(16, 4), nullable=True) # Kelishilgan narx
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    supplier = relationship("Supplier")
    product = relationship("Product", back_populates="supplier_products")
