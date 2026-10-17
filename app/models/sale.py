import enum
from datetime import datetime, timezone

from sqlalchemy import event, select, Column, DateTime, Date, Enum, ForeignKey, Integer, Numeric, String, Text, Index, JSON  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class PaymentType(str, enum.Enum):
    cash = "cash"
    card = "card"
    uzcard = "uzcard"
    humo = "humo"
    bank = "bank"
    click = "click"
    payme = "payme"
    visa = "visa"
    uzum = "uzum"
    debt = "debt"
    mixed = "mixed"
    cashback = "cashback"  # Mijoz bonus_balance hisobidan to'lov


class SaleStatus(str, enum.Enum):
    completed = "completed"
    refunded = "refunded"
    partial_refund = "partial_refund"
    cancelled = "cancelled"
    pending = "pending"


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(40), unique=True, nullable=False, index=True)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_amount = Column(Numeric(20, 4), nullable=False)
    discount_amount = Column(Numeric(20, 4), default=0)
    paid_amount = Column(Numeric(20, 4), nullable=False)
    paid_cash = Column(Numeric(20, 4), default=0)
    paid_card = Column(Numeric(20, 4), default=0)
    paid_cashback = Column(Numeric(20, 4), default=0)
    cashback_earned = Column(Numeric(20, 4), default=0)
    # T2.12: sotuv paytida mijozning total_spent ga qo'shilgan (UZS) summa — qaytarish/tahrir/o'chirishda
    # teskari hisob shu qiymat bo'yicha (joriy kurs/foizga emas). Eski sotuvlarda NULL -> total_amount.
    loyalty_base = Column(Numeric(20, 4), nullable=True)
    payment_type = Column(Enum(PaymentType), nullable=False)
    status = Column(Enum(SaleStatus), default=SaleStatus.completed)
    note = Column(Text, nullable=True)
    currency_id = Column(Integer, ForeignKey("currencies.id"), nullable=True)
    exchange_rate = Column(Numeric(14, 2), nullable=True, default=1)
    loyalty_points_earned = Column(Integer, default=0)
    loyalty_points_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    # T1.9: sotuv filiali SNAPSHOT — yaratilganda ombor (yo'q bo'lsa kassir/asosiy) filialidan yoziladi.
    # Ombor keyin boshqa filialga o'tkazilsa yoki sotuv tahrirlansa/qaytarilsa o'zgarmaydi;
    # filial hisobotlari shu ustun bo'yicha ishlaydi. Eski qatorlar migratsiya bilan to'ldiriladi.
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)
    # T1.10: sotuv puli tushgan kassa (qaytarishda asl kassa shu yerdan olinadi). Eski sotuvlar migratsiya bilan to'ldirilgan.
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    # Sotuv qaysi kassir smenasida qilingani — aniq bog'lanish (vaqt-oyna
    # taxmini o'rniga). Eski sotuvlarda NULL, ular uchun vaqt-oyna zaxira.
    shift_id = Column(Integer, ForeignKey("shifts.id"), nullable=True, index=True)
    # Savdo agenti mobil ilovadan olgan buyurtma (User.role = agent)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Takroriy sotuvdan himoya: POS har sotuvni Idempotency-Key: <uuid>
    # headeri bilan yuboradi (oflayn navbatdan qayta yuborilganda ham
    # xuddi shu kalit) — takror kelsa mavjud sotuv qaytariladi.
    # Unikallik kompaniya doirasida (kompozit indeks quyida) — global emas,
    # aks holda boshqa kompaniya kaliti bilan to'qnashuv 500 berardi.
    idempotency_key = Column(String(64), nullable=True)

    # Fiskal chek ma'lumotlari (Hippo Communicator natijasi) — POS
    # fiskalizatsiyadan keyin PATCH /sales/{id}/fiscal orqali yuboradi.
    fiscal_sign = Column(String(64), nullable=True)
    fiscal_qr_url = Column(Text, nullable=True)
    fiscal_receipt_seq = Column(Integer, nullable=True)
    fiscal_transaction_id = Column(String(64), nullable=True)
    fiscal_at = Column(DateTime, nullable=True)
    # T3.18: fiskallash qaysi fiskal modul (Hippo factory_id) orqali bajarilgani — filial qurilmalari ro'yxati bilan tekshiriladi
    fiscal_factory_id = Column(String(64), nullable=True)
    debt_due_date = Column(Date, nullable=True)
    debt_amounts = Column(JSON, nullable=True, server_default='{}')
    before_debt_balances = Column(JSON, nullable=True)
    # Qaytarish hujjati (R...) uchun asl sotuvga havola (T0.30). Qisman qaytarishda
    # to'ldiriladi; eski to'liq qaytarish ("Vazvrat: ...") hujjatlarida NULL qoladi.
    original_sale_id = Column(Integer, ForeignKey("sales.id"), nullable=True, index=True)

    currency = relationship("Currency")
    warehouse = relationship("Warehouse")
    branch = relationship("Branch", foreign_keys=[branch_id])
    customer = relationship("Customer")
    cashier = relationship("User", foreign_keys=[cashier_id])
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    payments = relationship("SalePayment", back_populates="sale", cascade="all, delete-orphan")
    # Yetkazib berish (faqat o'qish uchun — yozish sale_delivery_service orqali)
    delivery = relationship("SaleDelivery", uselist=False, viewonly=True)

    __table_args__ = (
        Index('ix_sale_company_created', 'company_id', 'created_at'),
        Index('ix_sale_company_status', 'company_id', 'status'),
        Index('ix_sale_company_branch_created', 'company_id', 'branch_id', 'created_at'),
        Index('ux_sales_company_idem_key', 'company_id', 'idempotency_key', unique=True),
    )


@event.listens_for(Sale, "before_insert")
def _sale_fill_branch(mapper, connection, target):
    """T1.9 xavfsizlik to'ri: `branch_id` aniq berilmagan sotuv (masalan qaytarish hujjati) ham
    filialsiz qolmasin. `create_sale`/`create_pending_sale` filialni o'zi aniqlab beradi; bu yerda faqat
    qolgan yo'llar uchun: asl sotuv filiali (qaytarish) -> ombor filiali (faqat o'z korxonasidan).
    Topilmasa NULL qoladi (kassir/korxona filialiga taxmin qilinmaydi)."""
    if target.branch_id is not None:
        return
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse

    cid = target.company_id

    def _own(bid):
        if not bid:
            return None
        q = select(Branch.id).where(Branch.id == bid)
        if cid is not None:
            q = q.where(Branch.company_id == cid)
        return connection.execute(q).scalar()

    found = None
    if target.original_sale_id:
        found = _own(connection.execute(
            select(Sale.branch_id).where(Sale.id == target.original_sale_id)
        ).scalar())
    if not found and target.warehouse_id:
        q = select(Warehouse.branch_id).where(Warehouse.id == target.warehouse_id)
        if cid is not None:
            q = q.where(Warehouse.company_id == cid)
        found = _own(connection.execute(q).scalar())
    target.branch_id = found


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)  # Qaysi ombordan sotildi
    unit = Column(String(20), nullable=True, default="dona")  # Mahsulot o'lchov birligi
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_price = Column(Numeric(16, 4), nullable=False)
    cost_price = Column(Numeric(16, 4), nullable=False)
    discount = Column(Numeric(16, 4), default=0)
    subtotal = Column(Numeric(20, 4), nullable=False)
    returned_quantity = Column(Numeric(12, 3), nullable=True, default=0)
    currency_code = Column(String(10), default="UZS")
    exchange_rate = Column(Numeric(14, 2), default=1)
    # Har bir sotilgan birlik uchun skanerlangan Data Matrix (markirovka) kodlari
    marking_codes = Column(JSON, nullable=True)
    # T4.3: qo'llangan aksiya va undagi chegirma ulushi (discount ichida; qo'shimcha chegirma emas)
    promotion_id = Column(Integer, ForeignKey("promotions.id", ondelete="SET NULL"), nullable=True)
    promotion_discount = Column(Numeric(16, 4), nullable=True)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")
    warehouse = relationship("Warehouse", foreign_keys=[warehouse_id])
    batches = relationship("SaleItemBatch", back_populates="sale_item", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_sale_item_sale_id', 'sale_id'),
        Index('ix_sale_item_product_id', 'product_id'),
        Index('ix_sale_items_promotion', 'promotion_id'),
    )


class SaleItemBatch(Base):
    __tablename__ = "sale_item_batches"

    id = Column(Integer, primary_key=True, index=True)
    sale_item_id = Column(Integer, ForeignKey("sale_items.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit_cost = Column(Numeric(14, 2), nullable=False)

    sale_item = relationship("SaleItem", back_populates="batches")
    batch = relationship("Batch")


class SalePayment(Base):
    __tablename__ = "sale_payments"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    payment_type = Column(String(50), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    # T3.18: provayder (click/payme/uzum) tranzaksiya raqami va to'lov terminali — ko'chirma bilan solishtirish uchun
    reference = Column(String(64), nullable=True, index=True)
    terminal_id = Column(Integer, ForeignKey("payment_terminals.id", ondelete="SET NULL"), nullable=True)

    sale = relationship("Sale", back_populates="payments")
