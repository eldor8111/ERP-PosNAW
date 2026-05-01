from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text, Boolean  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False) # e.g. "Asosiy Naqd", "Terminal"
    type = Column(String(20), nullable=False, default="cash") # 'cash', 'card', 'bank'
    balance = Column(Numeric(14, 2), default=0)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company")
    branch = relationship("Branch")

class ExpenseCategory(Base):
    __tablename__ = "expense_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    description = Column(String(200), nullable=True)

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    description = Column(Text, nullable=True)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    branch = relationship("Branch")
    category = relationship("ExpenseCategory")
    wallet = relationship("Wallet")
    approver = relationship("User")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    type = Column(String(20), nullable=False) # 'income', 'expense'
    amount = Column(Numeric(14, 2), nullable=False)
    reference_type = Column(String(50), nullable=True) # e.g. 'sale', 'expense', 'supplier_payment'
    reference_id = Column(Integer, nullable=True) # ID of the sale, expense, etc
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    payment_type = Column(String(50), nullable=True) # 'cash', 'card', 'click', 'humo'
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    branch = relationship("Branch")
    wallet = relationship("Wallet")

class WalletBalance(Base):
    __tablename__ = "wallet_balances"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False)
    payment_type = Column(String(50), nullable=False) # 'cash', 'card', 'click', etc.
    balance = Column(Numeric(14, 2), default=0)

    wallet = relationship("Wallet", backref="detailed_balances")
