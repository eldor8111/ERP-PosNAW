from datetime import datetime, timezone

from sqlalchemy import Column, Integer, ForeignKey, Numeric, UniqueConstraint, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class CustomerPrice(Base):
    __tablename__ = "customer_prices"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    customer = relationship("Customer", back_populates="custom_prices")
    product = relationship("Product", back_populates="customer_prices")

    __table_args__ = (
        UniqueConstraint("company_id", "customer_id", "product_id", name="uq_company_customer_product"),
    )