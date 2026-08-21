from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base

class AIAuditLog(Base):
    __tablename__ = "ai_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(50), nullable=True, index=True)
    conversation_id = Column(String(50), nullable=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    prompt = Column(Text, nullable=True)
    tool_name = Column(String(100), nullable=True, index=True)
    tool_arguments = Column(JSON, nullable=True)
    
    permission = Column(String(100), nullable=True)
    risk_level = Column(String(20), nullable=True) # LOW, MEDIUM, HIGH
    status = Column(String(20), nullable=False) # SUCCESS, ERROR, PENDING_CONFIRMATION, CANCELLED
    
    confirmation_required = Column(Boolean, default=False)
    confirmation_id = Column(String(50), nullable=True, index=True)
    
    result_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    
    execution_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    company = relationship("Company")
    user = relationship("User")
