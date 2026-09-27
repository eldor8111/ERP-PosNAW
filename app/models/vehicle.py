from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, UniqueConstraint

from app.database import Base


class Vehicle(Base):
    """Transport reestri. Kuryerdan mustaqil — bitta mashinani turli
    haydovchilar ishlatishi mumkin (Courier.vehicle_id — standart mashina)."""
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    plate_number = Column(String(20), nullable=False)
    model = Column(String(100), nullable=True)
    capacity_kg = Column(Numeric(10, 2), nullable=True)
    fuel_type = Column(String(20), nullable=True)  # petrol, diesel, gas, electric
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("company_id", "plate_number", name="uq_company_vehicle_plate"),
    )
