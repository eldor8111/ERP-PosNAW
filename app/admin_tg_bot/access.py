"""Admin bot uchun korxona a'zoligi tekshiruvi (T0.16).

Bot har bir so'rovda foydalanuvchini faqat tg_chat_id bo'yicha emas, balki
BOT KORXONASINING faol admin/direktori ekanini tekshirib topadi. Hisobot va
bildirishnoma oluvchilar ham shu shart bilan tanlanadi — o'chirilgan,
bloklangan yoki a'zoligi tugagan rahbarlarga xabar ketmaydi.
"""
from sqlalchemy import and_, exists, not_, or_
from sqlalchemy.orm import Session

from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany

ADMIN_BOT_ROLES = (UserRole.admin, UserRole.director)


def _admin_member_clause(company_id: int):
    """SQLAlchemy sharti: User faol VA bot korxonasida admin/direktor.

    A — user_companies da faol (is_active) admin/direktor yozuvi bor;
    B — user_companies da shu korxona uchun yozuv UMUMAN yo'q (eski foydalanuvchi),
        lekin users.company_id shu korxona va users.role admin/direktor.
    is_active=False yozuv bo'lsa A ham, B ham o'tmaydi.
    """
    uc_active_admin = exists().where(and_(
        UserCompany.user_id == User.id,
        UserCompany.company_id == company_id,
        UserCompany.is_active == True,
        UserCompany.role.in_(ADMIN_BOT_ROLES),
    ))
    uc_any = exists().where(and_(
        UserCompany.user_id == User.id,
        UserCompany.company_id == company_id,
    ))
    legacy = and_(
        User.company_id == company_id,
        User.role.in_(ADMIN_BOT_ROLES),
        not_(uc_any),
    )
    return and_(User.status == UserStatus.active, or_(uc_active_admin, legacy))


def get_company_admin_by_tg_id(db: Session, tg_id: str, company_id: int) -> User | None:
    """Telegram id bo'yicha bot korxonasining faol admin/direktorini qaytaradi (bo'lmasa None)."""
    if not tg_id:
        return None
    return db.query(User).filter(
        User.tg_chat_id == str(tg_id),
        _admin_member_clause(company_id),
    ).first()


def get_report_recipients(db: Session, company_id: int) -> list[User]:
    """Hisobot/bildirishnoma oluvchilar: korxonaning Telegram ulangan faol admin/direktorlari."""
    return db.query(User).filter(
        User.tg_chat_id.isnot(None),
        _admin_member_clause(company_id),
    ).all()
