import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class CountStatus(str, enum.Enum):
    draft = "draft"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class InventoryCount(Base):
    __tablename__ = "inventory_counts"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(30), unique=True, nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    status = Column(Enum(CountStatus), default=CountStatus.draft)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    warehouse = relationship("Warehouse")
    items = relationship("InventoryCountItem", back_populates="count", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])


class InventoryCountItem(Base):
    __tablename__ = "inventory_count_items"

    id = Column(Integer, primary_key=True, index=True)
    count_id = Column(Integer, ForeignKey("inventory_counts.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    system_qty = Column(Numeric(12, 3), default=0)
    counted_qty = Column(Numeric(12, 3), nullable=True)
    variance = Column(Numeric(12, 3), nullable=True)

    variance_reason = Column(Text, nullable=True)

    count = relationship("InventoryCount", back_populates="items")
    product = relationship("Product")
