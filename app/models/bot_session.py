from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text  # type: ignore
from app.database import Base  # type: ignore


class BotSession(Base):
    """Telegram bot ko'p bosqichli ro'yxatdan o'tish holati."""
    __tablename__ = "bot_sessions"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(50), nullable=False, index=True)
    token = Column(String(300), nullable=False)
    # step: "awaiting_name" | "awaiting_phone"
    step = Column(String(50), nullable=False, default="awaiting_name")
    temp_name = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
