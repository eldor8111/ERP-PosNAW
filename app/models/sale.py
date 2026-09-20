import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Date, Enum, ForeignKey, Integer, Numeric, String, Text, Index, JSON  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class PaymentType(str, enum.Enum):
    cash = "cash"
    card = "card"
    uzcard = "uzcard"
    humo = "humo"
    bank = "bank"
    click = "click"
    payme = "payme"
    visa = "visa"
    uzum = "uzum"
    debt = "debt"
    mixed = "mixed"
    cashback = "cashback"  # Mijoz bonus_balance hisobidan to'lov


class SaleStatus(str, enum.Enum):
    completed = "completed"
    refunded = "refunded"
    partial_refund = "partial_refund"
    cancelled = "cancelled"
    pending = "pending"


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(20), unique=True, nullable=False, index=True)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_amount = Column(Numeric(20, 4), nullable=False)
    discount_amount = Column(Numeric(20, 4), default=0)
    paid_amount = Column(Numeric(20, 4), nullable=False)
    paid_cash = Column(Numeric(20, 4), default=0)
    paid_card = Column(Numeric(20, 4), default=0)
    paid_cashback = Column(Numeric(20, 4), default=0)
    cashback_earned = Column(Numeric(20, 4), default=0)
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
    # Sotuv qaysi kassir smenasida qilingani — aniq bog'lanish (vaqt-oyna
    # taxmini o'rniga). Eski sotuvlarda NULL, ular uchun vaqt-oyna zaxira.
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True, index=True)

    # Takroriy sotuvdan himoya: POS har sotuvni Idempotency-Key: <uuid>
    # headeri bilan yuboradi (oflayn navbatdan qayta yuborilganda ham
    # xuddi shu kalit) — takror kelsa mavjud sotuv qaytariladi.
    idempotency_key = Column(String(64), nullable=True, unique=True, index=True)

    # Fiskal chek ma'lumotlari (Hippo Communicator natijasi) — POS
    # fiskalizatsiyadan keyin PATCH /sales/{id}/fiscal orqali yuboradi.
    fiscal_sign = Column(String(64), nullable=True)
    fiscal_qr_url = Column(Text, nullable=True)
    fiscal_receipt_seq = Column(Integer, nullable=True)
    fiscal_transaction_id = Column(String(64), nullable=True)
    fiscal_at = Column(DateTime, nullable=True)
    debt_due_date = Column(Date, nullable=True)
    debt_amounts = Column(JSON, nullable=True, server_default='{}')
    before_debt_balances = Column(JSON, nullable=True)

    currency = relationship("Currency")
    warehouse = relationship("Warehouse")
    customer = relationship("Customer")
    cashier = relationship("User")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    payments = relationship("SalePayment", back_populates="sale", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_sale_company_created', 'company_id', 'created_at'),
        Index('ix_sale_company_status', 'company_id', 'status'),
    )


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)  # Qaysi ombordan sotildi
    unit = Column(String(20), nullable=True, default="dona")  # Mahsulot o'lchov birligi
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(16, 4), nullable=False)
    cost_price = Column(Numeric(16, 4), nullable=False)
    discount = Column(Numeric(16, 4), default=0)
    subtotal = Column(Numeric(20, 4), nullable=False)
    returned_quantity = Column(Numeric(12, 3), nullable=True, default=0)
    currency_code = Column(String(10), default="UZS")
    exchange_rate = Column(Numeric(14, 2), default=1)
    # Har bir sotilgan birlik uchun skanerlangan Data Matrix (markirovka) kodlari
    marking_codes = Column(JSON, nullable=True)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id])
    batches = relationship("SaleItemBatch", back_populates="sale_item", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_sale_item_sale_id', 'sale_id'),
        Index('ix_sale_item_product_id', 'product_id'),
    )


class SaleItemBatch(Base):
    __tablename__ = "sale_item_batches"

    id = Column(Integer, primary_key=True, index=True)
    sale_item_id = Column(Integer, ForeignKey("sale_items.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(14, 2), nullable=False)

    sale_item = relationship("SaleItem", back_populates="batches")
    batch = relationship("Batch")


class SalePayment(Base):
    __tablename__ = "sale_payments"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    payment_type = Column(String(50), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)

    sale = relationship("Sale", back_populates="payments")
