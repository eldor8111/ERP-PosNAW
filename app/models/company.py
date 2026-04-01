from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    org_code = Column(String(10), unique=True, nullable=True, index=True)
    region = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    address = Column(String(250), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(100), nullable=True)
    tg_bot_token = Column(String(100), nullable=True)
    tg_bot_username = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    balance = Column(Numeric(18, 2), default=0, nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    branches = relationship("Branch", back_populates="company")
    agent = relationship("Agent")
