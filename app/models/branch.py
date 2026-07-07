from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore

class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    address = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="branches")
    warehouses = relationship("Warehouse", back_populates="branch")
    users = relationship("User", back_populates="branch")
