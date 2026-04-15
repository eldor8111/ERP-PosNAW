from datetime import datetime, timezone
import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, ForeignKey  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class UserRole(str, enum.Enum):
    super_admin = "super_admin"
    admin = "admin"
    director = "director"
    manager = "manager"
    accountant = "accountant"
    warehouse = "warehouse"
    cashier = "cashier"

class UserStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    blocked = "blocked"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    hashed_password = Column(String(200), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.cashier)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    status = Column(Enum(UserStatus), default=UserStatus.active)
    tg_chat_id = Column(String(50), nullable=True)  # Telegram OTP uchun
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    branch = relationship("Branch", back_populates="users")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # Multi-korxona bog'lanish (company_id backward compat. uchun saqlanadi)
    user_companies = relationship("UserCompany", back_populates="user", lazy="dynamic")
