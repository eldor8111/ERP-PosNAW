from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Index, JSON, func, text  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore

class Branch(Base):
    __tablename__ = "branches"
    # T1.4: korxonada bitta asosiy filial
    __table_args__ = (
        Index(
            "uq_branches_company_main", "company_id", unique=True,
            postgresql_where=text("is_main"),
            sqlite_where=text("is_main"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    address = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)
    # T1.13: NOT NULL (bazada DEFAULT TRUE), eski kod Python default (True) bilan ishlayveradi
    is_active = Column(Boolean, nullable=False, server_default=text("true"), default=True)
    # T1.4: korxonaning asosiy filiali (nomdagi "(Asosiy)" o'rniga)
    is_main = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    # T1.13: yaratilgan sana (tarixda qo'shilib o'chirib yuborilgan ustun qaytarildi)
    created_at = Column(DateTime, nullable=False, server_default=func.now(),
                        default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    # T1.12: filialni yopish (arxivlash) izi — qachon, kim va nima sababdan
    closed_at = Column(DateTime, nullable=True)
    # FK ataylab yo'q: users.branch_id <-> branches.closed_by aylana User.branch/Branch.users
    # relationship'larini noaniq qiladi (app/models/user.py da foreign_keys yo'q)
    closed_by = Column(Integer, nullable=True)
    close_reason = Column(String(255), nullable=True)
    # T4.2: filial rekvizitlari va sozlamalari. Hammasi ixtiyoriy: bo'sh bo'lsa chek korxona shablonidan olinadi.
    code = Column(String(20), nullable=True)                 # filial kodi (korxona ichida noyob, katta-kichik harfsiz)
    legal_name = Column(String(200), nullable=True)          # yuridik nom (chek sarlavhasi)
    stir = Column(String(14), nullable=True)                 # STIR (9 xonali) yoki JSHSHIR (14 xonali)
    tax_regime = Column(String(20), nullable=True)           # 'vat' | 'turnover'; NULL = belgilanmagan
    working_hours = Column(JSON, nullable=True)              # {'mon': {'open': '09:00', 'close': '18:00', 'closed': False}, ...}
    receipt_templates = Column(JSON, nullable=True)          # {'r58': {}, 'r80': {}, 'nak': {}}; NULL = korxona shabloni

    company = relationship("Company", back_populates="branches")
    warehouses = relationship("Warehouse", back_populates="branch")
    users = relationship("User", back_populates="branch")
    customers = relationship("Customer", back_populates="branch")
    orders = relationship("Order", back_populates="branch")

    @property
    def company_name(self):
        """BranchOut.company_name uchun (joinedload(Branch.company) bilan N+1 bo'lmaydi)."""
        return self.company.name if self.company else None


# T1.13: bir korxonada bir xil nomli (katta-kichik harf va chetdagi probellarsiz) faol filial bo'lmaydi.
# Eslatma: trim() PostgreSQL'da btrim() ga teng; SQLite'da ham mavjud (testlar uchun).
Index(
    "uq_branches_company_name_active", Branch.company_id, func.lower(func.trim(Branch.name)),
    unique=True,
    postgresql_where=text("is_active IS TRUE"),
    sqlite_where=text("is_active IS TRUE"),
)
Index("ix_branches_company_id", Branch.company_id)

# T4.2: filial kodi korxona ichida noyob (katta-kichik harfsiz); kod berilmagan filiallar cheklanmaydi.
Index(
    "uq_branches_company_code", Branch.company_id, func.lower(Branch.code),
    unique=True,
    postgresql_where=text("code IS NOT NULL"),
    sqlite_where=text("code IS NOT NULL"),
)
