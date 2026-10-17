"""Hisobot/moliya/dashboard uchun rol bo'yicha filial doirasi (T2.1).

Siyosat:
  - `admin`, `director`, `accountant`, `super_admin` cheklanmaydi: butun korxona yoki istalgan filial.
  - `manager` cheklanadi, agar unga filial biriktirilgan bo'lsa (`user_companies.branch_id` ∪
    `user_branches`, bo'lmasa legacy `users.branch_id`) va `reports.all_branches` huquqi yo'q bo'lsa.
    Bunday menejer uchun `branch_id` majburan o'z filialiga tenglashtiriladi; boshqa filial so'ralsa 403.
  - Filialsiz (hech narsa biriktirilmagan) menejer cheklanmaydi — aks holda hisobotlar bo'sh qaytardi.
  - `reports.all_branches` huquqi `user.permissions["reports"]["all_branches"]` yoki
    `user.custom_role.permissions["reports"]["all_branches"]` orqali beriladi (mexanizm
    `require_permissions` bilan bir xil: foydalanuvchi darajasidagi aniq `False` rol huquqini bekor qiladi).

Filial konteksti (`branch_context.get_branch_context`, X-Branch-Id) bilan ishlaydigan endpointlar uchun
`effective_ctx` — `all_branches` huquqi bor foydalanuvchining kontekst cheklovini olib tashlaydi.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

from fastapi import Depends, Header, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.branch_context import (
    BRANCH_NOT_FOUND, BranchContext, _own_branch_id, assigned_branch_ids,
)
from app.core.dependencies import get_current_user, optional_bearer, require_roles
from app.core.roles import REPORT_ROLES
from app.database import get_db
from app.models.branch import Branch
from app.models.user import User, UserRole

SCOPE_FORBIDDEN = "Bu filial hisobotiga ruxsat yo'q"
COMPANY_REQUIRED = "company_id parametri majburiy"
UNASSIGNED_BRANCH = -1  # pnl_service.UNASSIGNED_BRANCH — filialsiz guruh (faqat cheklanmaganlar uchun)


@dataclass(frozen=True)
class ReportScope:
    """Hisobot filial doirasi. `restricted` — foydalanuvchi o'z filiali(lari) bilan cheklangan;
    `branch_id` — hisobotga qo'llanadigan filial (None — butun korxona);
    `allowed_branch_ids` — cheklangan foydalanuvchining ruxsat etilgan filiallari (cheklanmaganda None)."""
    restricted: bool
    branch_id: Optional[int]
    allowed_branch_ids: Optional[Tuple[int, ...]] = None


def _role_of(user) -> Optional[UserRole]:
    role = getattr(user, "role", None)
    if isinstance(role, UserRole):
        return role
    try:
        return UserRole(role)
    except (ValueError, TypeError):
        return None


def _all_branches_flag(perms) -> Optional[bool]:
    """`perms["reports"]["all_branches"]`: True/False yoki None (belgilanmagan)."""
    if not isinstance(perms, dict):
        return None
    module = perms.get("reports")
    if not isinstance(module, dict):
        return None
    flag = module.get("all_branches")
    return flag if isinstance(flag, bool) else None


def user_has_all_branches(user) -> bool:
    """`reports.all_branches` huquqi: `user.permissions` (aniq False — rad etadi) yoki `custom_role.permissions`."""
    own = _all_branches_flag(getattr(user, "permissions", None))
    if own is not None:
        return own
    role = getattr(user, "custom_role", None)
    return _all_branches_flag(getattr(role, "permissions", None)) is True


def restricted_branch_ids(db: Session, user) -> Optional[Tuple[int, ...]]:
    """Cheklangan foydalanuvchining ruxsat etilgan filiallari; cheklanmagan bo'lsa None."""
    if _role_of(user) != UserRole.manager or user_has_all_branches(user):
        return None
    ids = assigned_branch_ids(db, user)
    return tuple(ids) if ids else None


def resolve_report_scope(db: Session, user, branch_id: Optional[int]) -> ReportScope:
    """So'ralgan `branch_id` ni foydalanuvchi huquqiga qarab doiraga aylantiradi.

    Cheklangan: boshqa filial — 403 (`SCOPE_FORBIDDEN`), berilmasa — o'z (asosiy) filiali.
    Cheklanmagan: `branch_id` berilsa shu korxonaniki bo'lishi shart (aks holda 404; `-1` — filialsiz
    guruh), berilmasa butun korxona (`branch_id=None`)."""
    allowed = restricted_branch_ids(db, user)
    if allowed is not None:
        if branch_id:
            if branch_id not in allowed:
                raise HTTPException(status_code=403, detail=SCOPE_FORBIDDEN)
            return ReportScope(True, branch_id, allowed)
        own = _own_branch_id(db, user)
        return ReportScope(True, own if own in allowed else allowed[0], allowed)

    if branch_id and branch_id != UNASSIGNED_BRANCH:
        cid = getattr(user, "company_id", None)
        if cid is not None:  # korxonasiz super_admin uchun tekshiruv yo'q
            ok = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first()
            if not ok:
                raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
    return ReportScope(False, branch_id or None)


def report_scope_dep(
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr (bo'sh — doiraga qarab)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REPORT_ROLES)),
) -> ReportScope:
    """FastAPI dependency: REPORT_ROLES tekshiruvi + filial doirasi."""
    return resolve_report_scope(db, current_user, branch_id)


def report_scope_key_or_user_dep(
    request: Request,
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr (bo'sh — doiraga qarab)"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ReportScope:
    """`company_scope_by_key_or_roles` bilan birga (rol allaqachon tekshirilgan): JWT bilan kirgan
    foydalanuvchi uchun `resolve_report_scope`; API kalit korxona darajasida (cheklanmagan) ishlaydi."""
    if x_api_key or credentials is None:
        return ReportScope(False, branch_id or None)
    user = get_current_user(request, credentials, db)
    return resolve_report_scope(db, user, branch_id)


def resolve_company_id(user, company_id_param: Optional[int] = None) -> int:
    """Hisobot korxonasi. `super_admin` uchun `company_id` query majburiy (agar `user.company_id` ham
    bo'lmasa — 400); boshqa rollar uchun doim `user.company_id` (parametr e'tiborsiz)."""
    if _role_of(user) == UserRole.super_admin:
        cid = company_id_param or getattr(user, "company_id", None)
        if not cid:
            raise HTTPException(status_code=400, detail=COMPANY_REQUIRED)
        return cid
    return user.company_id


def effective_ctx(user, ctx: Optional[BranchContext]) -> Optional[BranchContext]:
    """`reports.all_branches` huquqi bor foydalanuvchi uchun filial kontekstining cheklovini
    (biriktirilgan filiallar) olib tashlaydi; boshqalar uchun kontekst o'zgarmaydi."""
    if ctx is None or ctx.allowed_branch_ids is None or ctx.bypass:
        return ctx
    if user_has_all_branches(user):
        return BranchContext(None, None, False, False, ctx.user_id)
    return ctx
