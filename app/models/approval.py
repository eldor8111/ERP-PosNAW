"""T4.6 — filial amallari uchun tasdiqlash (approval) qoidalari va so'rovlari.

`ApprovalRule` — qaysi amal (chegirma, narx tushirish, xarajat, qaytarish, sotuvni o'chirish), qaysi rol va
qaysi filial uchun limit borligi. Qoida yo'q bo'lsa xatti-harakat o'zgarmaydi (default o'chiq).
`ApprovalRequest` — kassir/menejer yuborgan va menejer/direktor hal qiladigan bir martalik so'rov.
"""
from datetime import datetime, timezone

from sqlalchemy import (  # type: ignore
    Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text,
)
from sqlalchemy.orm import relationship  # type: ignore

from app.database import Base  # type: ignore

ACTION_TYPES = ("discount", "price_override", "expense", "refund", "sale_delete")
RULE_MODES = ("block", "require_approval")
REQUEST_STATUSES = ("pending", "approved", "rejected", "expired", "used")


def _now():
    return datetime.now(timezone.utc)


class ApprovalRule(Base):
    __tablename__ = "approval_rules"
    __table_args__ = (
        Index("ix_approval_rules_company_action", "company_id", "action_type", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    # NULL — butun korxona; aks holda faqat shu filial (filial qoidasi korxona qoidasidan ustun)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    action_type = Column(String(20), nullable=False)
    # NULL — barcha rollar (admin/director baribir ozod)
    role = Column(String(30), nullable=True)
    threshold_percent = Column(Numeric(5, 2), nullable=True)
    threshold_amount = Column(Numeric(20, 2), nullable=True)
    mode = Column(String(20), nullable=False, default="require_approval", server_default="require_approval")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    branch = relationship("Branch")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_req_company_status", "company_id", "status", "created_at"),
        Index("ix_approval_req_branch", "branch_id"),
        CheckConstraint(
            "status IN ('pending','approved','rejected','expired','used')", name="ck_approval_req_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    action_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    amount = Column(Numeric(20, 2), nullable=True)
    payload = Column(JSON, nullable=True)
    payload_hash = Column(String(64), nullable=False)
    reason = Column(Text, nullable=True)
    decision_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    decided_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    used_at = Column(DateTime, nullable=True)
    # Tasdiq ishlatilgan hujjat (sale, expense, ...)
    reference_type = Column(String(30), nullable=True)
    reference_id = Column(Integer, nullable=True)

    requester = relationship("User", foreign_keys=[requested_by])
    decider = relationship("User", foreign_keys=[decided_by])
    branch = relationship("Branch")
