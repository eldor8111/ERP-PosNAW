from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, Numeric, ForeignKey, DateTime, Index, CheckConstraint, column, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class BranchProductPrice(Base):
    """Filial narxi (T4.3): korxona narxini (Product.sale_price/wholesale_price) shu filial uchun ustidan yozadi.

    Yozuv yo'q yoki ustun NULL bo'lsa — korxona narxi qoladi. Valyuta mahsulotning
    `sale_currency` / `wholesale_currency` bilan bir xil (alohida valyuta ustuni yo'q).
    """
    __tablename__ = "branch_product_prices"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=True)
    sale_price = Column(Numeric(16, 4), nullable=True)
    wholesale_price = Column(Numeric(16, 4), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    branch = relationship("Branch")
    product = relationship("Product")

    __table_args__ = (
        # variant_id NULL bo'lgani uchun oddiy UniqueConstraint yetmaydi (StockLevel kabi, COALESCE indeks).
        # Migratsiya: t4_3_branch_prices_promotions
        Index("uq_branch_product_price", "branch_id", "product_id",
              func.coalesce(column("variant_id"), 0), unique=True),
        CheckConstraint("sale_price IS NOT NULL OR wholesale_price IS NOT NULL",
                        name="ck_branch_price_any"),
        CheckConstraint("sale_price IS NULL OR sale_price >= 0", name="ck_branch_price_sale_nonneg"),
        CheckConstraint("wholesale_price IS NULL OR wholesale_price >= 0", name="ck_branch_price_wholesale_nonneg"),
    )
