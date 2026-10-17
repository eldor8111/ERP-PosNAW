from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Enum as SQLEnum, JSON
from sqlalchemy import column, event, select, table
from sqlalchemy.orm import relationship

from app.database import Base


class OrderStatus(str, Enum):
    pending = "pending"          # Yangi — mijoz yubordi
    confirmed = "confirmed"      # Do'kon tasdiqladi
    preparing = "preparing"      # Tayyorlanmoqda (yig'ilmoqda)
    assigned = "assigned"        # Kuryerga biriktirildi
    on_way = "on_way"            # Yo'lda
    delivered = "delivered"      # Yetkazildi / olib ketildi
    cancelled = "cancelled"      # Bekor qilindi


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    # Bir checkout'da savatga solingan bir nechta mahsulot shu ID bilan
    # bog'lanadi — CRM/bot'da bitta buyurtma sifatida guruhlab ko'rsatish uchun.
    order_group_id = Column(String(36), nullable=True, index=True)
    # T0.36: buyurtma egasi korxona (avval faqat Customer orqali aniqlanardi).
    # Migratsiyada customers.company_id dan to'ldirilgan, NOT NULL.
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    # T3.13: buyurtma bajariladigan aniq ombor (olib ketish filialining shop ombori). NULL — eski buyurtmalar:
    # sotuvga aylantirishda filialning savdo ombori tanlanadi.
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(16, 4), nullable=False)
    total_amount = Column(Numeric(20, 4), nullable=False)
    # DB ustuni oddiy VARCHAR (migration'da sa.String(50) sifatida yaratilgan) —
    # native_enum=False bo'lmasa SQLAlchemy PostgreSQL'da mavjud bo'lmagan
    # "orderstatus" native enum type'ga CAST qilishga urinib xato beradi.
    status = Column(SQLEnum(OrderStatus, native_enum=False, length=20), default=OrderStatus.pending)
    payment_type = Column(String(20), nullable=True)  # cash, card, debt, etc
    notes = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True)

    # ── Yetkazib berish ──────────────────────────────────────────────────
    # delivery_type: 'pickup' (olib ketish) yoki 'delivery' (yetkazish).
    # Guruhdagi barcha qatorlarda bir xil qiymat saqlanadi (denormalizatsiya,
    # order_group_id bo'yicha guruhlash bilan mos). delivery_fee ham har
    # qatorga bir xil yoziladi — jamlashda guruh uchun BIR marta olinadi.
    delivery_type = Column(String(20), nullable=True, default="pickup")
    delivery_address = Column(String(500), nullable=True)
    delivery_lat = Column(Numeric(10, 7), nullable=True)
    delivery_lng = Column(Numeric(10, 7), nullable=True)
    contact_phone = Column(String(32), nullable=True)
    delivery_fee = Column(Numeric(14, 2), nullable=True, default=0)
    courier_id = Column(Integer, ForeignKey("couriers.id"), nullable=True, index=True)
    assigned_at = Column(DateTime, nullable=True)
    on_way_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String(300), nullable=True)
    # Yetkazilganda avtomatik yaratilgan Sale (sozlama yoqilgan bolsa) -
    # ham boglanish, ham takror yaratmaslik uchun idempotent belgi.
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=True)

    customer = relationship("Customer", back_populates="orders")
    branch = relationship("Branch", back_populates="orders")
    product = relationship("Product")
    courier = relationship("Courier")


# T0.36: company_id NOT NULL — Order(...) yaratadigan joy uni berishi shart. Berilmagan
# bo'lsa (eski/begona chaqiruvchi) IntegrityError o'rniga mijoz korxonasidan to'ldiriladi.
# Yengil `table()` — app.models.customer ni import qilmasdan (aylana import bo'lmasin).
_customers_t = table("customers", column("id", Integer), column("company_id", Integer))


@event.listens_for(Order, "before_insert")
def _order_fill_company_id(mapper, connection, target):
    if target.company_id is None and target.customer_id is not None:
        row = connection.execute(
            select(_customers_t.c.company_id).where(_customers_t.c.id == target.customer_id)
        ).first()
        if row and row[0] is not None:
            target.company_id = row[0]
