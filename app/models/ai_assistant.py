"""E-code AI yordamchi: suhbatlar, xabarlar va yuklangan fayllar (Claude API).

Xabarlar API ga yuborilgan bloklar bilan AYNAN saqlanadi (append-only): thinking bloklari va
vosita chaqiruvlari keyingi so'rovda o'zgarishsiz qaytariladi. Tarix tahrirlanmaydi, faqat oxiriga
qo'shiladi.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base  # type: ignore


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AiConversation(Base):
    __tablename__ = "ai_conversations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    model = Column(String(60), nullable=False)
    # Suhbat boshlanganda muzlatilgan kontekst (korxona, xodim, rol, ruxsatlar) va tizim/vositalar xeshi:
    # suhbat davomida tizim ko'rsatmasi va vositalar ro'yxati o'zgarmasligi kerak (kesh va thinking uchun)
    context = Column(JSON, nullable=True)
    tools_hash = Column(String(64), nullable=True)
    turns = Column(Integer, nullable=False, default=0)
    busy_until = Column(DateTime, nullable=True)        # bir vaqtda bitta so'rov (qulf muddati, UTC)
    pending_note = Column(Text, nullable=True)          # tasdiq/bekor natijasi: keyingi xabarga qo'shiladi
    has_files = Column(Boolean, nullable=False, default=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    messages = relationship("AiMessage", back_populates="conversation", order_by="AiMessage.id",
                            cascade="all, delete-orphan", passive_deletes=True)


class AiMessage(Base):
    __tablename__ = "ai_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    role = Column(String(16), nullable=False)           # user | assistant
    kind = Column(String(16), nullable=False)           # prompt | tool_result | response
    content = Column(JSON, nullable=False)              # API ga yuborilgan / qaytgan bloklar (aynan)
    text = Column(Text, nullable=True)                  # ko'rsatish uchun matn
    actions = Column(JSON, nullable=True)               # tasdiq kartalari (ko'rsatish uchun)
    model = Column(String(60), nullable=True)
    stop_reason = Column(String(30), nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(12, 6), nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)

    conversation = relationship("AiConversation", back_populates="messages")


class AiFile(Base):
    __tablename__ = "ai_files"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String(100), nullable=False, unique=True, index=True)   # Files API identifikatori
    company_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    conversation_id = Column(Integer, nullable=True, index=True)
    filename = Column(String(200), nullable=True)
    media_type = Column(String(50), nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
