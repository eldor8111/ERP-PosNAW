from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, DateTime, Boolean, Date, CheckConstraint, Index
from sqlalchemy.orm import relationship

from app.database import Base


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    discount_type = Column(String(20), nullable=False, default="percent") # percent, amount
    discount_value = Column(Numeric(12, 2), nullable=False)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    # Qamrov: "all" — barcha mahsulotlar, "products" — faqat tanlangan mahsulotlar (T3.19)
    applies_to = Column(String(10), nullable=False, default="all", server_default="all")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    products = relationship("PromotionProduct", back_populates="promotion", cascade="all, delete-orphan")
    # T4.3: filiallar (bo'sh = hamma filial)
    branches = relationship("PromotionBranch", back_populates="promotion", cascade="all, delete-orphan")

    @property
    def branch_ids(self):
        return [b.branch_id for b in (self.branches or [])]

    __table_args__ = (
        CheckConstraint("applies_to IN ('all','products')", name="ck_promotions_applies_to"),
    )


class PromotionProduct(Base):
    __tablename__ = "promotion_products"

    id = Column(Integer, primary_key=True, index=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    promotion = relationship("Promotion", back_populates="products")
    product = relationship("Product")

    @property
    def product_name(self):
        return self.product.name if self.product is not None else None


class PromotionBranch(Base):
    """Aksiya amal qiladigan filial (T4.3). Aksiyada bu yozuvlar bo'lmasa — hamma filialda amal qiladi."""
    __tablename__ = "promotion_branches"

    promotion_id = Column(Integer, ForeignKey("promotions.id", ondelete="CASCADE"), primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), primary_key=True)

    promotion = relationship("Promotion", back_populates="branches")

    __table_args__ = (Index("ix_promotion_branches_branch", "branch_id"),)
