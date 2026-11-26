"""Restoran rejimi (R0.3): oshxona sexlari, zallar va stollar.

Faqat `companies.business_type = 'restaurant'` korxonada yoziladi; oddiy do'konda jadvallar bo'sh qoladi.
Hamma jadvalda `company_id` bor (korxona izolyatsiyasi va company_purge uchun).
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class KitchenStation(Base):
    """Oshxona sexi (Issiq sex, Sovuq sex, Bar): buyurtma qatorlari sex bo'yicha printer/KDS ga yo'naltiriladi."""
    __tablename__ = "kitchen_stations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # pos-desktop orqali chop etish: printer nomi yoki LAN manzili (ip:port); bo'sh = chop etilmaydi
    printer = Column(String(200), nullable=True)
    kds_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=_now)


class Hall(Base):
    """Zal (Asosiy zal, VIP, Terrasa). service_pct NULL = korxona sozlamasidagi xizmat haqi."""
    __tablename__ = "halls"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    service_pct = Column(Numeric(5, 2), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=_now)

    tables = relationship("RestaurantTable", back_populates="hall", cascade="all, delete-orphan")


class RestaurantTable(Base):
    """Zaldagi stol. x/y/w/h — zal sxemasidagi joyi (shartli birlik), shape: 'rect' | 'round'."""
    __tablename__ = "restaurant_tables"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    hall_id = Column(Integer, ForeignKey("halls.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(50), nullable=False)
    seats = Column(Integer, nullable=False, default=4, server_default="4")
    x = Column(Integer, nullable=False, default=0, server_default="0")
    y = Column(Integer, nullable=False, default=0, server_default="0")
    w = Column(Integer, nullable=False, default=2, server_default="2")
    h = Column(Integer, nullable=False, default=2, server_default="2")
    shape = Column(String(10), nullable=False, default="rect", server_default="rect")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=_now)

    hall = relationship("Hall", back_populates="tables")
