"""
user_companies — ko'p-korxona bog'lanish jadvali.
Bir foydalanuvchi bir nechta korxonada ishlashi mumkin.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum,
    ForeignKey, Integer, UniqueConstraint,
)
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore
from app.models.user import UserRole  # type: ignore


class UserCompany(Base):
    __tablename__ = "user_companies"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    role       = Column(Enum(UserRole), default=UserRole.cashier, nullable=False)
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user    = relationship("User",    back_populates="user_companies")
    company = relationship("Company", back_populates="user_companies")

    __table_args__ = (
        UniqueConstraint("user_id", "company_id", name="uq_user_company"),
    )
