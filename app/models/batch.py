from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    lot_number = Column(String(100), nullable=True) # made nullable for auto-generated batches
    manufacture_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    initial_quantity = Column(Numeric(12, 3), default=0) # For tracking total purchase volume
    quantity = Column(Numeric(12, 3), default=0) # Remaining quantity
    purchase_price = Column(Numeric(14, 2), default=0) # Exact unit cost of this batch
    
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    product = relationship("Product")
    warehouse = relationship("Warehouse")
    purchase_order = relationship("PurchaseOrder")
