from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, Numeric, String, Text, ForeignKey  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    inn = Column(String(20), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    payment_terms = Column(Integer, default=30)  # days
    debt_balance = Column(Numeric(14, 2), default=0)
    is_active = Column(Boolean, default=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Bank rekvizitlari
    bank_name = Column(String(200), nullable=True)
    bank_account = Column(String(30), nullable=True)
    bank_mfo = Column(String(10), nullable=True)

    # Shartnoma ma'lumotlari
    contract_number = Column(String(100), nullable=True)
    contract_date = Column(DateTime, nullable=True)

    # Reyting (1.0 – 5.0)
    rating = Column(Float, nullable=True, default=None)

    # Qo'shimcha ma'lumot
    notes = Column(Text, nullable=True)

    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")
