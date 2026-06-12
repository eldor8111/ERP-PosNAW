import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Index, Integer, Numeric, SmallInteger, String, Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class VatRateType(str, enum.Enum):
    standard = "standard"   # 12% QQS
    zero     = "zero"       # 0% QQS
    exempt   = "exempt"     # QQS imtiyozi (lgota)


class MxikReference(Base):
    """tasnif.soliq.uz dan kelgan MXIK ma'lumotlari keshi."""
    __tablename__ = "mxik_references"

    id         = Column(Integer, primary_key=True, index=True)
    mxik_code  = Column(String(20), nullable=False, unique=True, index=True)
    mxik_name  = Column(String(500), nullable=True)
    short_name = Column(String(500), nullable=True)

    group_code         = Column(String(10),  nullable=True)
    group_name         = Column(String(255), nullable=True)
    class_code         = Column(String(10),  nullable=True)
    class_name         = Column(String(255), nullable=True)
    position_code      = Column(String(20),  nullable=True)
    position_name      = Column(String(255), nullable=True)
    sub_position_code  = Column(String(20),  nullable=True)
    sub_position_name  = Column(String(255), nullable=True)

    brand_code       = Column(String(20),  nullable=True)
    brand_name       = Column(String(100), nullable=True)
    attribute_name   = Column(String(255), nullable=True)
    international_code = Column(String(50), nullable=True)  # barcode

    label    = Column(SmallInteger, default=0)  # 1 = aksiz belgisi
    use_card = Column(SmallInteger, default=0)  # 1 = karta bilan to'lash majburiy

    # QQS / Lgota — API 1 javobidan
    lgota_id   = Column(Integer, nullable=True)
    lgota_name = Column(Text,    nullable=True)
    vat_rate_type = Column(
        Enum(VatRateType),
        default=VatRateType.standard,
        nullable=False,
    )

    last_synced_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    packages = relationship(
        "MxikPackage",
        back_populates="mxik_reference",
        cascade="all, delete-orphan",
    )


class MxikPackage(Base):
    """Bir MXIK ga tegishli o'lchov/qadoq birliklari (dona, blok, pallet...)."""
    __tablename__ = "mxik_packages"

    id                = Column(Integer, primary_key=True, index=True)
    mxik_reference_id = Column(Integer, ForeignKey("mxik_references.id"), nullable=False, index=True)

    code           = Column(Integer,      nullable=False, index=True)
    parent_code    = Column(Integer,      nullable=True)
    container_code = Column(Integer,      nullable=True)
    container_name = Column(String(100),  nullable=True)
    unit_id        = Column(Integer,      nullable=True)
    unit_name      = Column(String(50),   nullable=True)
    parent_value   = Column(Numeric(12, 4), nullable=True)
    name           = Column(String(500),  nullable=True)
    type           = Column(SmallInteger, nullable=True)  # 1=dona, 2=blok, 3=pallet
    is_unit_package = Column(SmallInteger, nullable=True)  # 1=asosiy birlik

    mxik_reference = relationship("MxikReference", back_populates="packages")

    __table_args__ = (
        Index("ix_mxik_package_ref_code", "mxik_reference_id", "code"),
    )
