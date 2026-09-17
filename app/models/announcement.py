from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from app.database import Base  # type: ignore


class Announcement(Base):
    """Super admin tomonidan korxonalarga yuboriladigan bildirish nomalar."""
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    # NULL = barcha korxonalarga, int = faqat shu korxonaga
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)  # Tugash vaqti (ixtiyoriy)
    has_survey = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SurveyQuestion(Base):
    __tablename__ = "survey_questions"
    id = Column(Integer, primary_key=True, index=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False)
    text = Column(String(500), nullable=False)
    question_type = Column(String(50), nullable=False) # 'text', 'single_choice', 'multiple_choice'
    options = Column(Text, nullable=True) # JSON list formatida saqlanadi
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class SurveyAnswer(Base):
    __tablename__ = "survey_answers"
    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("survey_questions.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    answer_data = Column(Text, nullable=False) # Foydalanuvchi javobi JSON formatida saqlanadi
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
