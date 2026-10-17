"""T4.6 — tasdiqlash (approval) qoidalari va so'rovlari.

- `/approvals/rules` — limit qoidalari (admin, director).
- `/approvals/requests` — kassir/menejer so'rov yuboradi; admin/director/menejer (menejer — faqat o'z filiali) hal qiladi.
Servis mantiqi: `app/services/approval_service.py`.
"""
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action_for
from app.core.dependencies import require_roles
from app.database import get_db
from app.models.approval import ApprovalRequest, ApprovalRule
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["Approvals"])

_ADMINS = (UserRole.admin, UserRole.director)
_APPROVERS = (UserRole.admin, UserRole.director, UserRole.manager)
_REQUESTERS = (UserRole.cashier, UserRole.manager, UserRole.accountant)
_ALL = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.cashier)

ActionType = Literal["discount", "price_override", "expense", "refund", "sale_delete"]
RuleMode = Literal["block", "require_approval"]
_ROLE_VALUES = tuple(r.value for r in UserRole)


# ─── Sxemalar ────────────────────────────────────────────────────────────────

class RuleIn(BaseModel):
    action_type: ActionType
    role: Optional[str] = None
    branch_id: Optional[int] = None
    threshold_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    threshold_amount: Optional[Decimal] = Field(None, ge=0)
    mode: RuleMode = "require_approval"
    is_active: bool = True

    @field_validator("role", mode="before")
    @classmethod
    def _role_ok(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if v not in _ROLE_VALUES:
            raise ValueError("Noma'lum rol")
        return v

    @field_validator("branch_id", mode="before")
    @classmethod
    def _blank_branch(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class RulePatch(BaseModel):
    action_type: Optional[ActionType] = None
    role: Optional[str] = None
    branch_id: Optional[int] = None
    threshold_percent: Optional[Decimal] = Field(None, ge=0, le=100)
    threshold_amount: Optional[Decimal] = Field(None, ge=0)
    mode: Optional[RuleMode] = None
    is_active: Optional[bool] = None

    @field_validator("role", mode="before")
    @classmethod
    def _role_ok(cls, v):
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        if v not in _ROLE_VALUES:
            raise ValueError("Noma'lum rol")
        return v


class RequestIn(BaseModel):
    action_type: ActionType
    branch_id: Optional[int] = None
    amount: Decimal = Field(Decimal("0"), ge=0)
    payload: dict = Field(default_factory=dict)
    reason: Optional[str] = Field(None, max_length=1000)


class DecisionIn(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _branch_or_404(db: Session, branch_id: int, company_id: int) -> Branch:
    b = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    return b


def _rule_out(r: ApprovalRule) -> dict:
    return {
        "id": r.id, "company_id": r.company_id, "branch_id": r.branch_id,
        "branch_name": r.branch.name if r.branch is not None else None,
        "action_type": r.action_type, "role": r.role,
        "threshold_percent": float(r.threshold_percent) if r.threshold_percent is not None else None,
        "threshold_amount": float(r.threshold_amount) if r.threshold_amount is not None else None,
        "mode": r.mode, "is_active": bool(r.is_active),
        "created_at": r.created_at, "updated_at": r.updated_at,
    }


def _request_out(r: ApprovalRequest) -> dict:
    return {
        "id": r.id, "company_id": r.company_id, "branch_id": r.branch_id,
        "branch_name": r.branch.name if r.branch is not None else None,
        "action_type": r.action_type, "status": r.status,
        "requested_by": r.requested_by, "requested_by_name": r.requester.name if r.requester is not None else None,
        "decided_by": r.decided_by, "decided_by_name": r.decider.name if r.decider is not None else None,
        "amount": float(r.amount) if r.amount is not None else None,
        "payload": r.payload, "reason": r.reason, "decision_note": r.decision_note,
        "created_at": r.created_at, "decided_at": r.decided_at, "expires_at": r.expires_at, "used_at": r.used_at,
        "reference_type": r.reference_type, "reference_id": r.reference_id,
    }


def _load_request(db: Session, request_id: int) -> Optional[ApprovalRequest]:
    return db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.branch), joinedload(ApprovalRequest.requester), joinedload(ApprovalRequest.decider),
    ).filter(ApprovalRequest.id == request_id).first()


# ─── Qoidalar ────────────────────────────────────────────────────────────────

@router.get("/rules")
def list_rules(db: Session = Depends(get_db), user: User = Depends(require_roles(*_ADMINS))):
    rows = db.query(ApprovalRule).options(joinedload(ApprovalRule.branch)).filter(
        ApprovalRule.company_id == user.company_id,
    ).order_by(ApprovalRule.action_type, ApprovalRule.id).all()
    return [_rule_out(r) for r in rows]


@router.post("/rules", status_code=201)
def create_rule(data: RuleIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*_ADMINS))):
    if data.branch_id is not None:
        _branch_or_404(db, data.branch_id, user.company_id)
    rule = ApprovalRule(
        company_id=user.company_id, branch_id=data.branch_id, action_type=data.action_type, role=data.role,
        threshold_percent=data.threshold_percent, threshold_amount=data.threshold_amount,
        mode=data.mode, is_active=data.is_active,
    )
    db.add(rule)
    db.flush()
    log_action_for(db, user, "APPROVAL_RULE_CREATE", "approval_rule", rule.id, new_values=_rule_audit(rule),
                   branch_id=rule.branch_id)
    db.commit()
    db.refresh(rule)
    return _rule_out(rule)


def _rule_audit(r: ApprovalRule) -> dict:
    d = _rule_out(r)
    return {k: d[k] for k in ("branch_id", "action_type", "role", "threshold_percent", "threshold_amount", "mode",
                              "is_active")}


def _own_rule_or_404(db: Session, rule_id: int, company_id: int) -> ApprovalRule:
    rule = db.query(ApprovalRule).filter(ApprovalRule.id == rule_id, ApprovalRule.company_id == company_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Qoida topilmadi")
    return rule


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, data: RulePatch, db: Session = Depends(get_db),
                user: User = Depends(require_roles(*_ADMINS))):
    rule = _own_rule_or_404(db, rule_id, user.company_id)
    old = _rule_audit(rule)
    fields = data.model_fields_set
    if "branch_id" in fields and data.branch_id is not None:
        _branch_or_404(db, data.branch_id, user.company_id)
    for name in ("action_type", "role", "branch_id", "threshold_percent", "threshold_amount", "mode", "is_active"):
        if name in fields:
            value = getattr(data, name)
            if name in ("action_type", "mode", "is_active") and value is None:
                continue      # bu maydonlar NULL bo'la olmaydi
            setattr(rule, name, value)
    log_action_for(db, user, "APPROVAL_RULE_UPDATE", "approval_rule", rule.id, old_values=old,
                   new_values=_rule_audit(rule), branch_id=rule.branch_id)
    db.commit()
    db.refresh(rule)
    return _rule_out(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*_ADMINS))):
    rule = _own_rule_or_404(db, rule_id, user.company_id)
    log_action_for(db, user, "APPROVAL_RULE_DELETE", "approval_rule", rule.id, old_values=_rule_audit(rule),
                   branch_id=rule.branch_id)
    db.delete(rule)
    db.commit()
    return {"ok": True}


# ─── So'rovlar ───────────────────────────────────────────────────────────────

@router.post("/requests", status_code=201)
def create_request(
    data: RequestIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_REQUESTERS)),
):
    """So'rov yuborish (15 daqiqa amal qiladi). `payload_hash` serverda hisoblanadi. Filial berilmasa — xodim filiali."""
    branch_id = data.branch_id
    if branch_id is not None:
        _branch_or_404(db, branch_id, user.company_id)
    else:
        from app.core.branch_context import effective_branch_id
        branch_id = effective_branch_id(db, user)
    new_hash = approval_service.compute_payload_hash(data.payload)
    # Bir xil tarkibli kutilayotgan so'rov takror yaratilmaydi (qayta urinish/ikki marta bosish)
    approval_service.expire_stale(db, user.company_id)
    dup = db.query(ApprovalRequest).filter(
        ApprovalRequest.company_id == user.company_id, ApprovalRequest.requested_by == user.id,
        ApprovalRequest.status == "pending", ApprovalRequest.action_type == data.action_type,
        ApprovalRequest.payload_hash == new_hash,
    ).first()
    if dup is not None:
        db.commit()
        return {"id": dup.id, "status": dup.status, "expires_at": dup.expires_at}
    req = approval_service.create_request(
        db, user, action_type=data.action_type, branch_id=branch_id, amount=data.amount, payload=data.payload,
        reason=data.reason,
    )
    db.commit()
    background_tasks.add_task(approval_service.notify_approvers_by_id, req.id)
    return {"id": req.id, "status": req.status, "expires_at": req.expires_at}


@router.get("/requests")
def list_requests(
    status: Optional[str] = Query(None),
    branch_id: Optional[int] = Query(None),
    mine: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*_ALL)),
):
    """Approver (admin/director/menejer) — korxona so'rovlari (menejer faqat o'z filiali). Boshqa rollar — faqat o'zinikilari."""
    if approval_service.expire_stale(db, user.company_id):
        db.commit()
    q = db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.branch), joinedload(ApprovalRequest.requester), joinedload(ApprovalRequest.decider),
    ).filter(ApprovalRequest.company_id == user.company_id)
    is_approver = user.role in _APPROVERS
    if mine or not is_approver:
        q = q.filter(ApprovalRequest.requested_by == user.id)
    elif user.role == UserRole.manager:
        ids = approval_service.approver_branch_ids(db, user)
        q = q.filter(ApprovalRequest.branch_id.in_(list(ids))) if ids else q.filter(ApprovalRequest.id == -1)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    if branch_id is not None:
        q = q.filter(ApprovalRequest.branch_id == branch_id)
    return [_request_out(r) for r in q.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
            .offset(skip).limit(limit).all()]


@router.get("/requests/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*_ALL))):
    """Kassir tasdiq holatini kutib turishi uchun (so'rovchi yoki approver)."""
    req = _load_request(db, request_id)
    if req is None or not approval_service.can_see_request(db, user, req):
        raise HTTPException(status_code=404, detail="So'rov topilmadi")
    if req.status in ("pending", "approved") and req.expires_at is not None \
            and approval_service._naive(req.expires_at) <= approval_service._utcnow():
        approval_service.expire_request(db, req)
        db.commit()
    return _request_out(req)


def _decide(request_id: int, approve: bool, data: Optional[DecisionIn], request: Request, db: Session, user: User):
    req = approval_service.decide(
        db, request_id, user, approve, data.note if data else None, ip=_client_ip(request),
    )
    return {"id": req.id, "status": req.status, "decided_by": req.decided_by, "decided_at": req.decided_at,
            "expires_at": req.expires_at}


@router.post("/requests/{request_id}/approve")
def approve_request(request_id: int, request: Request, data: Optional[DecisionIn] = None,
                    db: Session = Depends(get_db), user: User = Depends(require_roles(*_APPROVERS))):
    return _decide(request_id, True, data, request, db, user)


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: int, request: Request, data: Optional[DecisionIn] = None,
                   db: Session = Depends(get_db), user: User = Depends(require_roles(*_APPROVERS))):
    return _decide(request_id, False, data, request, db, user)
