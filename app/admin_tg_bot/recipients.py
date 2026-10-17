"""Admin bot oluvchilari (T3.16): rol, filial va korxona sozlamasi bo'yicha.

`resolve_recipients` — bildirishnoma/hisobot yuboriladigan Telegram ulangan FAOL xodimlar:
  - a'zolik: faol `UserCompany` yozuvi, yoki (eski foydalanuvchi) `user_companies` da shu korxona
    uchun yozuv UMUMAN yo'q va `users.company_id` shu korxona;
  - rol: `UserCompany.role`, bo'lmasa `User.role`; filial: `UserCompany.branch_id`, bo'lmasa `User.branch_id`;
  - admin/director har doim oladi (jadvalli xabarlarda `Company.daily_report_recipients` bilan toraytiriladi);
  - menejer faqat `CompanyBot.notify_branch_managers` yoqilgan, `branch_id` berilgan va menejerning
    filiali mos kelsa oladi;
  - `tg_chat_id` bo'yicha takrorlar olib tashlanadi.
"""
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin_tg_bot.models import CompanyBot
from app.models.company import Company
from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany

# Zudlik bilan yuboriladigan xabarlar (sozlama: CompanyBot.notify_instant_*)
INSTANT_KINDS = ("sale", "finance")
# Jadvalli xabarlar (kunlik hisobot, qarz, muddat): Company.daily_report_recipients ta'sir qiladi
SCHEDULED_KINDS = ("daily_report", "debt", "expiry")

LEADER_ROLES = (UserRole.admin, UserRole.director)
BOT_MEMBER_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)

RECIPIENTS_OWNERS_AND_ADMINS = "owners_and_admins"
RECIPIENTS_OWNERS = "owners"
RECIPIENTS_ALL_MANAGERS = "all_managers"
RECIPIENT_MODES = (RECIPIENTS_OWNERS_AND_ADMINS, RECIPIENTS_OWNERS, RECIPIENTS_ALL_MANAGERS)


def company_members(db: Session, company_id: int, *, with_tg_only: bool = True) -> list:
    """Korxonaning faol xodimlari: `[(User, rol, filial_id)]` (rol/filial korxona bo'yicha)."""
    uc_users = select(UserCompany.user_id).where(UserCompany.company_id == company_id)
    q = db.query(User).filter(
        User.status == UserStatus.active,
        or_(User.company_id == company_id, User.id.in_(uc_users)),
    )
    if with_tg_only:
        q = q.filter(User.tg_chat_id.isnot(None))
    users = q.order_by(User.id).all()
    if not users:
        return []
    ucs = {
        uc.user_id: uc for uc in db.query(UserCompany).filter(
            UserCompany.company_id == company_id, UserCompany.user_id.in_([u.id for u in users]),
        ).all()
    }
    out = []
    for u in users:
        uc = ucs.get(u.id)
        if uc is not None:
            if not uc.is_active:
                continue
            branch = uc.branch_id
            if branch is None and u.company_id == company_id:
                branch = u.branch_id          # T1.2 dan oldingi yozuvlar: users.branch_id
            out.append((u, uc.role or u.role, branch))
        elif u.company_id == company_id:
            out.append((u, u.role, u.branch_id))
    return out


def get_bot_member(db: Session, tg_id: str, company_id: int) -> Optional[tuple]:
    """Telegram id bo'yicha bot korxonasining faol admin/direktor/menejeri: `(User, rol, filial_id)` yoki None."""
    if not tg_id:
        return None
    for u, role, branch in company_members(db, company_id):
        if str(u.tg_chat_id) == str(tg_id) and role in BOT_MEMBER_ROLES:
            return u, role, branch
    return None


def user_member_role(db: Session, user: User, company_id: int) -> Optional[tuple]:
    """Foydalanuvchining shu korxonadagi `(rol, filial_id)` — a'zo bo'lmasa None."""
    for u, role, branch in company_members(db, company_id, with_tg_only=False):
        if u.id == user.id:
            return role, branch
    return None


def resolve_recipients(
    db: Session,
    company_id: int,
    *,
    branch_id: Optional[int] = None,
    kind: str,
    managers_only: bool = False,
) -> list:
    """Xabar oluvchi foydalanuvchilar (takrorlarsiz, `tg_chat_id` bo'yicha).

    `kind`: "sale"/"finance" (zudlik bilan) yoki "daily_report"/"debt"/"expiry" (jadvalli).
    `managers_only=True` — faqat `branch_id` filiali menejerlari (admin/director qo'shilmaydi).
    """
    if kind not in INSTANT_KINDS + SCHEDULED_KINDS:
        raise ValueError(f"Noma'lum xabar turi: {kind}")
    scheduled = kind in SCHEDULED_KINDS

    mode = RECIPIENTS_OWNERS_AND_ADMINS
    if scheduled:
        raw = db.query(Company.daily_report_recipients).filter(Company.id == company_id).scalar()
        mode = raw if raw in RECIPIENT_MODES else RECIPIENTS_OWNERS_AND_ADMINS

    leader_roles = (UserRole.director,) if mode == RECIPIENTS_OWNERS else LEADER_ROLES
    managers_allowed = not scheduled or mode == RECIPIENTS_ALL_MANAGERS
    if managers_allowed and branch_id is not None:
        flag = db.query(CompanyBot.notify_branch_managers).filter(
            CompanyBot.company_id == company_id, CompanyBot.bot_type == "admin",
        ).scalar()
        managers_allowed = flag is not False
    else:
        managers_allowed = False   # filialsiz (butun korxona) xabar menejerga bormaydi

    out, seen = [], set()
    for u, role, member_branch in company_members(db, company_id):
        if role in leader_roles:
            ok = not managers_only
        elif role == UserRole.manager:
            ok = managers_allowed and member_branch is not None and member_branch == branch_id
        else:
            ok = False
        if ok and u.tg_chat_id not in seen:
            seen.add(u.tg_chat_id)
            out.append(u)
    return out
