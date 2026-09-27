import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.database import Base


class SaleDeliveryStatus(str, enum.Enum):
    pending = "pending"      # Yetkazish kutilmoqda (marshrutga qo'shilmagan)
    assigned = "assigned"    # Kuryerga biriktirildi
    on_way = "on_way"
    delivered = "delivered"
    cancelled = "cancelled"


class SaleDelivery(Base):
    """Ulgurji sotuvni mijozga yetkazib berish. Telegram-do'kon buyurtmasi
    (Order) dan farqli — sotuv allaqachon mavjud, shuning uchun
    "yetkazildi" yangi sotuv yaratmaydi. Logistikada to'xtov kaliti:
    "sale-{sale_id}"."""
    __tablename__ = "sale_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    address = Column(String(500), nullable=True)
    lat = Column(Numeric(10, 7), nullable=True)
    lng = Column(Numeric(10, 7), nullable=True)
    contact_phone = Column(String(32), nullable=True)
    delivery_fee = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    planned_date = Column(Date, nullable=True)
    note = Column(Text, nullable=True)
    status = Column(SQLEnum(SaleDeliveryStatus, native_enum=False, length=20),
                    default=SaleDeliveryStatus.pending, nullable=False, index=True)
    courier_id = Column(Integer, ForeignKey("couriers.id"), nullable=True, index=True)
    assigned_at = Column(DateTime, nullable=True)
    on_way_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String(300), nullable=True)
    # Yetkazish haqi moliyaga bir marta yozilishi uchun (idempotentlik)
    fee_recorded = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    sale = relationship("Sale")
    courier = relationship("Courier")
