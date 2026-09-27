import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, Text, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class DeliveryRouteStatus(str, enum.Enum):
    planned = "planned"          # Tuzildi, buyurtmalar kuryerga biriktirildi
    in_progress = "in_progress"  # Kuryer yo'lga chiqdi (buyurtmalar on_way)
    completed = "completed"
    cancelled = "cancelled"


class DeliveryRoute(Base):
    """Bir kuryerning bir kunlik ko'p to'xtovli marshruti."""
    __tablename__ = "delivery_routes"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(20), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    route_date = Column(Date, nullable=False, index=True)
    courier_id = Column(Integer, ForeignKey("couriers.id"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    status = Column(SQLEnum(DeliveryRouteStatus, native_enum=False, length=20),
                    default=DeliveryRouteStatus.planned, nullable=False)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    courier = relationship("Courier")
    vehicle = relationship("Vehicle")
    stops = relationship("DeliveryRouteStop", back_populates="route",
                         order_by="DeliveryRouteStop.sequence", cascade="all, delete-orphan")


class DeliveryRouteStop(Base):
    """Marshrutdagi to'xtov = bitta buyurtma guruhi. Holati alohida
    saqlanmaydi — Order.status dan olinadi (kuryer boti ham o'zgartiradi)."""
    __tablename__ = "delivery_route_stops"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("delivery_routes.id", ondelete="CASCADE"), nullable=False, index=True)
    # orders.py dagi _group_key bilan bir xil: order_group_id yoki "single-{id}"
    group_key = Column(String(50), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)

    route = relationship("DeliveryRoute", back_populates="stops")

    __table_args__ = (
        UniqueConstraint("route_id", "group_key", name="uq_route_stop_group"),
    )
