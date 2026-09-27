import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ProductionOrderStatus(str, enum.Enum):
    draft = "draft"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class ProductionOrder(Base):
    """Ishlab chiqarish buyurtmasi. Xom ashyo faqat `completed` bosqichida
    (bir vaqtning o'zida, bitta tranzaksiyada) hisobdan chiqadi va tayyor
    mahsulot kiradi — shuning uchun draft/in_progress bosqichida bekor
    qilish uchun qoldiqni qaytarish shart emas (hali hech narsa harakatlanmagan)."""
    __tablename__ = "production_orders"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(30), unique=True, nullable=False, index=True)

    bom_id = Column(Integer, ForeignKey("boms.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)

    planned_quantity = Column(Numeric(14, 4), nullable=False)
    produced_quantity = Column(Numeric(14, 4), default=0)
    defect_quantity = Column(Numeric(14, 4), default=0)
    # Yakunlanganda hisoblangan tannarx (xom ashyo narxi + qo'shimcha xarajatlar)
    unit_cost = Column(Numeric(16, 4), nullable=True)
    total_cost = Column(Numeric(16, 2), nullable=True)

    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)  # xom ashyo shu ombordan chiqadi
    target_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)  # tayyor mahsulot shu omborga kiradi

    status = Column(Enum(ProductionOrderStatus), default=ProductionOrderStatus.draft)
    note = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    bom = relationship("BOM")
    product = relationship("Product", foreign_keys=[product_id])
    variant = relationship("ProductVariant", foreign_keys=[variant_id])
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id])
    target_warehouse = relationship("Warehouse", foreign_keys=[target_warehouse_id])
    creator = relationship("User", foreign_keys=[created_by])
    costs = relationship("ProductionOrderCost", back_populates="production_order", cascade="all, delete-orphan")


class ProductionOrderCost(Base):
    """Ishlab chiqarish buyurtmasiga qo'lda kiritiladigan qo'shimcha
    xarajatlar (ishchi haqi, kommunal, amortizatsiya va h.k.) — tannarx
    hisobiga xom ashyo narxi bilan birga qo'shiladi."""
    __tablename__ = "production_order_costs"

    id = Column(Integer, primary_key=True, index=True)
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)
    cost_type = Column(String(30), nullable=False)  # labor, utility, overhead, other
    amount = Column(Numeric(16, 2), nullable=False)
    note = Column(String(300), nullable=True)

    production_order = relationship("ProductionOrder", back_populates="costs")
