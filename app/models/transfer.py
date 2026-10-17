import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class TransferStatus(str, enum.Enum):
    pending = "pending"
    in_transit = "in_transit"
    received = "received"
    cancelled = "cancelled"


class StockTransfer(Base):
    __tablename__ = "stock_transfers"
    # T1.13: ombor bo'yicha ro'yxat/qidiruv indekslari
    __table_args__ = (
        Index("ix_stock_transfers_from_wh", "from_warehouse_id"),
        Index("ix_stock_transfers_to_wh", "to_warehouse_id"),
        # T4.1: holat bo'yicha filtr ("yo'lda" transferlar)
        Index("ix_stock_transfers_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(40), unique=True, nullable=False, index=True)
    from_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    to_warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    status = Column(Enum(TransferStatus), default=TransferStatus.pending)
    note = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True)
    # T4.1: ikki bosqichli transfer — yuboruvchi/vaqt (confirmed_by/at = QABUL qilgan) va bekor qilish sababi
    sent_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    cancel_reason = Column(Text, nullable=True)

    from_warehouse = relationship("Warehouse", foreign_keys=[from_warehouse_id])
    to_warehouse = relationship("Warehouse", foreign_keys=[to_warehouse_id])
    items = relationship("StockTransferItem", back_populates="transfer", cascade="all, delete-orphan")
    # Ko'chirilgan partiyalar bog'lanishi (manba partiya → manzildagi ko'zgu partiya)
    batch_links = relationship("StockTransferBatch", back_populates="transfer", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    confirmer = relationship("User", foreign_keys=[confirmed_by])
    sender = relationship("User", foreign_keys=[sent_by])


class StockTransferItem(Base):
    __tablename__ = "stock_transfer_items"

    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("stock_transfers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    # Ixtiyoriy: maqsad omborda boshqa mahsulotga kirim qilish uchun
    # Agar None bo'lsa, product_id ishlatiladi (odatdagi holat)
    target_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=False)
    # T4.1: yuborilgan va qabul qilingan haqiqiy miqdor (quantity = rejalashtirilgan/yuborilgan);
    # kamomad (qty_sent - qty_received) hujjatda sababi bilan qoladi
    qty_sent = Column(Numeric(12, 3), nullable=True)
    qty_received = Column(Numeric(12, 3), nullable=True)
    discrepancy_reason = Column(String(200), nullable=True)

    transfer = relationship("StockTransfer", back_populates="items")
    product = relationship("Product", foreign_keys=[product_id])
    target_product = relationship("Product", foreign_keys=[target_product_id])
    variant = relationship("ProductVariant", foreign_keys=[variant_id])


class StockTransferBatch(Base):
    """Transferda ko'chirilgan partiya: manba ombordagi partiyadan qancha olinib,
    manzil omborda qaysi ko'zgu partiya yaratilgani. Bekor qilish/tahrirda shu
    qatorlar bo'yicha partiyalar qaytariladi."""
    __tablename__ = "stock_transfer_batches"

    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False, index=True)
    # Manba mahsulot (transfer qatoridagi product_id)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    source_batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    # T4.1: yo'lda (qabul qilinmagan) yoki kamomad qismi uchun NULL — manzilda ko'zgu partiya yo'q
    dest_batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True, index=True)
    # T4.1: qaysi transfer qatoriga tegishli (qabulda partiyalarni qator bo'yicha taqsimlash uchun)
    item_id = Column(Integer, ForeignKey("stock_transfer_items.id", ondelete="SET NULL"), nullable=True, index=True)
    quantity = Column(Numeric(12, 3), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    transfer = relationship("StockTransfer", back_populates="batch_links")
    source_batch = relationship("Batch", foreign_keys=[source_batch_id])
    dest_batch = relationship("Batch", foreign_keys=[dest_batch_id])
