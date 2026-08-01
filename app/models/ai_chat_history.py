"""
AI Chat Tarix Modeli
Foydalanuvchilarning AI Copilot bilan yozishmalarini saqlab turadi.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from app.database import Base


class AiChatHistory(Base):
    __tablename__ = "ai_chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(10), nullable=False)    # "user" yoki "assistant"
    message = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)   # "debt_payment", "add_debt", "query" ...
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_chat_history_user_company", "user_id", "company_id"),
        Index("ix_chat_history_created", "created_at"),
    )
