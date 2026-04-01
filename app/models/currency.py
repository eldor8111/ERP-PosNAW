from sqlalchemy import Column, Integer, String, Boolean, Numeric, ForeignKey  # type: ignore
from app.database import Base  # type: ignore

class Currency(Base):
    __tablename__ = "currencies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)   # e.g. "US Dollar"
    code = Column(String(10), nullable=False)  # e.g. "USD"
    rate = Column(Numeric(14, 2), nullable=False, default=1)
    is_default = Column(Boolean, default=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    is_active = Column(Boolean, default=True)   # ko'p valyuta bir vaqtda faol bo'lishi mumkin
