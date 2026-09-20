from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Courier(Base):
    """Dostavchik (kuryer) — CRM foydalanuvchisi emas, faqat kuryer boti /
    Mini App orqali ishlaydi. Telefon raqami orqali botda ro'yxatdan o'tadi
    (contact share) va tg_chat_id bog'lanadi."""

    __tablename__ = "couriers"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(32), nullable=False)
    tg_chat_id = Column(String(32), nullable=True, index=True)
    transport = Column(String(30), nullable=True)  # piyoda, velosiped, moto, avto
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company")
