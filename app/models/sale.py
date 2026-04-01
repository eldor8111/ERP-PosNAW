import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Date, Enum, ForeignKey, Integer, Numeric, String, Text  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class PaymentType(str, enum.Enum):
    cash   = "cash"
    card   = "card"
    uzcard = "uzcard"
    humo   = "humo"
    bank   = "bank"
    click  = "click"
    payme  = "payme"
    visa   = "visa"
    uzum   = "uzum"
    debt   = "debt"
    mixed  = "mixed"


class SaleStatus(str, enum.Enum):
    completed = "completed"
    refunded = "refunded"
    partial_refund = "partial_refund"
    cancelled = "cancelled"


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(20), unique=True, nullable=False, index=True)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_amount = Column(Numeric(14, 2), nullable=False)
    discount_amount = Column(Numeric(14, 2), default=0)
    paid_amount = Column(Numeric(14, 2), nullable=False)
    paid_cash = Column(Numeric(14, 2), default=0)
    paid_card = Column(Numeric(14, 2), default=0)
    payment_type = Column(Enum(PaymentType), nullable=False)
    status = Column(Enum(SaleStatus), default=SaleStatus.completed)
    note = Column(Text, nullable=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    exchange_rate = Column(Numeric(14, 2), nullable=True, default=1)
    loyalty_points_earned = Column(Integer, default=0)
    loyalty_points_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    debt_due_date = Column(Date, nullable=True)

    currency = relationship("Currency")
    warehouse = relationship("Warehouse")
    customer = relationship("Customer")

    cashier = relationship("User")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    cost_price = Column(Numeric(12, 2), nullable=False)
    discount = Column(Numeric(12, 2), default=0)
    subtotal = Column(Numeric(14, 2), nullable=False)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")
    batches = relationship("SaleItemBatch", back_populates="sale_item", cascade="all, delete-orphan")


class SaleItemBatch(Base):
    __tablename__ = "sale_item_batches"

    id = Column(Integer, primary_key=True, index=True)
    sale_item_id = Column(Integer, ForeignKey("sale_items.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(14, 2), nullable=False)

    sale_item = relationship("SaleItem", back_populates="batches")
    batch = relationship("Batch")
