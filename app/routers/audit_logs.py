"""T1.19: Audit jurnalini o'qish (faqat admin/director; super_admin — company_id parametri bilan)."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.user import User, UserRole

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


def _parse_date(value: Optional[str], end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.strip())
    except ValueError:
        raise HTTPException(400, "Sana formati noto'g'ri (YYYY-MM-DD)")
    # Faqat sana berilgan bo'lsa — "gacha" chegarasi keyingi kun boshigacha (shu kun kiradi)
    if end and len(value.strip()) <= 10:
        d = d + timedelta(days=1)
    return d.replace(tzinfo=None)


@router.get("")
def list_audit_logs(
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    entity_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    company_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    q = db.query(AuditLog)
    if current_user.role == UserRole.super_admin:
        # Super admin hamma korxonani ko'ra oladi; company_id berilsa — o'sha korxona
        if company_id is not None:
            q = q.filter(AuditLog.company_id == company_id)
    else:
        q = q.filter(AuditLog.company_id == current_user.company_id)

    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    if action:
        q = q.filter(AuditLog.action == action)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if branch_id is not None:
        q = q.filter(AuditLog.branch_id == branch_id)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == entity_id)
    df = _parse_date(date_from)
    dt = _parse_date(date_to, end=True)
    if df:
        q = q.filter(AuditLog.created_at >= df)
    if dt:
        q = q.filter(AuditLog.created_at < dt)

    total = q.count()
    rows = q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(skip).limit(limit).all()

    user_ids = {r.user_id for r in rows if r.user_id}
    branch_ids = {r.branch_id for r in rows if r.branch_id}
    users = {u.id: u.name for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    branches = {b.id: b.name for b in db.query(Branch).filter(Branch.id.in_(branch_ids)).all()} if branch_ids else {}

    return {
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "user_id": r.user_id,
                "user_name": users.get(r.user_id),
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "branch_id": r.branch_id,
                "branch_name": branches.get(r.branch_id),
                "old_values": r.old_values,
                "new_values": r.new_values,
                "ip_address": r.ip_address,
            }
            for r in rows
        ],
        "total": total,
    }
