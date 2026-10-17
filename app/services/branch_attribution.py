"""Pul operatsiyasi filialini aniqlash — yagona qoida (T2.2).

`resolve_money_branch_id` xarajat, qo'lda kiritilgan tranzaksiya, qarz to'lovi, sotuv tranzaksiyasi va
AI amallari uchun BIR XIL tartibda filial tanlaydi, shuning uchun P&L da tushum, xarajat va boshqa kirim
bitta filialga tushadi. `0` yoki "tartibsiz birinchi filial" hech qachon qaytarilmaydi.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.branch import Branch
from app.models.warehouse import Warehouse

NO_BRANCH = "Korxonada filial yo'q"
NO_ACTIVE_BRANCH = "Faol filial topilmadi"


def _own_active_branch(db: Session, branch_id: Optional[int], company_id: Optional[int]) -> Optional[int]:
    """Filial shu korxonaniki va faol bo'lsa id si, aks holda None."""
    if not branch_id or company_id is None:
        return None
    row = db.query(Branch.id).filter(
        Branch.id == branch_id,
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
    ).first()
    return row[0] if row else None


def _warehouse_branch(db: Session, warehouse_id: Optional[int], company_id: Optional[int]) -> Optional[int]:
    """Ombor filiali (ombor ham, filial ham faqat shu korxonaniki va faol)."""
    if not warehouse_id:
        return None
    row = db.query(Warehouse.branch_id).filter(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id,
    ).first()
    return _own_active_branch(db, row[0] if row else None, company_id)


def resolve_money_branch_id(
    db: Session,
    user,
    *,
    wallet=None,
    warehouse_id: Optional[int] = None,
    explicit_branch_id: Optional[int] = None,
    check_user_branch_active: bool = False,
) -> int:
    """Pul/sotuv yozuvining filialini aniqlaydi.

    Tartib:
      1. `explicit_branch_id` — korxonaga tekshiriladi (begona/mavjud emas bo'lsa 400 "Filial topilmadi");
      2. sotuv bilan bog'liq chaqiruvda (`warehouse_id` berilgan) ombor filiali, pul operatsiyasida
         (`wallet` berilgan) kassa filiali; ikkalasi ham berilsa avval ombor, so'ng kassa;
      3. foydalanuvchining joriy filiali (T1.2 `effective_branch_id`, faqat shu korxonaniki);
      4. korxonaning asosiy filiali, bo'lmasa `ORDER BY id` bo'yicha birinchi FAOL filial.
    Hech biri topilmasa HTTPException(400); `0` qaytarilmaydi.
    `check_user_branch_active=True` — foydalanuvchi filiali yopilgan bo'lsa 409 (sotuv yo'li, T1.12).
    """
    from app.core.branch_context import effective_branch_id
    from app.services.branch_helpers import fallback_active_branch_id
    from app.services.wallet_access import get_company_branch

    company_id = getattr(user, "company_id", None)

    if explicit_branch_id:
        return get_company_branch(db, explicit_branch_id, company_id).id

    found = _warehouse_branch(db, warehouse_id, company_id)
    if found:
        return found
    if wallet is not None:
        found = _own_active_branch(db, getattr(wallet, "branch_id", None), company_id)
        if found:
            return found

    eff = effective_branch_id(db, user)
    if eff:
        if check_user_branch_active:
            from app.services.sale_helpers import assert_user_branch_active
            assert_user_branch_active(db, user)
        return eff

    found = fallback_active_branch_id(db, user)
    if found:
        return found

    has_any = db.query(Branch.id).filter(Branch.company_id == company_id).first() if company_id is not None else None
    raise HTTPException(status_code=400, detail=NO_ACTIVE_BRANCH if has_any else NO_BRANCH)
