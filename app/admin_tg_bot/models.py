# app/company_bot/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class CompanyBot(Base):
    __tablename__ = "company_bots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, unique=True)
    bot_token = Column(String(100), nullable=False, unique=True)
    bot_username = Column(String(100), nullable=True)
    bot_type = Column(String(20), nullable=False, default="company")  # 'admin' or 'company'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company")