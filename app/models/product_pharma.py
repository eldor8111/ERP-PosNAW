"""Dori ma'lumotlari (D2.1): mahsulotning farmatsevtik bloki va ta'sir etuvchi moddalar ma'lumotnomasi.

Faqat dorixona moduli yoqilgan korxonada ishlatiladi; oddiy do'konda bu jadvallar bo'sh qoladi.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base

# Ruxsat etilgan qiymatlar (enum-string; bazada oddiy String sifatida saqlanadi)
DOSAGE_FORMS = (
    "tablet", "capsule", "syrup", "injection", "ointment",
    "drops", "powder", "solution", "suppository", "other",
)
STORAGE_TYPES = ("room", "cold_2_8", "frozen")
CONTROL_CLASSES = ("none", "potent", "psychotropic", "narcotic", "precursor")


class ProductPharma(Base):
    """Mahsulotga 1:1 bog'langan dori ma'lumotlari."""
    __tablename__ = "product_pharma"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)

    dosage_form = Column(String(20), nullable=True)  # tablet, capsule, syrup, ...
    strength = Column(String(100), nullable=True)  # masalan "500 mg"
    pack_qty = Column(Integer, nullable=True)  # qadoqdagi dona soni
    manufacturer = Column(String(200), nullable=True)
    country = Column(String(100), nullable=True)
    reg_number = Column(String(100), nullable=True)  # ro'yxatdan o'tish guvohnomasi raqami
    reg_valid_until = Column(Date, nullable=True)
    atc_code = Column(String(20), nullable=True)
    storage = Column(String(20), nullable=True)  # room, cold_2_8, frozen
    is_rx = Column(Boolean, nullable=False, default=False, server_default="false")  # retseptli
    control_class = Column(String(20), nullable=False, default="none", server_default="none")
    max_retail_price = Column(Numeric(16, 4), nullable=True)  # davlat belgilagan chegara narx

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    product = relationship("Product", foreign_keys=[product_id])


class PharmaSubstance(Base):
    """Ta'sir etuvchi modda. company_id NULL = umumiy (hamma dorixonaga ko'rinadi), aks holda korxonaniki."""
    __tablename__ = "pharma_substances"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    name_uz = Column(String(200), nullable=False)
    name_ru = Column(String(200), nullable=True)
    name_lat = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_pharma_substances_name_uz", "name_uz"),
        Index("ix_pharma_substances_name_ru", "name_ru"),
        Index("ix_pharma_substances_name_lat", "name_lat"),
    )


class ProductSubstance(Base):
    """Mahsulot va modda bog'lanishi (ko'pga-ko'p)."""
    __tablename__ = "product_substances"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    substance_id = Column(Integer, ForeignKey("pharma_substances.id"), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("product_id", "substance_id", name="uq_product_substances_pair"),
    )
