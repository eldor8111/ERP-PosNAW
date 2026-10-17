from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database import Base


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(String(50), primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    tool_name = Column(String(100), nullable=False, index=True)
    tool_arguments = Column(JSON, nullable=False)
    description = Column(Text, nullable=True)

    # Status: pending, executed, cancelled, expired
    status = Column(String(20), nullable=False, default="pending", index=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    executed_at = Column(DateTime, nullable=True)
    result_summary = Column(Text, nullable=True)

    company = relationship("Company")
    user = relationship("User")
