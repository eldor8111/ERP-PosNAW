from datetime import datetime, timezone

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Numeric

from app.database import Base


class FieldShift(Base):
    """Dala xodimining ish smenasi ("Ishni boshlash" → "Tugatish").
    GPS kuzatuv faqat ochiq smena davomida olib boriladi."""
    __tablename__ = "field_shifts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ended_at = Column(DateTime, nullable=True)
    start_lat = Column(Numeric(10, 7), nullable=True)
    start_lng = Column(Numeric(10, 7), nullable=True)
    end_lat = Column(Numeric(10, 7), nullable=True)
    end_lng = Column(Numeric(10, 7), nullable=True)
