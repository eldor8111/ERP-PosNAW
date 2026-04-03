"""
PlatformSettings — Super Admin tomonidan boshqariladigan global sozlamalar.
Karta raqami, ega ismi, Telegram username, telefon.
"""
from sqlalchemy import Column, Integer, String
from app.database import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id         = Column(Integer, primary_key=True, index=True)
    key        = Column(String(100), unique=True, nullable=False, index=True)
    value      = Column(String(500), nullable=True)
    label      = Column(String(200), nullable=True)   # Admin UI uchun nom
