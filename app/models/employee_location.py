from datetime import datetime, timezone

from sqlalchemy import Column, Integer, DateTime, ForeignKey, Numeric, Index

from app.database import Base


class EmployeeLocation(Base):
    """Dala xodimining GPS nuqtasi — faqat ochiq ish smenasida yoziladi,
    90 kundan keyin avtomatik o'chiriladi (scheduler)."""
    __tablename__ = "employee_locations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    lat = Column(Numeric(10, 7), nullable=False)
    lng = Column(Numeric(10, 7), nullable=False)
    accuracy = Column(Integer, nullable=True)
    speed = Column(Numeric(6, 2), nullable=True)      # m/s
    battery = Column(Integer, nullable=True)           # %
    recorded_at = Column(DateTime, nullable=False)     # telefondagi vaqt
    received_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_employee_locations_user_time", "user_id", "recorded_at"),
        Index("ix_employee_locations_company_time", "company_id", "recorded_at"),
    )
