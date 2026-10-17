from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import relationship

from app.database import Base


class BinLocation(Base):
    __tablename__ = "bin_locations"

    id = Column(Integer, primary_key=True, index=True)
    # T0.21: korxonaga bog'langan (migratsiyadan keyin NOT NULL qilinadi)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    # Ixtiyoriy: NULL = "barcha omborlar"
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    code = Column(String(50), nullable=False, index=True)
    label = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    warehouse = relationship("Warehouse", lazy="joined")

    @property
    def warehouse_name(self):
        return self.warehouse.name if self.warehouse else None

    # Kod unikalligi korxona (va ombor) ichida; warehouse_id NULL bo'lsa 0 deb olinadi
    __table_args__ = (
        Index("uq_bin_locations_company_wh_code", company_id, func.coalesce(warehouse_id, 0), code, unique=True),
    )
