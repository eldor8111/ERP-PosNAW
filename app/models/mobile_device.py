from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint

from app.database import Base


class MobileDevice(Base):
    """Mobil ilovaga kirgan qurilma. Mobil tokenlar (dev claim) shu yozuvga
    bog'lanadi — revoked_at o'rnatilsa (telefon yo'qolgan, xodim ketgan)
    access ham, refresh ham darhol ishlamay qoladi."""
    __tablename__ = "mobile_devices"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    device_id = Column(String(100), nullable=False)
    platform = Column(String(20), nullable=True)      # android | ios | web
    model = Column(String(100), nullable=True)
    app_version = Column(String(20), nullable=True)
    fcm_token = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "device_id", name="uq_mobile_device_user_device"),
    )
