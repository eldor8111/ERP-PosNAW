from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey  # type: ignore
from app.database import Base  # type: ignore

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False) # Description of key usage (e.g., '1C Integration')
    key_hash = Column(String(200), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # T0.22: kalit korxonaga bog'langan. NULL = egasiz eski kalit (nofaol; hech qachon "hamma uchun" emas)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    key_prefix = Column(String(12), nullable=True)   # tokenning dastlabki belgilari (UI uchun, hash o'rniga)
    last_used_at = Column(DateTime, nullable=True)
