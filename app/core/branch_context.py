"""Yagona joriy filial konteksti (T1.1).

Joriy filial `X-Branch-Id` header'idan (ixtiyoriy) va foydalanuvchining joriy korxonadagi
filial(lar)idan aniqlanadi (T1.2: `user_companies.branch_id` ∪ `user_branches`, bo'lmasa
legacy `users.branch_id`). JWT'ga filial claim'i qo'shilmaydi — filial almashtirish qayta
login talab qilmasin.

Qoidalar:
  1. Bypass rol (admin/director/super_admin): header bo'lsa filial shu korxonaniki va faol
     bo'lishi shart, aks holda 404 "Filial topilmadi". Header yo'q — barcha filiallar.
     super_admin uchun header e'tiborsiz (u korxonaga bog'liq emas).
  2. Non-bypass, biriktirilgan filial(lar) bor (shu korxonaniki): faqat shular. Header ro'yxatdan
     tashqari filialni ko'rsatsa 403 "Bu filialga ruxsat yo'q". Bitta filial — avto-tanlanadi;
     bir nechta — header bo'lmasa hammasi birga (`allowed_branch_ids`), `branch_id=None`.
  2b. `reports.all_branches` huquqi bor manager (T2.1) — biriktirilgan filialdan qat'i nazar cheklanmaydi.
  3. Non-bypass, filial yo'q: manager/accountant — barcha filiallar; boshqalar (cashier,
     warehouse va h.k.) — korxonada 1 ta faol filial bo'lsa o'sha avto-aniqlanadi, 0 ta bo'lsa
     cheklov yo'q, 2+ bo'lsa hech narsa ko'rmaydi (`needs_assignment=True`).
"""
from dataclasses import dataclass
from typing import FrozenSet, Optional, Set

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse

BRANCH_BYPASS_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)
UNASSIGNED_SEES_ALL_ROLES = (UserRole.manager, UserRole.accountant)

BRANCH_HEADER = "X-Branch-Id"
BRANCH_NOT_FOUND = "Filial topilmadi"
BRANCH_FORBIDDEN = "Bu filialga ruxsat yo'q"
BRANCH_HEADER_INVALID = "X-Branch-Id butun son bo'lishi kerak"


@dataclass(frozen=True)
class BranchContext:
    """Joriy so'rovning filial doirasi.

    `branch_id` — faol (tanlangan) filial, `None` esa "barcha filiallar".
    `allowed_branch_ids` — ruxsat etilgan filiallar; `None` cheklanmaganlikni bildiradi,
    bo'sh to'plam esa "hech narsa" (filial biriktirilmagan xodim).
    """
    branch_id: Optional[int]
    allowed_branch_ids: Optional[FrozenSet[int]]
    bypass: bool
    needs_assignment: bool
    user_id: Optional[int] = None

    @property
    def unrestricted(self) -> bool:
        """Hech qanday filial filtri qo'llanmaydi."""
        return self.branch_id is None and self.allowed_branch_ids is None

    def scope_ids(self) -> Optional[FrozenSet[int]]:
        """Filtr uchun filial id'lari: `None` — filtr yo'q, aks holda `in_(...)` uchun to'plam."""
        if self.branch_id is not None:
            return frozenset({self.branch_id})
        return self.allowed_branch_ids


def _role_of(user) -> Optional[UserRole]:
    role = getattr(user, "role", None)
    if isinstance(role, UserRole):
        return role
    try:
        return UserRole(role)
    except (ValueError, TypeError):
        return None


def _parse_header(request: Optional[Request]) -> Optional[int]:
    """`X-Branch-Id` header'ini o'qiydi; bo'sh/yo'q → None, son emas → 400."""
    if request is None:
        return None
    raw = request.headers.get(BRANCH_HEADER)
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=BRANCH_HEADER_INVALID)


def _company_branch_id(db: Session, branch_id: Optional[int], company_id) -> Optional[int]:
    """`branch_id` shu korxonaniki bo'lsa qaytaradi, aks holda None."""
    if not branch_id:
        return None
    row = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    return row[0] if row else None


def _legacy_branch_id(db: Session, user) -> Optional[int]:
    """`users.branch_id` — faqat `Branch.company_id == user.company_id` bo'lsa (legacy ko'zgu)."""
    return _company_branch_id(db, getattr(user, "branch_id", None), getattr(user, "company_id", None))


def _own_branch_id(db: Session, user) -> Optional[int]:
    """Joriy korxona bo'yicha asosiy filial (T1.2): `user_companies.branch_id`, bo'lmasa
    legacy `users.branch_id` — ikkalasi ham faqat `Branch.company_id == user.company_id` bo'lsa."""
    from app.models.user_company import UserCompany

    user_id = getattr(user, "id", None)
    company_id = getattr(user, "company_id", None)
    if user_id and company_id is not None:
        row = db.query(UserCompany.branch_id).filter(
            UserCompany.user_id == user_id, UserCompany.company_id == company_id,
        ).first()
        found = _company_branch_id(db, row[0] if row else None, company_id)
        if found is not None:
            return found
    return _legacy_branch_id(db, user)


def assigned_branch_ids(db: Session, user) -> list:
    """Joriy korxona bo'yicha ruxsat etilgan filiallar (tartiblangan, T1.2):
    `{uc.branch_id} ∪ user_branches(user_id, company_id)`; bo'sh bo'lsa legacy `users.branch_id`
    (faqat shu korxonaniki). Begona korxona filiali hech qachon kirmaydi."""
    from app.models.user_branch import UserBranch
    from app.models.user_company import UserCompany

    user_id = getattr(user, "id", None)
    company_id = getattr(user, "company_id", None)
    if not user_id or company_id is None:
        return []
    ids = set()
    row = db.query(UserCompany.branch_id).filter(
        UserCompany.user_id == user_id, UserCompany.company_id == company_id,
    ).first()
    if row and row[0]:
        ids.add(row[0])
    ids.update(r[0] for r in db.query(UserBranch.branch_id).filter(
        UserBranch.user_id == user_id, UserBranch.company_id == company_id,
    ).all())
    if ids:
        ids = {r[0] for r in db.query(Branch.id).filter(
            Branch.id.in_(list(ids)), Branch.company_id == company_id,
        ).all()}
    if not ids:
        legacy = _legacy_branch_id(db, user)
        if legacy is not None:
            ids = {legacy}
    return sorted(ids)


def company_branch_exists(db: Session, branch_id: int, company_id: Optional[int]) -> bool:
    """Filial shu korxonaniki va faol ekanini tekshiradi."""
    return db.query(Branch.id).filter(
        Branch.id == branch_id,
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
    ).first() is not None


def build_branch_context(db: Session, user, header_branch_id: Optional[int] = None) -> BranchContext:
    """Foydalanuvchi va header bo'yicha kontekstni quradi (dependency'siz ishlatish uchun)."""
    role = _role_of(user)
    company_id = getattr(user, "company_id", None)
    user_id = getattr(user, "id", None)

    # 1. Bypass rollar
    if role in BRANCH_BYPASS_ROLES:
        if role == UserRole.super_admin or header_branch_id is None:
            return BranchContext(None, None, True, False, user_id)
        if not company_branch_exists(db, header_branch_id, company_id):
            raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
        return BranchContext(header_branch_id, None, True, False, user_id)

    # 1b. T2.1: `reports.all_branches` huquqi bor menejer biriktirilgan filialdan qat'i nazar cheklanmaydi
    #     (aylanma import bo'lmasligi uchun funksiya ichida import qilinadi)
    if role == UserRole.manager:
        from app.core.report_scope import user_has_all_branches
        if user_has_all_branches(user):
            if header_branch_id is None:
                return BranchContext(None, None, False, False, user_id)
            if not company_branch_exists(db, header_branch_id, company_id):
                raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
            return BranchContext(header_branch_id, None, False, False, user_id)

    # 2. Biriktirilgan filial(lar): uc.branch_id ∪ user_branches, bo'lmasa legacy users.branch_id (T1.2)
    allowed = assigned_branch_ids(db, user)
    if allowed:
        if header_branch_id is not None:
            if header_branch_id not in allowed:
                raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
            return BranchContext(header_branch_id, frozenset(allowed), False, False, user_id)
        if len(allowed) == 1:
            return BranchContext(allowed[0], frozenset(allowed), False, False, user_id)
        # Bir nechta filial, header yo'q — hammasi birga (faol filial tanlanmagan)
        return BranchContext(None, frozenset(allowed), False, False, user_id)

    # 3. Filial biriktirilmagan
    if role in UNASSIGNED_SEES_ALL_ROLES:
        if header_branch_id is None:
            return BranchContext(None, None, False, False, user_id)
        if not company_branch_exists(db, header_branch_id, company_id):
            raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
        return BranchContext(header_branch_id, None, False, False, user_id)

    active_ids = [r[0] for r in db.query(Branch.id).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).order_by(Branch.id).limit(2).all()]
    if len(active_ids) == 1:
        auto = active_ids[0]
        if header_branch_id is not None and header_branch_id != auto:
            raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        return BranchContext(auto, frozenset({auto}), False, False, user_id)
    if not active_ids:
        if header_branch_id is not None:
            raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
        return BranchContext(None, None, False, False, user_id)
    # 2+ faol filial, xodim biriktirilmagan — hech narsa ko'rmaydi
    if header_branch_id is not None:
        raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
    return BranchContext(None, frozenset(), False, True, user_id)


def get_branch_context(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BranchContext:
    """FastAPI dependency: joriy filial konteksti. `db.info["branch_ctx"]` ga ham yoziladi
    (servislar uchun, `effective_branch_id`). ORM `user` obyekti o'zgartirilmaydi."""
    ctx = build_branch_context(db, current_user, _parse_header(request))
    db.info["branch_ctx"] = ctx
    return ctx


def _explicit_in_scope(ctx: BranchContext, explicit_branch_id: Optional[int]) -> Optional[int]:
    """Aniq `?branch_id=` parametri ruxsat doirasida bo'lsa uni qaytaradi, aks holda None
    (eski xatti-harakat: non-admin uchun parametr e'tiborsiz)."""
    if not explicit_branch_id:
        return None
    if ctx.allowed_branch_ids is None or explicit_branch_id in ctx.allowed_branch_ids:
        return explicit_branch_id
    return None


def apply_branch_scope(q, ctx: BranchContext, branch_col, explicit_branch_id: Optional[int] = None):
    """To'g'ridan-to'g'ri filial ustuni uchun filtr (`Warehouse.branch_id`, `Shift.branch_id`).
    `explicit_branch_id` (so'rov parametri) header'dan ustun — faqat ruxsat doirasida."""
    explicit = _explicit_in_scope(ctx, explicit_branch_id)
    if explicit is not None:
        return q.filter(branch_col == explicit)
    ids = ctx.scope_ids()
    if ids is None:
        return q
    if len(ids) == 1:
        return q.filter(branch_col == next(iter(ids)))
    return q.filter(branch_col.in_(list(ids)))


def _warehouse_ids_subq(branch_ids):
    return select(Warehouse.id).where(Warehouse.branch_id.in_(list(branch_ids))).scalar_subquery()


def apply_warehouse_scope(q, ctx: BranchContext, wh_col, explicit_branch_id: Optional[int] = None):
    """Ombor ustuni uchun filtr (`Sale.warehouse_id`): ombor ruxsat etilgan filiallardan biriniki."""
    explicit = _explicit_in_scope(ctx, explicit_branch_id)
    if explicit is not None:
        return q.filter(wh_col.in_(_warehouse_ids_subq([explicit])))
    ids = ctx.scope_ids()
    if ids is None:
        return q
    return q.filter(wh_col.in_(_warehouse_ids_subq(ids)))


def warehouse_ids_for_ctx(db: Session, ctx: BranchContext) -> Optional[Set[int]]:
    """`branch_wh_set` qurish uchun: `None` — cheklov yo'q, aks holda ombor id'lari to'plami
    (bo'sh bo'lishi mumkin — filialida ombori yo'q xodim)."""
    ids = ctx.scope_ids()
    if ids is None:
        return None
    if not ids:
        return set()
    return {r[0] for r in db.query(Warehouse.id).filter(Warehouse.branch_id.in_(list(ids))).all()}


def effective_branch_ids(db: Session, user) -> FrozenSet[int]:
    """Servislar uchun ruxsat etilgan filiallar to'plami (T1.2): `db.info["branch_ctx"]` dagi
    (shu foydalanuvchi uchun) kontekst doirasi, bo'lmasa joriy korxonadagi biriktirilgan
    filiallar. Bo'sh to'plam — cheklov yo'q yoki biriktirilmagan (chaqiruvchi hal qiladi)."""
    ctx = db.info.get("branch_ctx") if hasattr(db, "info") else None
    if isinstance(ctx, BranchContext) and ctx.user_id == getattr(user, "id", None):
        ids = ctx.scope_ids()
        return frozenset(ids) if ids else frozenset()
    return frozenset(assigned_branch_ids(db, user))


def effective_branch_id(db: Session, user) -> Optional[int]:
    """Servislar uchun joriy filial: `db.info["branch_ctx"]` dagi (shu foydalanuvchi uchun
    qurilgan) kontekstning faol filiali, bo'lmasa joriy korxonadagi asosiy filial
    (`user_companies.branch_id`, legacy `users.branch_id`) — faqat shu korxonaniki bo'lsa."""
    ctx = db.info.get("branch_ctx") if hasattr(db, "info") else None
    if isinstance(ctx, BranchContext) and ctx.user_id == getattr(user, "id", None):
        if ctx.branch_id is not None:
            return ctx.branch_id
        if ctx.allowed_branch_ids is not None and not ctx.allowed_branch_ids:
            return None
    return _own_branch_id(db, user)
