from sqlalchemy import Column, DateTime, String

from app.database import Base


class BackgroundLease(Base):
    """Fon jarayon "rahbar"i uchun ijara (lease) — T3.15.

    Ko'p gunicorn worker'da scheduler va admin bot polling faqat bitta jarayonda ishlashi uchun:
    ijarani muddati (expires_at) o'tgan yoki o'zining holder'i bo'lsa olinadi/yangilanadi.
    Oddiy jadval orqali ishlaydi (advisory lock emas), PgBouncer/pooler da ham to'g'ri ishlaydi.
    Kunlik vazifalarning idempotentligi alohida: `scheduler_runs` (SchedulerRun, T2.10).
    """
    __tablename__ = "background_leases"

    name = Column(String(60), primary_key=True)
    holder = Column(String(120), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
