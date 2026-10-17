import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, Index, Integer, String, ForeignKey, text  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class WarehouseType(str, enum.Enum):
    main = "main"
    transit = "transit"
    returns = "returns"
    shop = "shop"
    raw_material = "raw_material"  # Xom ashyo ombori (ishlab chiqarish moduli)
    wip = "wip"  # Jarayondagi (Work-In-Progress) ombor


class Warehouse(Base):
    __tablename__ = "warehouses"
    # T1.4: filialda bittadan ortiq "asosiy savdo ombori" (is_default) bo'lishi mumkin emas
    __table_args__ = (
        # T1.13: korxona/filial bo'yicha omborlar ro'yxati indeksi
        Index("ix_warehouses_company_branch", "company_id", "branch_id"),
        Index(
            "uq_warehouses_branch_default", "branch_id", unique=True,
            postgresql_where=text("is_default AND branch_id IS NOT NULL"),
            sqlite_where=text("is_default AND branch_id IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(Enum(WarehouseType), default=WarehouseType.main)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    # T1.4: filialning asosiy savdo ombori (filialda eng ko'pi bilan bitta)
    is_default = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    branch = relationship("Branch", back_populates="warehouses")
    stock_levels = relationship("StockLevel", back_populates="warehouse", cascade="all, delete-orphan")
