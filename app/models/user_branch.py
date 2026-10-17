"""
user_branches — foydalanuvchiga korxona ichida bir nechta filial biriktirish (T1.2).

`user_companies.branch_id` — asosiy (bitta) filial; `user_branches` esa qo'shimcha
to'plam (masalan, 2-3 filialga mas'ul menejer). Ruxsat etilgan filiallar =
{uc.branch_id} ∪ user_branches(user_id, company_id).
"""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, UniqueConstraint  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore


class UserBranch(Base):
    __tablename__ = "user_branches"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User")
    branch = relationship("Branch")

    __table_args__ = (
        UniqueConstraint("user_id", "branch_id", name="uq_user_branch"),
        Index("ix_user_branches_user_company", "user_id", "company_id"),
    )
