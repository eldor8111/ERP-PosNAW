from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean, and_
from sqlalchemy.orm import relationship

from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    sort_order = Column(Integer, default=0)
    is_deleted = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent")
    products = relationship("Product", primaryjoin="(Category.id==Product.category_id) & (Product.is_deleted==False)", back_populates="category")

    @property
    def products_count(self):
        return len(self.products)
