from datetime import datetime, timezone

from sqlalchemy import Column, Integer, ForeignKey, String, Text, DateTime

from app.database import Base


class SMSLog(Base):
    __tablename__ = "sms_logs"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    phone = Column(String(20))
    message = Column(Text, nullable=False)
    status = Column(String(20), default="sent")   # sent, failed
    eskiz_id = Column(String(50), nullable=True)
    sms_type = Column(String(30), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
