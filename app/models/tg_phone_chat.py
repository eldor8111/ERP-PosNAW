from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime  # type: ignore
from app.database import Base  # type: ignore


class TgPhoneChat(Base):
    """
    Telegram bot orqali ulangan telefon raqam ↔ chat_id bog'liq.
    Ro'yxatdan o'tмаган foydalanuvchi uchun ham saqlanadi.
    """
    __tablename__ = "tg_phone_chats"

    id = Column(Integer, primary_key=True)
    phone = Column(String(30), nullable=False, index=True, unique=True)
    chat_id = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
