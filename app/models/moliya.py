from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Index, Text, Boolean, JSON, func, text  # type: ignore
from sqlalchemy import event  # type: ignore
from sqlalchemy.orm import Session, relationship, with_loader_criteria  # type: ignore
from app.database import Base  # type: ignore

# Haqiqiy pul tushadigan to'lov turlari (KassaMovement/Transaction faqat shular uchun).
CASH_PAYMENT_TYPES = ("cash", "card", "uzcard", "humo", "bank", "click", "payme", "uzum", "visa")
# Naqd bo'lmagan turlar: qarz, keshbek (bonus) va aralash — pul oqimiga yozilmaydi.
NON_CASH_PAYMENT_TYPES = ("debt", "cashback", "mixed")
# "keshbek" — eski kassa harakatlari yo'qolmasligi uchun qoladi.
PAYMENT_TYPES = list(CASH_PAYMENT_TYPES) + ["keshbek"]

class Wallet(Base):
    __tablename__ = "wallets"
    # T1.13: korxona/filial bo'yicha qidiruv indeksi
    __table_args__ = (
        Index("ix_wallets_company_branch", "company_id", "branch_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(20), nullable=False, default="cash")
    balance = Column(Numeric(14, 2), default=0)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    is_open = Column(Boolean, default=True)
    # T1.10: shaxsiy (kuryer/agent "qo'l kassasi") kassa — hech qachon umumiy fallback bo'lib tanlanmaydi,
    # ro'yxatda faqat egasiga ko'rinadi
    is_personal = Column(Boolean, nullable=False, default=False, server_default='false')
    opening_balance = Column(Numeric(14, 2), default=0)
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company")
    branch = relationship("Branch")

class ExpenseCategory(Base):
    __tablename__ = "expense_categories"
    # T2.2: nom korxona ichida (yoki umumiy qatorlar ichida) takrorlanmasin: lower(trim(name)).
    # Alembic `t2_2` migratsiyasidagi qisman unikal indekslar (Postgres'da btrim == trim).
    # SQLite (testlar bazasi)da `WHERE 1 = 0` — indeks yaratiladi, lekin hech narsani cheklamaydi: testlar migratsiyadan
    # OLDINGI takroriy nomli (legacy) kategoriyalarni ataylab yaratadi.
    __table_args__ = (
        Index("uq_expense_cat_company_name", "company_id", func.lower(func.trim(text("name"))), unique=True,
              postgresql_where=text("company_id IS NOT NULL"), sqlite_where=text("1 = 0")),
        Index("uq_expense_cat_global_name", func.lower(func.trim(text("name"))), unique=True,
              postgresql_where=text("company_id IS NULL"), sqlite_where=text("1 = 0")),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    description = Column(String(200), nullable=True)

class Expense(Base):
    __tablename__ = "expenses"
    # T2.2: P&L / xarajat hisobotlari (korxona + filial + sana) uchun indeks — alembic `t2_2` bilan bir xil nom
    __table_args__ = (
        Index("ix_expenses_company_branch_created", "company_id", "branch_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("expense_categories.id"), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    # T2.7: xarajat valyutasi (amount shu valyutada); exchange_rate/amount_uzs — yozilgan paytdagi kurs va UZS ekvivalent.
    # Kurs topilmagan eski yozuvlarda NULL — hisobotlar coalesce(amount_uzs, amount) ishlatadi.
    currency = Column(String(3), nullable=False, default="UZS", server_default="UZS")
    exchange_rate = Column(Numeric(14, 4), nullable=True)
    amount_uzs = Column(Numeric(18, 2), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    description = Column(Text, nullable=True)
    # T4.6: approved_by — haqiqiy TASDIQLOVCHI (limit ichidagi xarajatda NULL = avto-tasdiq); yaratuvchi — created_by
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    # T4.6: pending (tasdiq kutilmoqda) / approved / rejected. Faqat 'approved' kassa va P&L ga kiradi
    status = Column(String(20), nullable=False, default="approved", server_default="approved")
    approval_request_id = Column(Integer, ForeignKey("approval_requests.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # T1.19: o'chirish o'rniga bekor qilish (void) — yozuv bazada qoladi, hisobotlar voided_at IS NULL bilan ishlaydi
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    branch = relationship("Branch")
    category = relationship("ExpenseCategory")
    wallet = relationship("Wallet")
    approver = relationship("User", foreign_keys=[approved_by])

@event.listens_for(Session, "do_orm_execute")
def _hide_unapproved_expenses(state):
    """T4.6: tasdiq kutayotgan (`pending`) va rad etilgan (`rejected`) xarajatlar HECH QAYSI so'rovda ko'rinmaydi:
    P&L, filial kunlik xulosasi, moliya hisobotlari va kassa balansi faqat `approved` xarajatni sanaydi.
    Tasdiqlash oqimi (approval_service, kassa/moliya xarajat ro'yxati) uchun so'rovga
    `execution_options(include_unapproved_expenses=True)` beriladi. Refresh va atribut yuklash (`is_column_load`)
    ta'sirlanmaydi."""
    if (
        state.is_select
        and not state.is_column_load
        and not state.is_relationship_load
        and not state.execution_options.get("include_unapproved_expenses")
    ):
        state.statement = state.statement.options(
            with_loader_criteria(Expense, Expense.status == "approved", include_aliases=True)
        )


class Transaction(Base):
    __tablename__ = "transactions"
    # T1.13: eng tez o'sadigan jadval — korxona/filial/sana va havola bo'yicha so'rovlar uchun indekslar
    __table_args__ = (
        Index("ix_transactions_company_created", "company_id", "created_at"),
        Index("ix_transactions_company_branch_created", "company_id", "branch_id", "created_at"),
        Index("ix_transactions_company_type_created", "company_id", "type", "created_at"),
        Index("ix_transactions_reference", "reference_type", "reference_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    type = Column(String(20), nullable=False) # 'income', 'expense'
    amount = Column(Numeric(14, 2), nullable=False)
    reference_type = Column(String(50), nullable=True)
    reference_id = Column(Integer, nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    payment_type = Column(String(50), nullable=True)
    currency_code = Column(String(3), nullable=True, server_default='UZS', default='UZS')
    description = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    # Bekor qilish uchun kerakli tafsilotlar (masalan ta'minotchi to'lovining valyutalar bo'yicha taqsimoti)
    meta = Column(JSON, nullable=True)
    # T1.19: bekor qilingan (void) yozuv — qattiq o'chirilmaydi, hisobotlar voided_at IS NULL bilan ishlaydi
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    branch = relationship("Branch")
    wallet = relationship("Wallet")
    user = relationship("User", foreign_keys=[user_id])

class WalletBalance(Base):
    __tablename__ = "wallet_balances"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False)
    payment_type = Column(String(50), nullable=False)
    balance = Column(Numeric(14, 2), default=0)

    wallet = relationship("Wallet", backref="detailed_balances")


# ─── Kassa Sessiyasi ──────────────────────────────────────────────────────────

class KassaSession(Base):
    """Kassa ochilish/yopilish sessiyasi"""
    __tablename__ = "kassa_sessions"
    # T1.11: filial kesimidagi kunlik yopilishlar ro'yxati uchun indeks
    __table_args__ = (
        Index("ix_kassa_sessions_company_branch_opened", "company_id", "branch_id", "opened_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    # T1.11: sessiya ochilgan paytdagi kassa filiali (snapshot)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    opened_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime, nullable=True)
    opening_balance = Column(Numeric(14, 2), default=0)
    
    # Kutilgan va haqiqiy balanslarni saqlash (Blind close uchun)
    expected_summary = Column(JSON, nullable=True)   # tizim hisoblagan summa
    closing_summary = Column(JSON, nullable=True)    # kassir kiritgan summa
    difference_summary = Column(JSON, nullable=True) # oradagi farq
    
    note = Column(Text, nullable=True)
    status = Column(String(20), default="open")  # open | closed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    wallet = relationship("Wallet", backref="sessions")


# ─── Kassa Harakatlari ────────────────────────────────────────────────────────

class KassaMovement(Base):
    """Kassadagi har bir kirim/chiqim harakati (to'lov turi bo'yicha)"""
    __tablename__ = "kassa_movements"

    id = Column(Integer, primary_key=True, index=True)
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("kassa_sessions.id"), nullable=True)
    direction = Column(String(10), nullable=False)   # 'in' | 'out'
    payment_type = Column(String(30), nullable=False, default="cash")  # cash|card|uzcard|humo|click|payme|uzum|keshbek
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="UZS")
    reference_type = Column(String(50), nullable=True)   # sale|supplier_payment|expense|invest|withdraw|customer_payment
    reference_id = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    wallet = relationship("Wallet", backref="movements")
    session = relationship("KassaSession", backref="movements")

# ─── Kassa o'tkazmalari (Transfers) ──────────────────────────────────────────

class CashTransfer(Base):
    """Qat'iy 2 bosqichli kassa o'tkazmalari (Kassadan kassaga)"""
    __tablename__ = "cash_transfers"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    
    sender_wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False)
    receiver_wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=False)
    # T0.35: o'tkazma paytidagi filial snapshot (kassa keyin boshqa filialga o'tsa ham hisobot o'zgarmaydi)
    sender_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    receiver_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="UZS")
    payment_type = Column(String(30), nullable=False, default="cash")
    
    status = Column(String(20), nullable=False, default="pending")  # pending | completed | rejected
    
    sent_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    received_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    sent_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    received_at = Column(DateTime, nullable=True)
    
    note = Column(Text, nullable=True)

    sender_wallet = relationship("Wallet", foreign_keys=[sender_wallet_id])
    receiver_wallet = relationship("Wallet", foreign_keys=[receiver_wallet_id])
    sender_user = relationship("User", foreign_keys=[sent_by])
    receiver_user = relationship("User", foreign_keys=[received_by])
