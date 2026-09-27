from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey

from app.database import Base


class CustomerDocument(Base):
    """Mijoz hujjatlari (shartnoma, litsenziya, pasport). Fayl ochiq /static
    ga emas, uploads_private/ ga saqlanadi va faqat avtorizatsiyali
    endpoint orqali beriladi."""
    __tablename__ = "customer_documents"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    file_path = Column(String(300), nullable=False)  # uploads_private/ ichidagi nisbiy yo'l
    original_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=True)
    size = Column(Integer, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
