from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Boolean, Date
from sqlalchemy.orm import relationship

from app.database import Base


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    discount_type = Column(String(20), nullable=False, default="percent") # percent, amount
    discount_value = Column(Numeric(12, 2), nullable=False)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    products = relationship("PromotionProduct", back_populates="promotion", cascade="all, delete-orphan")


class PromotionProduct(Base):
    __tablename__ = "promotion_products"

    id = Column(Integer, primary_key=True, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    promotion = relationship("Promotion", back_populates="products")
    product = relationship("Product")
