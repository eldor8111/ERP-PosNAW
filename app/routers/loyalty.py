"""Sodiqlik dasturi sozlamalari (T2.12): korxona va filial bo'yicha qoidalar."""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.loyalty import LoyaltyBranchRule, LoyaltySettings
from app.models.user import User, UserRole
from app.services.loyalty_service import LoyaltyRules

router = APIRouter(prefix="/loyalty", tags=["Loyalty"])

READ_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier)
WRITE_ROLES = (UserRole.admin, UserRole.director)


class LoyaltySettingsIn(BaseModel):
    """PUT /loyalty/settings; `company_id` qabul qilinmaydi (korxona foydalanuvchidan olinadi)."""
    is_enabled: bool = True
    points_percent: Decimal = Field(Decimal("1"), ge=0, le=100)
    point_value: Decimal = Field(Decimal("1"), gt=0)
    default_cashback_percent: Decimal = Field(Decimal("0"), ge=0, le=100)
    max_redeem_percent: Decimal = Field(Decimal("100"), ge=0, le=100)
    accrue_on_unpaid: bool = True
    return_reverses_loyalty: bool = True
    tier_bronze: int = Field(1000, ge=0)
    tier_silver: int = Field(5000, ge=0)
    tier_gold: int = Field(10000, ge=0)

    @model_validator(mode="after")
    def tiers_ordered(self):
        if not (self.tier_bronze < self.tier_silver < self.tier_gold):
            raise ValueError("Daraja chegaralari o'sib borishi kerak: bronza < kumush < oltin")
        return self


class LoyaltyBranchRuleIn(BaseModel):
    is_enabled: bool = True
    cashback_percent_override: Optional[Decimal] = Field(None, ge=0, le=100)


def _settings_out(st: Optional[LoyaltySettings]) -> dict:
    d = LoyaltyRules()
    if st is None:
        return {
            "exists": False,
            "is_enabled": True,
            "points_percent": float(d.points_percent),
            "point_value": float(d.point_value),
            "default_cashback_percent": float(d.default_cashback_percent),
            "max_redeem_percent": float(d.max_redeem_percent),
            "accrue_on_unpaid": d.accrue_on_unpaid,
            "return_reverses_loyalty": d.return_reverses_loyalty,
            "tier_bronze": d.tier_bronze,
            "tier_silver": d.tier_silver,
            "tier_gold": d.tier_gold,
        }
    return {
        "exists": True,
        "is_enabled": bool(st.is_enabled),
        "points_percent": float(st.points_percent),
        "point_value": float(st.point_value),
        "default_cashback_percent": float(st.default_cashback_percent or 0),
        "max_redeem_percent": float(st.max_redeem_percent),
        "accrue_on_unpaid": bool(st.accrue_on_unpaid),
        "return_reverses_loyalty": bool(st.return_reverses_loyalty),
        "tier_bronze": int(st.tier_bronze),
        "tier_silver": int(st.tier_silver),
        "tier_gold": int(st.tier_gold),
    }


def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*READ_ROLES)),
):
    """Joriy korxona sodiqlik sozlamalari (qator bo'lmasa sukut qiymatlar, `exists: false`)."""
    st = db.query(LoyaltySettings).filter(LoyaltySettings.company_id == _company_id(current_user)).first()
    return _settings_out(st)


@router.put("/settings")
def put_settings(
    data: LoyaltySettingsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    cid = _company_id(current_user)
    st = db.query(LoyaltySettings).filter(LoyaltySettings.company_id == cid).first()
    old = _settings_out(st)
    if st is None:
        st = LoyaltySettings(company_id=cid)
        db.add(st)
    for k, v in data.model_dump().items():
        setattr(st, k, v)
    db.flush()
    log_action(db, "LOYALTY_SETTINGS_UPDATE", "company", cid, user_id=current_user.id,
               old_values=old, new_values=_settings_out(st), company_id=cid)
    db.commit()
    db.refresh(st)
    return _settings_out(st)


def _rule_out(branch: Branch, rule: Optional[LoyaltyBranchRule]) -> dict:
    return {
        "branch_id": branch.id,
        "branch_name": branch.name,
        "is_enabled": True if rule is None else bool(rule.is_enabled),
        "cashback_percent_override": (
            float(rule.cashback_percent_override)
            if rule is not None and rule.cashback_percent_override is not None else None
        ),
    }


@router.get("/branch-rules")
def list_branch_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*READ_ROLES)),
):
    """Korxonaning barcha filiallari va ularning sodiqlik qoidalari (qoida yo'q filial — yoqilgan, stavka yo'q)."""
    cid = _company_id(current_user)
    branches = db.query(Branch).filter(Branch.company_id == cid).order_by(Branch.id).all()
    rules = {r.branch_id: r for r in db.query(LoyaltyBranchRule).filter(LoyaltyBranchRule.company_id == cid).all()}
    return [_rule_out(b, rules.get(b.id)) for b in branches]


@router.put("/branch-rules/{branch_id}")
def put_branch_rule(
    branch_id: int,
    data: LoyaltyBranchRuleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    cid = _company_id(current_user)
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == cid).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    rule = db.query(LoyaltyBranchRule).filter(
        LoyaltyBranchRule.company_id == cid, LoyaltyBranchRule.branch_id == branch_id,
    ).first()
    old = _rule_out(branch, rule)
    if rule is None:
        rule = LoyaltyBranchRule(company_id=cid, branch_id=branch_id)
        db.add(rule)
    rule.is_enabled = data.is_enabled
    rule.cashback_percent_override = data.cashback_percent_override
    db.flush()
    log_action(db, "LOYALTY_BRANCH_RULE_UPDATE", "branch", branch_id, user_id=current_user.id,
               old_values=old, new_values=_rule_out(branch, rule), company_id=cid)
    db.commit()
    return _rule_out(branch, rule)
