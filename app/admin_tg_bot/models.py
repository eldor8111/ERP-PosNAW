# app/admin_tg_bot/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class CompanyBot(Base):
    __tablename__ = "company_bots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    bot_token = Column(String(100), nullable=False, unique=True)
    bot_username = Column(String(100), nullable=True)
    bot_type = Column(String(20), nullable=False, default="company")  # 'admin' or 'company'
    
    # Settings for admin bot
    notify_instant_sales = Column(Boolean, default=True)
    notify_instant_finance = Column(Boolean, default=True)
    notify_scheduled = Column(Boolean, default=True)
    scheduled_time = Column(String(5), default="20:00")
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    company = relationship("Company")

    __table_args__ = (
        UniqueConstraint('company_id', 'bot_type', name='uq_company_bot_type'),
    )
