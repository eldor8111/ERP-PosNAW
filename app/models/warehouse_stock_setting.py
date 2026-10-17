"""T4.4: ombor bo'yicha min/max qoldiq sozlamasi.

Har bir (ombor, mahsulot) juftligi uchun alohida chegara. Qator yo'q (yoki qiymat NULL) bo'lsa —
mahsulot darajasidagi `Product.min_stock` / `Product.max_stock` ishlatiladi (`effective_min()` /
`effective_max()`, app/utils/stock_utils.py).
"""
from datetime import datetime, timezone

from sqlalchemy import (  # type: ignore
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, UniqueConstraint,
)

from app.database import Base  # type: ignore


class WarehouseStockSetting(Base):
    __tablename__ = "warehouse_stock_settings"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "product_id", name="uq_wss_warehouse_product"),
        CheckConstraint("min_qty IS NULL OR min_qty >= 0", name="ck_wss_min_nonneg"),
        CheckConstraint("max_qty IS NULL OR max_qty >= 0", name="ck_wss_max_nonneg"),
        CheckConstraint("reorder_qty IS NULL OR reorder_qty >= 0", name="ck_wss_reorder_nonneg"),
        CheckConstraint("min_qty IS NULL OR max_qty IS NULL OR max_qty >= min_qty", name="ck_wss_max_ge_min"),
        CheckConstraint("source_warehouse_id IS NULL OR source_warehouse_id <> warehouse_id",
                        name="ck_wss_source_not_self"),
        Index("ix_wss_product", "product_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    min_qty = Column(Numeric(12, 3), nullable=True)
    max_qty = Column(Numeric(12, 3), nullable=True)
    reorder_qty = Column(Numeric(12, 3), nullable=True)
    # To'ldirish manbai (odatda markaziy ombor)
    source_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
