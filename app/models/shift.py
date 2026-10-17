from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Index, Text, text  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore

class Shift(Base):
    __tablename__ = "shifts"
    # T1.13: filial kesimidagi ro'yxat indeksi va bir kassirda ikkita ochiq smena bo'lmasligi (bazada)
    __table_args__ = (
        Index("ix_shifts_company_branch_opened", "company_id", "branch_id", "opened_at"),
        Index(
            "ux_shifts_one_open_per_cashier", "cashier_id", unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    closed_at = Column(DateTime, nullable=True)
    opening_cash = Column(Numeric(14, 2), default=0)
    closing_cash = Column(Numeric(14, 2), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    status = Column(String(20), default="open") # 'open', 'closed'

    # T0.28: yopilishdagi kutilgan naqd, farq va inkassatsiya (kassalararo ichki harakat)
    expected_cash = Column(Numeric(14, 2), nullable=True)
    cash_difference = Column(Numeric(14, 2), nullable=True)
    handover_cash_amount = Column(Numeric(14, 2), nullable=True)
    handover_wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    handover_card_wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)

    # T1.11: smena bog'langan kassa, yopgan xodim va izohlar
    wallet_id = Column(Integer, ForeignKey("wallets.id"), nullable=True)
    closed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    note_open = Column(Text, nullable=True)
    note_close = Column(Text, nullable=True)

    cashier = relationship("User", foreign_keys=[cashier_id])
    closer = relationship("User", foreign_keys=[closed_by])
    branch = relationship("Branch")
    wallet = relationship("Wallet", foreign_keys=[wallet_id])

    @property
    def difference(self):
        """TZ nomi: kassir sanagan - kutilgan naqd (manfiy = kamomad). Ustun nomi `cash_difference` (T0.28)."""
        return self.cash_difference
