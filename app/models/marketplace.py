from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Enum, JSON, Index, text
from sqlalchemy.orm import relationship # type: ignore

from app.database import Base # type: ignore


class MarketplaceAgentCategory(Base):
    __tablename__ = "marketplace_agent_categories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, nullable=False, index=True)  # ID from mir-maza.uz
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    company = relationship("Company")


class MarketplaceProductStatus(str, enum.Enum):
    draft = "draft"
    review = "review"
    approved = "approved"
    rejected = "rejected"


class MarketplaceProduct(Base):
    __tablename__ = "marketplace_products"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    price = Column(Numeric(18, 2), nullable=False, default=0)
    qty = Column(Numeric(18, 2), nullable=False, default=0)
    category_id = Column(Integer, nullable=False, index=True)
    barcode = Column(String(100), nullable=True)
    sku = Column(String(100), nullable=True)
    images = Column(JSON, default=list)
    
    status = Column(Enum(MarketplaceProductStatus), default=MarketplaceProductStatus.draft, index=True)
    reject_reason = Column(String, nullable=True)
    purchase_order_id = Column(Integer, nullable=True)  # ERP dagi xarid/prixod hujjati (PurchaseOrder)
    # T3.17: tasdiqlashda kirim qilingan ombor va agent so'ragan (ixtiyoriy) topshirish ombori
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    preferred_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company")
    agent = relationship("User")
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id])


class MarketplaceTransactionType(str, enum.Enum):
    income = "income"
    payout = "payout"
    commission = "commission"
    refund = "refund"


class MarketplaceAgentTransaction(Base):
    __tablename__ = "marketplace_agent_transactions"
    # T0.18: bir buyurtma + bir mahsulot uchun faqat bitta income yozuvi (webhook/pull idempotentligi)
    __table_args__ = (
        Index(
            "uq_mp_tx_income_order_product", "order_id", "marketplace_product_id", unique=True,
            postgresql_where=text("transaction_type = 'income' AND marketplace_product_id IS NOT NULL"),
            sqlite_where=text("transaction_type = 'income' AND marketplace_product_id IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    order_id = Column(Integer, nullable=True) # ID of the order from mir-maza.uz
    # T0.18: daromad qaysi marketplace mahsuloti bo'yicha yozilgani (idempotentlik uchun)
    marketplace_product_id = Column(Integer, ForeignKey("marketplace_products.id", ondelete="SET NULL"), nullable=True, index=True)
    transaction_type = Column(Enum(MarketplaceTransactionType), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    
    note = Column(String, nullable=True)

    # T3.17: to'lov (payout) qaysi kassa, filial va moliya tranzaksiyasiga bog'langani
    # (eski to'lovlarda NULL — "kassaga bog'lanmagan")
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    finance_transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    agent = relationship("User")
    company = relationship("Company")


class MarketplaceAgentNotification(Base):
    __tablename__ = "marketplace_agent_notifications"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    title = Column(String(255), nullable=False)
    body = Column(String(1000), nullable=False)
    notif_type = Column(String(50), default="general") # order_sold, product_approved, product_rejected, payment_received
    data = Column(JSON, default=dict)
    is_read = Column(Boolean, default=False, index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    agent = relationship("User")
    company = relationship("Company")

