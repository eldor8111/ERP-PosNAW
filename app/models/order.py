from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Enum as SQLEnum, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class OrderStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    delivered = "delivered"
    cancelled = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(16, 4), nullable=False)
    total_amount = Column(Numeric(20, 4), nullable=False)
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.pending)
    payment_type = Column(String(20), nullable=True)  # cash, card, debt, etc
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="orders")
    branch = relationship("Branch", back_populates="orders")
    product = relationship("Product")
