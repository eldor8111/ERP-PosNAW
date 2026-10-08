from datetime import datetime, timezone
import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Enum, JSON
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

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company")
    agent = relationship("User")


class MarketplaceTransactionType(str, enum.Enum):
    income = "income"
    payout = "payout"
    commission = "commission"
    refund = "refund"


class MarketplaceAgentTransaction(Base):
    __tablename__ = "marketplace_agent_transactions"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    
    order_id = Column(Integer, nullable=True) # ID of the order from mir-maza.uz
    transaction_type = Column(Enum(MarketplaceTransactionType), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    
    note = Column(String, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    agent = relationship("User")
    company = relationship("Company")
