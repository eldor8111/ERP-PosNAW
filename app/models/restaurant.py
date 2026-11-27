"""Restoran rejimi (R0.3): oshxona sexlari, zallar va stollar.

Faqat `companies.business_type = 'restaurant'` korxonada yoziladi; oddiy do'konda jadvallar bo'sh qoladi.
Hamma jadvalda `company_id` bor (korxona izolyatsiyasi va company_purge uchun).
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class KitchenStation(Base):
    """Oshxona sexi (Issiq sex, Sovuq sex, Bar): buyurtma qatorlari sex bo'yicha printer/KDS ga yo'naltiriladi.

    Korxona darajasida: taom yoki kategoriya bitta sexga biriktiriladi va hamma filialda shu sexga ketadi.
    Filial bo'yicha printer manzili R4.1 da alohida jadvalda saqlanadi."""
    __tablename__ = "kitchen_stations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
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


class ModifierGroup(Base):
    """Taom qo'shimchalari guruhi (R1.3): "Pishirish darajasi" (1 ta majburiy), "Qo'shimchalar" (0..3).
    min_select > 0 bo'lsa guruh majburiy; max_select — eng ko'p tanlov."""
    __tablename__ = "modifier_groups"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    min_select = Column(Integer, nullable=False, default=0, server_default="0")
    max_select = Column(Integer, nullable=False, default=1, server_default="1")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=_now)

    modifiers = relationship("Modifier", back_populates="group", cascade="all, delete-orphan",
                             order_by="Modifier.sort_order, Modifier.id")


class Modifier(Base):
    """Guruhdagi variant: qo'shimcha narx va ixtiyoriy bog'langan mahsulot (ombordan quantity x taom soni yechiladi).
    Buyurtma qatorida nom va narx surati saqlanadi: o'zgartirish eski cheklarga ta'sir qilmaydi."""
    __tablename__ = "modifiers"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    price = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=False, default=0, server_default="0")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    group = relationship("ModifierGroup", back_populates="modifiers")


class ProductModifierGroup(Base):
    """Qaysi taomga qaysi qo'shimchalar guruhi biriktirilgan."""
    __tablename__ = "product_modifier_groups"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (UniqueConstraint("product_id", "group_id", name="uq_product_modifier_group"),)


class MenuStop(Base):
    """Stop-list (R1.5): filial bo'yicha taomni vaqtincha sotuvdan olish va "qoldi N porsiya" hisoblagichi.

    Taom sotilmaydi, agar: `stopped` va (`until` yo'q yoki hali kelmagan), yoki `remaining` 0 ga tushgan.
    `remaining` NULL = hisoblagich yo'q. Chekka qo'shilganda kamayadi, pishmagan qator bekor qilinsa qaytadi.
    Qator ham to'xtatilmagan, ham hisoblagichsiz bo'lsa o'chiriladi."""
    __tablename__ = "menu_stops"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    stopped = Column(Boolean, nullable=False, default=False, server_default="false")
    reason = Column(String(200), nullable=True)
    until = Column(DateTime, nullable=True)
    remaining = Column(Numeric(12, 3), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, default=_now)

    __table_args__ = (UniqueConstraint("branch_id", "product_id", name="uq_menu_stop_branch_product"),)


class RestaurantTerminal(Base):
    """Ofitsiant plansheti (R6.1): menejer bir marta ulaydi, keyin xodimlar shu qurilmada PIN bilan almashib kiradi.
    Token faqat xeshi bilan saqlanadi; PIN bilan berilgan sessiya tokeni `term` claim orqali shu qurilmaga bog'langan,
    qurilma bekor qilinsa (revoked_at) sessiyalar darhol yaroqsiz bo'ladi."""
    __tablename__ = "restaurant_terminals"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
