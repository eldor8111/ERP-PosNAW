"""Ombor ro'yxatlari va filial chegarasi tekshiruvi (T1.3).

  - `list_company_warehouses` — `GET /warehouses` va `GET /inventory/warehouses` uchun yagona ro'yxat:
    `scope=context` (joriy filial konteksti, T1.1) yoki `scope=all` (korxonaning barcha omborlari —
    faqat admin/director/super_admin/manager/warehouse; transfer maqsadi va boshqaruv sahifalari uchun).
  - `assert_warehouse_branch_access` — yozish amallarida (kirim, transfer manbasi, xarid) ombor
    ruxsat etilgan filialda ekanini tekshiradi. Bypass rollar (admin/director/super_admin) va
    cheklanmagan kontekst uchun tekshiruv o'tkazib yuboriladi; transfer MAQSADI esa istalgan
    korxona ombori bo'lishi mumkin (`as_transfer_target=True`).
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.branch_context import (
    BRANCH_FORBIDDEN, BRANCH_NOT_FOUND, BranchContext, apply_branch_scope, build_branch_context,
)
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse

# `scope=all` ruxsati: admin/director/super_admin + transfer bilan ishlaydigan manager/warehouse
ALL_SCOPE_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin, UserRole.manager, UserRole.warehouse)

ALL_SCOPE_FORBIDDEN = "Barcha omborlarni ko'rish ruxsati yo'q"
WAREHOUSE_BRANCH_FORBIDDEN = "Bu ombor sizning filialingizga tegishli emas"


def _role_of(user) -> Optional[UserRole]:
    role = getattr(user, "role", None)
    if isinstance(role, UserRole):
        return role
    try:
        return UserRole(role)
    except (ValueError, TypeError):
        return None


def resolve_ctx(db: Session, user, ctx: Optional[BranchContext] = None) -> BranchContext:
    """Servislar uchun filial konteksti: berilgan `ctx`, bo'lmasa `db.info["branch_ctx"]`
    (shu foydalanuvchi uchun), bo'lmasa header'siz qurilgan kontekst."""
    if isinstance(ctx, BranchContext):
        return ctx
    cached = db.info.get("branch_ctx") if hasattr(db, "info") else None
    if isinstance(cached, BranchContext) and cached.user_id == getattr(user, "id", None):
        return cached
    return build_branch_context(db, user)


def list_company_warehouses(
    db: Session,
    user: User,
    ctx: BranchContext,
    *,
    scope: str = "context",
    branch_id: Optional[int] = None,
    include_inactive: bool = False,
) -> List[Warehouse]:
    """Korxona omborlari (filial nomi bilan, `joinedload(Warehouse.branch)`).

    - `scope="context"` (standart): joriy filial konteksti — bypass rollar header'siz hammasini,
      qolganlar ruxsat etilgan filiallarni ko'radi;
    - `scope="all"`: korxonaning barcha omborlari; ruxsatsiz rol uchun 403;
    - `branch_id`: shu filial omborlari; begona korxona filiali — 404, non-bypass uchun ruxsatsiz
      filial (`scope=context`) — 403;
    - `include_inactive`: nofaol omborlar ham qaytariladi.
    """
    if scope not in ("context", "all"):
        raise HTTPException(status_code=422, detail="scope 'context' yoki 'all' bo'lishi kerak")
    if scope == "all" and _role_of(user) not in ALL_SCOPE_ROLES:
        raise HTTPException(status_code=403, detail=ALL_SCOPE_FORBIDDEN)

    if branch_id is not None:
        exists = db.query(Branch.id).filter(
            Branch.id == branch_id, Branch.company_id == user.company_id,
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
        if scope == "context":
            ids = ctx.scope_ids()
            if ids is not None and branch_id not in ids:
                raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)

    q = db.query(Warehouse).options(joinedload(Warehouse.branch)).filter(
        Warehouse.company_id == user.company_id,
    )
    if not include_inactive:
        q = q.filter(Warehouse.is_active == True)  # noqa: E712
    if branch_id is not None:
        q = q.filter(Warehouse.branch_id == branch_id)
    elif scope == "context":
        q = apply_branch_scope(q, ctx, Warehouse.branch_id)
    return q.order_by(Warehouse.name, Warehouse.id).all()


def assert_warehouse_branch_access(
    db: Session,
    user: User,
    ctx: Optional[BranchContext],
    warehouse_id: int,
    *,
    as_transfer_target: bool = False,
) -> Warehouse:
    """Ombor korxonaniki (aks holda 404) va non-bypass xodim uchun ruxsat etilgan filialda
    (aks holda 403 "Bu ombor sizning filialingizga tegishli emas") ekanini tekshiradi.
    Bypass rol, cheklanmagan kontekst va transfer maqsadi ombori uchun filial tekshirilmaydi.
    Omborning faolligi tekshirilmaydi — buni chaqiruvchi hal qiladi."""
    q = db.query(Warehouse).filter(Warehouse.id == warehouse_id)
    if _role_of(user) != UserRole.super_admin:
        q = q.filter(Warehouse.company_id == user.company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    if as_transfer_target:
        return wh
    ctx = resolve_ctx(db, user, ctx)
    if ctx.bypass:
        return wh
    ids = ctx.scope_ids()
    if ids is not None and wh.branch_id not in ids:
        raise HTTPException(status_code=403, detail=WAREHOUSE_BRANCH_FORBIDDEN)
    return wh
