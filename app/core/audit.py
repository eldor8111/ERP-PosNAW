from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

# Audit jurnali tez o'sadi: katta ro'yxatlar (items va h.k.) shu sondan ortig'i qirqiladi.
_MAX_LIST_ITEMS = 50


def _trim(value: Any, depth: int = 0) -> Any:
    """old_values/new_values hajmini cheklaydi: 50 tadan uzun ro'yxatlar qirqiladi."""
    if depth > 4:
        return value
    if isinstance(value, list):
        out = [_trim(v, depth + 1) for v in value[:_MAX_LIST_ITEMS]]
        if len(value) > _MAX_LIST_ITEMS:
            out.append({"_truncated": len(value) - _MAX_LIST_ITEMS})
        return out
    if isinstance(value, dict):
        return {k: _trim(v, depth + 1) for k, v in value.items()}
    return value


def log_action(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    user_id: Optional[int] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    ip_address: Optional[str] = None,
    company_id: Optional[int] = None,
    branch_id: Optional[int] = None,
):
    # T1.19: company_id/branch_id berilmasa foydalanuvchidan olinadi (identity map keshidan)
    if user_id is not None and (company_id is None or branch_id is None):
        from app.models.user import User
        u = db.get(User, user_id)
        if u is not None:
            if company_id is None:
                company_id = u.company_id
            if branch_id is None:
                branch_id = u.branch_id
    log = AuditLog(
        user_id=user_id,
        company_id=company_id,
        branch_id=branch_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values=_trim(old_values),
        new_values=_trim(new_values),
        ip_address=ip_address,
    )
    db.add(log)
    return log


def log_action_for(
    db: Session,
    user,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    ip_address: Optional[str] = None,
    branch_id: Optional[int] = None,
    company_id: Optional[int] = None,
):
    """`user` obyektidan user_id, company_id va (berilmasa) branch_id ni oladi — qo'shimcha so'rovsiz."""
    return log_action(
        db, action, entity_type, entity_id,
        user_id=getattr(user, "id", None),
        old_values=old_values, new_values=new_values, ip_address=ip_address,
        company_id=company_id if company_id is not None else getattr(user, "company_id", None),
        branch_id=branch_id if branch_id is not None else getattr(user, "branch_id", None),
    )
