"""Restoran cheki (R3): buyurtma, qatorlar va oshxona tiketlari.

`restaurant_orders` mavjud `orders` (Telegram/agent buyurtmalari) bilan aralashtirilmaydi.
To'langan chek R5 da mavjud `Sale` sifatida yoziladi (`sale_id`), shunda kassa, fiskal va moliya qayta yozilmaydi.
"""
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric,
                        String, Text)
from sqlalchemy.orm import relationship

from app.database import Base


def _now():
    return datetime.now(timezone.utc)


ORDER_TYPES = ("dine_in", "takeaway", "delivery")
ORDER_STATUSES = ("open", "prechecked", "paid", "cancelled")
ITEM_STATUSES = ("draft", "sent", "cooking", "ready", "served", "cancelled")


class RestaurantOrder(Base):
    __tablename__ = "restaurant_orders"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    number = Column(String(40), nullable=False)
    daily_no = Column(Integer, nullable=False)          # ekranda ko'rinadigan qisqa raqam (filial, kun bo'yicha)
    order_type = Column(String(20), nullable=False, default="dine_in", server_default="dine_in")
    table_id = Column(Integer, ForeignKey("restaurant_tables.id", ondelete="SET NULL"), nullable=True, index=True)
    hall_id = Column(Integer, ForeignKey("halls.id", ondelete="SET NULL"), nullable=True)
    guests = Column(Integer, nullable=False, default=1, server_default="1")
    waiter_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="open", server_default="open")
    subtotal = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    discount_pct = Column(Numeric(5, 2), nullable=True)
    discount_amount = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    discount_reason = Column(String(200), nullable=True)
    service_pct = Column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    service_amount = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    total = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    comment = Column(String(500), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")   # optimistik qulf (13-bo'lim)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    opened_at = Column(DateTime, default=_now)
    prechecked_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String(300), nullable=True)
    merged_into_id = Column(Integer, ForeignKey("restaurant_orders.id", ondelete="SET NULL"), nullable=True)
    # R5.2: hisob bo'lingan bo'lsa — qaysi chekdan ajratilgan (har bir qism alohida to'lov va fiskal chek)
    split_from_id = Column(Integer, ForeignKey("restaurant_orders.id", ondelete="SET NULL"), nullable=True)
    # R5: to'lov. payments — [{type, amount, reference, terminal_id}] surati; tips — choy puli (tushumga kirmaydi)
    payments = Column(JSON, nullable=True)
    tips_amount = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    change_amount = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    paid_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # R5.4: qaytarishlar — jami qaytarilgan summa va har bir qaytarish yozuvi
    # [{sale_id, number, amount, payment_type, reason, at, by, approved_by, lines:[{item_id, quantity}]}]
    refunded_amount = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    refunds = Column(JSON, nullable=True)

    items = relationship("RestaurantOrderItem", back_populates="order", cascade="all, delete-orphan",
                         order_by="RestaurantOrderItem.id")

    __table_args__ = (
        CheckConstraint("order_type IN ('dine_in','takeaway','delivery')", name="ck_rest_orders_type"),
        CheckConstraint("status IN ('open','prechecked','paid','cancelled')", name="ck_rest_orders_status"),
        Index("ix_rest_orders_branch_status", "company_id", "branch_id", "status"),
    )


class RestaurantOrderItem(Base):
    __tablename__ = "restaurant_order_items"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("restaurant_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    bom_id = Column(Integer, ForeignKey("boms.id", ondelete="SET NULL"), nullable=True)   # sotuv paytidagi tex karta versiyasi
    name = Column(String(200), nullable=False)          # nom surati (keyin nom o'zgarsa ham chekda saqlanadi)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(16, 2), nullable=False)
    modifiers = Column(JSON, nullable=True)             # R1.3 da
    modifiers_total = Column(Numeric(16, 2), nullable=False, default=0, server_default="0")
    course = Column(Integer, nullable=False, default=1, server_default="1")
    guest_no = Column(Integer, nullable=True)
    station_id = Column(Integer, ForeignKey("kitchen_stations.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="draft", server_default="draft")
    comment = Column(String(300), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now)
    sent_at = Column(DateTime, nullable=True)
    cooking_at = Column(DateTime, nullable=True)
    ready_at = Column(DateTime, nullable=True)
    served_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String(300), nullable=True)
    cancelled_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancel_approved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Tayyorlangan taom bekor qilinsa ingredientlari chiqimga yoziladi (R7.3)
    write_off = Column(Boolean, nullable=False, default=False, server_default="false")
    # R7.1: ingredientlar ombordan yechildimi (to'lovda, 'sent' rejimida yuborishda yoki chiqimda)
    stock_deducted = Column(Boolean, nullable=False, default=False, server_default="false")
    # Yechilgan ingredientlar: [{product_id, quantity, warehouse_id}] — bekor qilinsa aynan shular qaytariladi
    stock_lines = Column(JSON, nullable=True)
    # R5.4: to'langan chekdan qaytarilgan miqdor
    refunded_qty = Column(Numeric(12, 3), nullable=False, default=0, server_default="0")

    order = relationship("RestaurantOrder", back_populates="items")

    __table_args__ = (
        CheckConstraint("status IN ('draft','sent','cooking','ready','served','cancelled')",
                        name="ck_rest_order_items_status"),
        CheckConstraint("quantity > 0", name="ck_rest_order_items_qty"),
    )


class KitchenTicket(Base):
    """Oshxonaga yuborilgan tiket: sex bo'yicha (R4.1 printer va R4.2 KDS shu jadvaldan oladi).
    kind: 'order' — yangi taomlar, 'cancel' — bekor qilingan taomlar."""
    __tablename__ = "kitchen_tickets"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("restaurant_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    station_id = Column(Integer, ForeignKey("kitchen_stations.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(10), nullable=False, default="order", server_default="order")
    lines = Column(JSON, nullable=False)                 # [{item_id, name, quantity, comment, course}]
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=_now)
    printed_at = Column(DateTime, nullable=True)
    print_attempts = Column(Integer, nullable=False, default=0, server_default="0")
