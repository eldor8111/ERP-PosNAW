"""Mijoz qarzi harakatlari jurnali (T2.6).

Har bir qarz o'zgarishi (sotuv, tahrir, qaytarish, to'lov, yetkazish haqi, AI, hisobdan chiqarish)
`customer_ledger` servisi orqali shu jadvalga yoziladi. Invariant: har bir mijoz va valyuta uchun
`SUM(delta)` = `customers.debt_balances[valyuta]`.

- `branch_id` — qarz tegishli filial (sotuv filiali; sotuvsiz bo'lsa mijoz filiali);
- `cash_branch_id` — pul tushgan kassa filiali (faqat to'lovlar).
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Text  # type: ignore

from app.database import Base  # type: ignore

DEBT_LOG_KINDS = (
    "opening", "sale", "sale_edit", "payment", "reversal", "return",
    "edit", "writeoff", "delivery_fee", "ai", "recalc",
)


class CustomerDebtLog(Base):
    __tablename__ = "customer_debt_log"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    cash_branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    kind = Column(String(20), nullable=False)
    currency = Column(String(3), nullable=False, default="UZS", server_default="UZS")
    delta = Column(Numeric(20, 4), nullable=False)       # shu valyutada: + qarz oshdi, - kamaydi
    delta_uzs = Column(Numeric(20, 4), nullable=False)
    rate = Column(Numeric(14, 4), nullable=True)
    sale_id = Column(Integer, ForeignKey("sales.id", ondelete="SET NULL"), nullable=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_customer_debt_log_company_branch_customer", "company_id", "branch_id", "customer_id"),
        Index("ix_customer_debt_log_customer_created", "customer_id", "created_at"),
        Index("ix_customer_debt_log_sale", "sale_id"),
        Index("ix_customer_debt_log_transaction", "transaction_id"),
    )
