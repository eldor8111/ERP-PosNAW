from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime  # type: ignore
from app.database import Base  # type: ignore

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False) # Description of key usage (e.g., '1C Integration')
    key_hash = Column(String(200), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
