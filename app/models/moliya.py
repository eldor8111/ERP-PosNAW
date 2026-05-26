from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text, Boolean, JSON  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore

PAYMENT_TYPES = ["cash", "card", "uzcard", "humo", "click", "payme", "uzum", "keshbek"]

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False, default="cash")
    balance = Column(Numeric(14, 2), default=0)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    is_open = Column(Boolean, default=True)
    opening_balance = Column(Numeric(14, 2), default=0)
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
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
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    type = Column(String(20), nullable=False) # 'income', 'expense'
    amount = Column(Numeric(14, 2), nullable=False)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    payment_type = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    branch = relationship("Branch")
    wallet = relationship("Wallet")

class WalletBalance(Base):
    __tablename__ = "wallet_balances"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False)
    payment_type = Column(String(50), nullable=False)
    balance = Column(Numeric(14, 2), default=0)

    wallet = relationship("Wallet", backref="detailed_balances")


# ─── Kassa Sessiyasi ──────────────────────────────────────────────────────────

class KassaSession(Base):
    """Kassa ochilish/yopilish sessiyasi"""
    __tablename__ = "kassa_sessions"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime, nullable=True)
    opening_balance = Column(Numeric(14, 2), default=0)
    # Yopilish paytidagi har bir to'lov turi balansi {cash: X, card: Y, ...}
    closing_summary = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(20), default="open")  # open | closed

    wallet = relationship("Wallet", backref="sessions")


# ─── Kassa Harakatlari ────────────────────────────────────────────────────────

class KassaMovement(Base):
    """Kassadagi har bir kirim/chiqim harakati (to'lov turi bo'yicha)"""
    __tablename__ = "kassa_movements"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("kassa_sessions.id"), nullable=True)
    direction = Column(String(10), nullable=False)   # 'in' | 'out'
    payment_type = Column(String(30), nullable=False, default="cash")  # cash|card|uzcard|humo|click|payme|uzum|keshbek
    amount = Column(Numeric(14, 2), nullable=False)
    reference_type = Column(String(50), nullable=True)   # sale|supplier_payment|expense|invest|withdraw|customer_payment
    reference_id = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    wallet = relationship("Wallet", backref="movements")
    session = relationship("KassaSession", backref="movements")
