import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.orm import relationship

from app.database import Base


class CountStatus(str, enum.Enum):
    draft = "draft"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    # Bitta omborda bir vaqtda faqat bitta ochiq (draft/in_progress) revizya bo'lishi mumkin
    __table_args__ = (
        Index(
            "uq_inventory_counts_one_open_per_wh", "warehouse_id", unique=True,
            postgresql_where=text("status IN ('draft','in_progress')"),
            sqlite_where=text("status IN ('draft','in_progress')"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(40), unique=True, nullable=False, index=True)
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
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    system_qty = Column(Numeric(12, 3), default=0)
    counted_qty = Column(Numeric(12, 3), nullable=True)
    variance = Column(Numeric(12, 3), nullable=True)
    counted_at = Column(DateTime, nullable=True)  # sanalgan vaqt (system_qty shu paytdagi qoldiq)

    variance_reason = Column(Text, nullable=True)

    count = relationship("InventoryCount", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")
