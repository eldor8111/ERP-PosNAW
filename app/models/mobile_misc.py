from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, JSON, UniqueConstraint

from app.database import Base


class MobileIdempotency(Base):
    """Oflayn navbatdan kelgan yozuv so'rovlari (Idempotency-Key): tarmoq
    uzilib qayta yuborilsa, amal qayta bajarilmaydi — saqlangan javob qaytadi."""
    __tablename__ = "mobile_idempotency"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(64), nullable=False)
    endpoint = Column(String(100), nullable=False)
    response = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_mobile_idem_user_key"),)


class DeliveryProof(Base):
    """Yetkazish isboti: rasm (shaxsiy papkada) va kuryer turgan nuqta."""
    __tablename__ = "delivery_proofs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    stop_key = Column(String(50), nullable=False, index=True)   # "sale-12" | order_group_id | "single-5"
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    photo_path = Column(String(300), nullable=True)
    lat = Column(Numeric(10, 7), nullable=True)
    lng = Column(Numeric(10, 7), nullable=True)
    distance_m = Column(Integer, nullable=True)                 # manzildan qancha uzoqda
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
