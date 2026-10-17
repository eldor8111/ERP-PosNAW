from sqlalchemy import Column, ForeignKey, Integer, String

from app.database import Base


class DocumentCounter(Base):
    """Hujjat raqamlari hisoblagichi (T1.14): korxona + filial + hujjat turi + kun kesimida.

    branch_id = 0 — filialsiz. Qator tranzaksiya ichida `INSERT .. ON CONFLICT DO UPDATE`
    bilan atomar oshiriladi (qarang: app/services/document_numbers.py).
    """
    __tablename__ = "document_counters"

    company_id = Column(Integer, ForeignKey("companies.id"), primary_key=True, nullable=False)
    branch_id = Column(Integer, primary_key=True, nullable=False, default=0, server_default="0")
    doc_type = Column(String(8), primary_key=True, nullable=False)
    period = Column(String(8), primary_key=True, nullable=False)  # YYYYMMDD
    last_value = Column(Integer, nullable=False, default=0, server_default="0")
