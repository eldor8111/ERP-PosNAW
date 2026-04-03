"""
Tarif cheklovlarini tekshirish uchun yordamchi funksiyalar.
Har bir korxona o'zining faol tarifiga mos holda foydalanishi mumkin.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.billing import Tariff
from app.models.branch import Branch
from app.models.user import User, UserRole, UserStatus


# Super Admin va tarifi bo'lmagan korxonalar uchun standart cheklovlar
_DEFAULT_MAX_BRANCHES = 1
_DEFAULT_MAX_USERS    = 5


def _get_active_tariff(company: Company) -> Tariff | None:
    """Korxonaning hozirda faol tarifini qaytaradi."""
    if not company or not company.tariff:
        return None
    sub_ends = company.subscription_ends_at
    if sub_ends is None:
        return None
    if sub_ends.tzinfo is None:
        sub_ends = sub_ends.replace(tzinfo=timezone.utc)
    if sub_ends < datetime.now(timezone.utc):
        return None          # muddati o'tgan
    return company.tariff


def check_branch_limit(db: Session, company_id: int, acting_user: User) -> None:
    """
    Yangi filial qo'shishdan oldin chaqiriladi.
    Agar tarif limiti to'lgan bo'lsa, 403 xatolik chiqaradi.
    Super Admin uchun hech qanday cheklov yo'q.
    """
    if acting_user.role == UserRole.super_admin:
        return

    company = db.query(Company).filter(Company.id == company_id).first()
    tariff  = _get_active_tariff(company)

    max_branches = tariff.max_branches if tariff else _DEFAULT_MAX_BRANCHES

    current = (
        db.query(Branch)
        .filter(Branch.company_id == company_id, Branch.is_active == True)
        .count()
    )

    if current >= max_branches:
        tariff_name = tariff.name if tariff else "Sinov"
        raise HTTPException(
            status_code=403,
            detail=(
                f"'{tariff_name}' tarifi bo'yicha maksimal filiallar soni: {max_branches}. "
                f"Hozir: {current}. Tarif yangilang yoki administrator bilan bog'laning."
            ),
        )


def check_user_limit(db: Session, company_id: int, acting_user: User) -> None:
    """
    Yangi xodim qo'shishdan oldin chaqiriladi.
    Super Admin uchun hech qanday cheklov yo'q.
    """
    if acting_user.role == UserRole.super_admin:
        return

    company = db.query(Company).filter(Company.id == company_id).first()
    tariff  = _get_active_tariff(company)

    max_users = tariff.max_users if tariff else _DEFAULT_MAX_USERS

    current = (
        db.query(User)
        .filter(
            User.company_id == company_id,
            User.status != UserStatus.inactive,
            User.role != UserRole.super_admin,
        )
        .count()
    )

    if current >= max_users:
        tariff_name = tariff.name if tariff else "Sinov"
        raise HTTPException(
            status_code=403,
            detail=(
                f"'{tariff_name}' tarifi bo'yicha maksimal xodimlar soni: {max_users}. "
                f"Hozir: {current}. Tarif yangilang yoki administrator bilan bog'laning."
            ),
        )
