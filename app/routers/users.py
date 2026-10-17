from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.branch_context import _company_branch_id
from app.core.dependencies import get_current_user, require_roles
from app.core.security import hash_password
from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import UserCreate, UserOut, UserPasswordChange, UserUpdate
from app.services.tenant_guards import validate_branch, validate_role
from app.services.tariff_guard import check_agent_limit, check_courier_limit, check_user_limit

router = APIRouter(prefix="/users", tags=["Users"])

ADMIN_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)

_SHARED_PERSONAL_MSG = (
    "Bu foydalanuvchi bir nechta korxonada ishlaydi. "
    "Shaxsiy ma'lumotlarni faqat o'zi o'zgartira oladi"
)
_SHARED_PASSWORD_MSG = (
    "Bu foydalanuvchi bir nechta korxonada ishlaydi. "
    "Parolni faqat o'zi o'zgartira oladi"
)


def _is_shared_user(db: Session, user: User, company_id) -> bool:
    """Foydalanuvchi `company_id` dan tashqari yana boshqa korxonada ham ishlaydimi (T0.38).

    Bunday foydalanuvchining global maydonlarini (parol, telefon, email, ism, global status)
    faqat o'zi yoki super_admin o'zgartira oladi."""
    from app.models.user_company import UserCompany
    if user.company_id not in (None, company_id):
        return True
    return db.query(UserCompany.id).filter(
        UserCompany.user_id == user.id,
        UserCompany.is_active == True,  # noqa: E712
        UserCompany.company_id != company_id,
    ).first() is not None


def _shared_user_ids(db: Session, users, company_id) -> set:
    """Ro'yxatdagi qaysi foydalanuvchilar boshqa korxonada ham faol (bitta guruhlangan so'rov)."""
    from app.models.user_company import UserCompany
    ids = [u.id for u in users]
    shared = {u.id for u in users if u.company_id not in (None, company_id)}
    if ids:
        rows = db.query(UserCompany.user_id).filter(
            UserCompany.user_id.in_(ids),
            UserCompany.is_active == True,  # noqa: E712
            UserCompany.company_id != company_id,
        ).distinct().all()
        shared.update(r[0] for r in rows)
    return shared


def _norm_phone(v) -> str:
    return (v or "").strip().replace("+", "").replace(" ", "").replace("-", "")


# ── T1.2: filial korxona bo'yicha (user_companies.branch_id ∪ user_branches) ─────────────
# Bu rollar uchun korxonada 2+ faol filial bo'lsa filial majburiy (manager/accountant — ixtiyoriy)
_BRANCH_REQUIRED_ROLES = (UserRole.cashier, UserRole.warehouse, UserRole.agent, UserRole.courier)
_BRANCH_REQUIRED_MSG = "Bu rol uchun filial majburiy"


def _active_branch_count(db: Session, company_id) -> int:
    from app.models.branch import Branch
    return db.query(Branch.id).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).count()


def _require_branch_for_role(db: Session, role, branch_id, branch_ids, company_id) -> None:
    """cashier/warehouse/agent/courier uchun 2+ faol filialli korxonada filial majburiy → 400."""
    if role in _BRANCH_REQUIRED_ROLES and not branch_id and not branch_ids \
            and _active_branch_count(db, company_id) >= 2:
        raise HTTPException(status_code=400, detail=_BRANCH_REQUIRED_MSG)


def _validate_branch_ids(db: Session, branch_ids, company_id, keep_ids=None) -> list:
    """`branch_ids` — takrorsiz, shu korxonaning faol filiallari (T0.9 `validate_branch`, begona → 400).
    `keep_ids` — xodimda allaqachon biriktirilgan filiallar: ular nofaol bo'lsa ham o'tadi
    (forma qayta saqlanganda to'smasin); yangi qo'shilganlar faol bo'lishi shart."""
    keep = set(keep_ids or [])
    out = []
    for bid in branch_ids or []:
        validate_branch(db, bid, company_id, require_active=bid not in keep)
        if bid not in out:
            out.append(bid)
    return out


def _replace_user_branches(db: Session, user_id: int, company_id, branch_ids) -> None:
    """Shu korxona uchun user_branches to'liq almashtiriladi (boshqa korxona qatorlariga tegilmaydi)."""
    from app.models.user_branch import UserBranch
    db.query(UserBranch).filter(
        UserBranch.user_id == user_id, UserBranch.company_id == company_id,
    ).delete(synchronize_session=False)
    for bid in branch_ids:
        db.add(UserBranch(user_id=user_id, company_id=company_id, branch_id=bid))
    db.flush()


def _company_branch_map(db: Session, users, company_id) -> dict:
    """{user_id: (branch_id, [branch_ids])} — joriy korxona bo'yicha. Asosiy filial:
    `uc.branch_id`, bo'lmasa legacy `users.branch_id`; ikkalasi ham faqat shu korxonaniki bo'lsa.
    `branch_ids` = {asosiy} ∪ user_branches (tartiblangan)."""
    from app.models.branch import Branch
    from app.models.user_branch import UserBranch
    from app.models.user_company import UserCompany
    ids = [u.id for u in users]
    if not ids:
        return {}
    uc_branch = {r[0]: r[1] for r in db.query(UserCompany.user_id, UserCompany.branch_id).filter(
        UserCompany.user_id.in_(ids), UserCompany.company_id == company_id,
    ).all()}
    extra = {}
    for uid, bid in db.query(UserBranch.user_id, UserBranch.branch_id).filter(
        UserBranch.user_id.in_(ids), UserBranch.company_id == company_id,
    ).all():
        extra.setdefault(uid, set()).add(bid)
    candidates = set(b for b in uc_branch.values() if b) | set(u.branch_id for u in users if u.branch_id)
    for s in extra.values():
        candidates |= s
    own = set()
    if candidates:
        own = {r[0] for r in db.query(Branch.id).filter(
            Branch.id.in_(list(candidates)), Branch.company_id == company_id,
        ).all()}
    out = {}
    for u in users:
        primary = uc_branch.get(u.id)
        if primary not in own:
            primary = u.branch_id if u.branch_id in own else None
        allowed = {b for b in extra.get(u.id, set()) if b in own}
        if primary:
            allowed.add(primary)
        out[u.id] = (primary, sorted(allowed))
    return out


def _user_out_for_company(db: Session, user: User, company_id, *, is_shared=None, extra=None) -> UserOut:
    """Javob — joriy korxona bo'yicha filial(lar) bilan. ORM obyektiga `branch_id` YOZILMAYDI
    (commit bo'lsa `users.branch_id` ga tushib ketardi) — `UserOut` nusxasi qaytariladi."""
    primary, allowed = _company_branch_map(db, [user], company_id).get(user.id, (None, []))
    update = {"branch_id": primary, "branch_ids": allowed}
    if is_shared is not None:
        update["is_shared"] = is_shared
    if extra:
        update.update(extra)
    return UserOut.model_validate(user).model_copy(update=update)


def _deny_shared(db: Session, request: Request, current_user: User, user: User, detail: str, attempted: dict):
    """Rad etilgan urinishni auditga yozib, 403 qaytaradi (T0.38)."""
    log_action(
        db=db,
        action="USER_SHARED_EDIT_DENIED",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        new_values=attempted,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    raise HTTPException(status_code=403, detail=detail)


@router.get("/", response_model=List[UserOut])
def list_users(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import or_, func
    from app.models.user_company import UserCompany
    from app.models.payme_transaction import PaymeTransaction
    q = db.query(User).filter(User.status.in_([UserStatus.active, UserStatus.pending, UserStatus.inactive]))
    
    uc_exists = db.query(UserCompany).filter(
        UserCompany.user_id == User.id,
        UserCompany.company_id == current_user.company_id,
        UserCompany.is_active == True
    ).exists()

    q = q.filter(
        or_(
            User.company_id == current_user.company_id,
            uc_exists
        )
    )
    users_list = q.all()
    shared_ids = _shared_user_ids(db, users_list, current_user.company_id)
    # T1.2: filial joriy korxona bo'yicha; ORM obyektiga yozilmaydi — UserOut nusxasi
    branch_map = _company_branch_map(db, users_list, current_user.company_id)
    if branch_id is not None:
        # T3.1: filial bo'yicha filtr — korxona filtridan keyin; branch_map faqat shu korxona filiallarini
        # biladi, shuning uchun boshqa korxona filiali so'ralsa ro'yxat bo'sh
        users_list = [
            u for u in users_list
            if branch_map.get(u.id, (None, []))[0] == branch_id or branch_id in branch_map.get(u.id, (None, []))[1]
        ]
    result = []
    for u in users_list:
        primary, allowed = branch_map.get(u.id, (None, []))
        update = {"is_shared": u.id in shared_ids, "branch_id": primary, "branch_ids": allowed}
        if u.role in (UserRole.agent, UserRole.marketplace_agent):
            total_tiyin = db.query(func.sum(PaymeTransaction.amount)).filter(
                PaymeTransaction.account_org_code == u.phone,
                PaymeTransaction.state == 2
            ).scalar()
            if total_tiyin:
                update["paid_amount"] = float(total_tiyin) / 100
        result.append(UserOut.model_validate(u).model_copy(update=update))
    return result


@router.get("/{user_id}/wallets")
def get_user_wallets(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Foydalanuvchiga biriktirilgan kassalar ro'yxati (o'ziniki yoki admin/director — shu korxona xodimi)"""
    from app.services.wallet_access import get_company_user
    if user_id != current_user.id:
        if current_user.role not in (UserRole.admin, UserRole.director):
            raise HTTPException(status_code=403, detail="Bu amal uchun ruxsat yo'q. Kerakli rol: ['admin', 'director']")
        get_company_user(db, user_id, current_user.company_id)
    _sa_text = __import__('sqlalchemy').text
    rows = db.execute(
        _sa_text("SELECT wallet_id, is_default FROM user_wallets WHERE user_id=:uid"),
        {"uid": user_id}
    ).fetchall()
    if not rows:
        return []
    from app.models.moliya import Wallet
    wallet_ids = [int(r[0]) for r in rows]
    defaults = {int(r[0]): bool(r[1]) for r in rows}
    wallets = db.query(Wallet).filter(
        Wallet.id.in_(wallet_ids),
        Wallet.company_id == current_user.company_id
    ).all()
    return [
        {"id": w.id, "name": w.name, "type": w.type,
         "is_default": defaults.get(w.id, False)}
        for w in wallets
    ]


from pydantic import BaseModel as _BaseModel
class _AssignWalletIn(_BaseModel):
    wallet_id: int
    is_default: bool = False


# T0.4: shu korxona kassalaridagi default'larni bekor qilish (bir foydalanuvchi + korxonada bitta default,
# uq_user_wallets_default_per_company partial indeksi bilan mos). Eski (company_id NULL) qatorlar ham
# wallets.company_id orqali qamrab olinadi.
_SQL_DEMOTE_DEFAULTS = """
    UPDATE user_wallets SET is_default = false
    WHERE user_id = :uid AND is_default = true
      AND wallet_id IN (SELECT id FROM wallets WHERE company_id = :cid)
"""
_SQL_UPSERT_USER_WALLET = """
    INSERT INTO user_wallets(user_id, wallet_id, is_default, company_id)
    VALUES(:uid, :wid, :def, :cid)
    ON CONFLICT(user_id, wallet_id) DO UPDATE SET is_default = EXCLUDED.is_default, company_id = EXCLUDED.company_id
"""


@router.post("/{user_id}/wallets", status_code=200)
def assign_wallet_to_user(
    user_id: int,
    data: _AssignWalletIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Foydalanuvchiga kassa biriktirish (admin/director; xodim ham, kassa ham shu korxonadan)"""
    from app.services.wallet_access import get_company_user, get_company_wallet
    _sa_text = __import__('sqlalchemy').text
    cid = current_user.company_id
    target = get_company_user(db, user_id, cid)
    wallet = get_company_wallet(db, data.wallet_id, cid)
    if data.is_default:
        db.execute(_sa_text(_SQL_DEMOTE_DEFAULTS), {"uid": user_id, "cid": cid})
    db.execute(
        _sa_text(_SQL_UPSERT_USER_WALLET),
        {"uid": user_id, "wid": data.wallet_id, "def": data.is_default, "cid": cid}
    )
    db.commit()
    # T1.10: kassa filiali xodim filialiga mos kelmasa — ogohlantirish (biriktirish baribir bajariladi)
    from app.services.wallet_resolver import wallet_branch_warning
    warning = wallet_branch_warning(db, target, wallet)
    return {"ok": True, "warning": warning} if warning else {"ok": True}


@router.delete("/{user_id}/wallets/{wallet_id}", status_code=200)
def remove_wallet_from_user(
    user_id: int,
    wallet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Foydalanuvchidan kassani olib tashlash (admin/director; nofaol kassa ham olib tashlanadi)"""
    from app.services.wallet_access import get_company_user, get_company_wallet
    _sa_text = __import__('sqlalchemy').text
    cid = current_user.company_id
    get_company_user(db, user_id, cid)
    get_company_wallet(db, wallet_id, cid, require_active=False)
    db.execute(
        _sa_text("DELETE FROM user_wallets WHERE user_id=:uid AND wallet_id=:wid"),
        {"uid": user_id, "wid": wallet_id}
    )
    db.commit()
    return {"ok": True}


@router.post("/{user_id}/wallets/{wallet_id}/set-default", status_code=200)
def set_default_wallet(
    user_id: int,
    wallet_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Default kassani o'rnatish (admin/director); shu korxonadagi boshqa default'lar bekor qilinadi"""
    from app.services.wallet_access import get_company_user, get_company_wallet
    _sa_text = __import__('sqlalchemy').text
    cid = current_user.company_id
    target = get_company_user(db, user_id, cid)
    wallet = get_company_wallet(db, wallet_id, cid)
    db.execute(_sa_text(_SQL_DEMOTE_DEFAULTS), {"uid": user_id, "cid": cid})
    db.execute(
        _sa_text(_SQL_UPSERT_USER_WALLET),
        {"uid": user_id, "wid": wallet_id, "def": True, "cid": cid}
    )
    db.commit()
    from app.services.wallet_resolver import wallet_branch_warning
    _warning = wallet_branch_warning(db, target, wallet)
    return {"ok": True, "warning": _warning} if _warning else {"ok": True}


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    from app.models.user_company import UserCompany
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    # Kompaniyaga tegishliligini tekshirish
    if current_user.role != UserRole.super_admin:
        in_company = (
            user.company_id == current_user.company_id or
            db.query(UserCompany).filter(
                UserCompany.user_id == user_id,
                UserCompany.company_id == current_user.company_id,
                UserCompany.is_active == True
            ).first() is not None
        )
        if not in_company:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return _user_out_for_company(
        db, user, current_user.company_id,
        is_shared=user.id in _shared_user_ids(db, [user], current_user.company_id),
    )



@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    company_id = current_user.company_id if current_user.role != UserRole.super_admin else getattr(data, 'company_id', None)

    # Faqat super_admin super_admin huquqi bera oladi — aks holda oddiy admin
    # o'ziga yoki xodimiga platformani boshqaradigan rol berib olishi mumkin edi.
    if data.role == UserRole.super_admin and current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Bu rolni faqat platforma super adminligi bera oladi")

    # T0.9: filial va rol shu korxonaga tegishli bo'lishi shart (begona/mavjud bo'lmasa 400).
    # Mavjud foydalanuvchini boshqa korxonadan qo'shish tarmog'ida ham tekshiriladi (jimgina yutilmasin).
    validate_branch(db, data.branch_id, company_id)
    validate_role(db, data.role_id, company_id)
    # T1.2: qo'shimcha filiallar ham shu korxonaniki; kassir/omborchi/agent/kuryer uchun filial majburiy
    branch_ids = _validate_branch_ids(db, data.branch_ids, company_id)
    _require_branch_for_role(db, data.role, data.branch_id, branch_ids, company_id)

    active_existing = db.query(User).filter(
        User.phone == data.phone,
        User.status == UserStatus.active
    ).first()

    # Agar bu telefon raqami allaqachon boshqa (yoki shu) kompaniyada faol
    # foydalanuvchiga tegishli bo'lsa — uni o'z kompaniyasiga ulash aslida o'sha
    # odamning akkauntini egallab olish bilan teng. Shuning uchun telefon
    # egasi OTP orqali tasdiqlagan bo'lishi kerak (ro'yxatdan o'tishdagi kabi).
    if active_existing and current_user.role != UserRole.super_admin:
        if not data.otp_verified_token:
            raise HTTPException(
                status_code=400,
                detail="Bu telefon raqami allaqachon ro'yxatdan o'tgan. Qo'shish uchun telefon egasi OTP kod bilan tasdiqlashi kerak.",
            )
        from app.core.security import decode_token
        session_data = None
        try:
            session_data = decode_token(data.otp_verified_token)
        except Exception:
            session_data = None
        if not session_data or session_data.get("type") != "otp_verified" or session_data.get("phone") != data.phone:
            raise HTTPException(status_code=400, detail="OTP tasdiqlash tokeni xato yoki muddati o'tgan")

    # Nofaol (o'chirilgan) foydalanuvchi topilsa — uni qayta faollashtirish
    inactive_existing = db.query(User).filter(
        User.phone == data.phone,
        User.status == UserStatus.inactive
    ).first()

    # ── Tarif limit tekshiruvi (T3.5: umumiy yordamchi, 403 + code=TARIFF_LIMIT) ──
    check_user_limit(db, company_id, current_user)
    # T3.9: agent / kuryer rollari uchun alohida kvota (mavjud xodimni UserCompany orqali qo'shish tarmog'i ham shu yerdan o'tadi)
    if current_user.role != UserRole.super_admin:
        if data.role == UserRole.agent:
            check_agent_limit(db, company_id)
        elif data.role == UserRole.courier:
            check_courier_limit(db, company_id)
    # ─────────────────────────────────────────────────────────

    from app.models.user_company import UserCompany
    from sqlalchemy import or_

    if active_existing:
        # Tekshiramiz agar joriy korxonaga ulangan bo'lsa
        already_in_company = db.query(User).outerjoin(UserCompany).filter(
            User.id == active_existing.id,
            or_(
                User.company_id == company_id,
                (UserCompany.company_id == company_id) & (UserCompany.is_active == True)
            )
        ).first()

        if already_in_company:
            raise HTTPException(status_code=400, detail="Foydalanuvchi ushbu korxonada allaqachon mavjud.")

        # Eski asosiy kompaniyasini UserCompany'ga saqlash (qolib ketgan bo'lsa)
        if active_existing.company_id:
            old_uc = db.query(UserCompany).filter(
                UserCompany.user_id == active_existing.id,
                UserCompany.company_id == active_existing.company_id
            ).first()
            if not old_uc:
                db.add(UserCompany(
                    user_id=active_existing.id,
                    company_id=active_existing.company_id,
                    role=active_existing.role,
                    is_active=True
                ))

        # Yangi korxonaga qo'shish (T1.2: filial shu korxona a'zoligida; users.branch_id — asosiy korxonaniki, tegilmaydi)
        new_uc = UserCompany(
            user_id=active_existing.id,
            company_id=company_id,
            role=data.role,
            permissions=data.permissions or {},
            is_active=True,
            branch_id=data.branch_id,
        )
        db.add(new_uc)
        db.flush()
        if branch_ids:
            _replace_user_branches(db, active_existing.id, company_id, branch_ids)
        db.commit()
        db.refresh(active_existing)

        log_action(
            db=db,
            action="ADD_USER_COMPANY",
            entity_type="user",
            entity_id=active_existing.id,
            user_id=current_user.id,
            new_values={"company_id": company_id, "role": data.role.value, "branch_id": data.branch_id},
            ip_address=request.client.host if request.client else None,
        )
        pass  # tg_chat_id set separately if needed

        return _user_out_for_company(
            db, active_existing, company_id,
            is_shared=active_existing.id in _shared_user_ids(db, [active_existing], company_id),
        )

    if inactive_existing:
        # Mavjud nofaol foydalanuvchini yangilash va qayta faollashtirish
        user = inactive_existing
        user.name = data.name
        user.email = data.email
        user.hashed_password = hash_password(data.password)
        user.role = data.role
        user.role_id = getattr(data, 'role_id', None)
        user.permissions = data.permissions or {}
        user.branch_id = data.branch_id
        user.company_id = company_id
        user.status = UserStatus.active

        uc_inactive = db.query(UserCompany).filter(UserCompany.user_id == user.id, UserCompany.company_id == company_id).first()
        if not uc_inactive:
            db.add(UserCompany(user_id=user.id, company_id=company_id, role=data.role, permissions=data.permissions or {},
                               is_active=True, branch_id=data.branch_id))
        else:
            uc_inactive.is_active = True
            uc_inactive.role = data.role
            uc_inactive.permissions = data.permissions or {}
            uc_inactive.branch_id = data.branch_id
    else:
        user = User(
            name=data.name,
            phone=data.phone,
            email=data.email,
            hashed_password=hash_password(data.password),
            role=data.role,
            role_id=data.role_id,
            permissions=data.permissions or {},
            branch_id=data.branch_id,
            company_id=company_id,
            tg_chat_id=None,
        )
        db.add(user)
        db.flush()
        db.add(UserCompany(user_id=user.id, company_id=company_id, role=data.role, permissions=data.permissions or {},
                           is_active=True, branch_id=data.branch_id))

    db.flush()
    # T1.2: qo'shimcha filiallar (yangi/qayta faollashtirilgan xodim uchun shu korxona bo'yicha)
    _replace_user_branches(db, user.id, company_id, branch_ids)

    log_action(
        db=db,
        action="CREATE",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        new_values={"name": user.name, "phone": user.phone, "role": user.role.value},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)

    # Foydalanuvchi yaratildi. OTP tasdiqlash frontend orqali qilinadi.

    return _user_out_for_company(db, user, company_id)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    # Faqat super_admin super_admin huquqi bera oladi (o'ziga ham) — aks holda
    # istalgan admin o'z rolini platforma boshqaruvchisiga ko'tarib olishi mumkin edi.
    if data.role == UserRole.super_admin and current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Bu rolni faqat platforma super adminligi bera oladi")

    from app.models.user_company import UserCompany
    user = db.query(User).filter(User.id == user_id).first()
    if user and current_user.role != UserRole.super_admin:
        in_company = (
            user.company_id == current_user.company_id or
            db.query(UserCompany).filter(
                UserCompany.user_id == user_id,
                UserCompany.company_id == current_user.company_id,
                UserCompany.is_active == True
            ).first() is not None
        )
        if not in_company:
            user = None
    
    uc = None
    if user:
        # T1.2: a'zolik qatori — joriy korxona (super_admin uchun xodimning asosiy korxonasi)
        uc_company_id = user.company_id if current_user.role == UserRole.super_admin else current_user.company_id
        uc = db.query(UserCompany).filter(
            UserCompany.user_id == user.id,
            UserCompany.company_id == uc_company_id
        ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    old = {"name": user.name, "phone": user.phone, "role": user.role.value, "status": user.status.value}
    # T3.4: eski rol o'zgartirishdan OLDIN olinadi (filial majburiyligi rol o'zgarganini aniqlashi uchun)
    old_role = uc.role if uc else user.role
    # T3.9: rol agent/kuryerga o'zgarsa tegishli kvota tekshiriladi (mutatsiyadan oldin; xodimning o'zi sanalmaydi)
    if current_user.role != UserRole.super_admin and data.role is not None and data.role != old_role:
        if data.role == UserRole.agent:
            check_agent_limit(db, uc_company_id, exclude_user_id=user.id)
        elif data.role == UserRole.courier:
            check_courier_limit(db, uc_company_id, exclude_user_id=user.id)

    # T0.38: bir nechta korxonada ishlaydigan foydalanuvchining global maydonlarini
    # boshqa korxona admini o'zgartira olmaydi — faqat o'z korxonasidagi UserCompany.
    shared = (
        current_user.role != UserRole.super_admin
        and user.id != current_user.id
        and _is_shared_user(db, user, current_user.company_id)
    )
    # T1.2: filial joriy korxona bo'yicha (uc.branch_id); users.branch_id faqat asosiy korxona ko'zgusi
    old_primary = _company_branch_map(db, [user], uc_company_id).get(user.id, (None, []))[0]
    branch_field_set = 'branch_id' in data.model_fields_set
    new_branch_id = old_primary
    if shared:
        attempted = data.model_dump(mode='json', exclude_none=True)
        personal_changed = (
            (data.name is not None and data.name.strip() != (user.name or "").strip())
            or (data.phone is not None and _norm_phone(data.phone) != _norm_phone(user.phone))
            or (data.email is not None and (data.email.strip() or None) != (user.email or None))
        )
        if personal_changed:
            _deny_shared(db, request, current_user, user, _SHARED_PERSONAL_MSG, attempted)
        # users.role_id global bitta ustun — boshqa korxona admini o'zgartira olmaydi
        role_id_changed = data.role_id is not None and data.role_id != user.role_id
        if role_id_changed:
            _deny_shared(db, request, current_user, user, _SHARED_PERSONAL_MSG, attempted)
        if branch_field_set and data.branch_id is not None and data.branch_id == user.branch_id \
                and data.branch_id != old_primary \
                and _company_branch_id(db, data.branch_id, uc_company_id) is None:
            # Eski mijoz asosiy korxonaning global filialini qayta yuborgan — bu korxona uchun ma'nosiz, e'tiborsiz
            branch_field_set = False
        if uc is None and (data.role is not None or data.permissions is not None or data.status is not None
                           or branch_field_set or data.branch_ids is not None):
            raise HTTPException(status_code=404, detail="Foydalanuvchi bu korxonada topilmadi")

        # Faqat shu korxona a'zoligi (UserCompany); users.role/permissions/status o'zgarmaydi
        if data.role is not None:
            uc.role = data.role
        if data.permissions is not None:
            uc.permissions = data.permissions
        if data.status is not None:
            uc.is_active = (data.status == UserStatus.active)
    else:
        # T0.9: filial/rol tekshiruvi yozishdan OLDIN.
        if data.role_id is not None:
            validate_role(db, data.role_id, user.company_id)
        if data.name is not None:
            user.name = data.name
        if data.phone is not None:
            user.phone = data.phone
        if data.email is not None:
            user.email = data.email.strip() or None

        if data.role is not None:
            user.role = data.role
            if uc:
                uc.role = data.role
        # role_id: aniq yuborilgan null ham yoziladi (dinamik roldan oddiy rolga o'tish)
        if 'role_id' in data.model_fields_set:
            user.role_id = data.role_id

        if data.permissions is not None:
            user.permissions = data.permissions
            if uc:
                uc.permissions = data.permissions
        if data.status is not None:
            user.status = data.status
            if uc:
                uc.is_active = (data.status == UserStatus.active)

    # ── T1.2: filial(lar) — joriy korxona a'zoligiga; users.branch_id faqat asosiy korxonada ko'zgu ──
    if branch_field_set:
        if data.branch_id is not None:
            # O'zgarmagan (forma qayta saqlanganda) nofaol filial xodimni tahrirlashni to'smasin
            validate_branch(db, data.branch_id, uc_company_id, require_active=data.branch_id != old_primary)
        new_branch_id = data.branch_id
    new_branch_ids = None
    if data.branch_ids is not None:
        cur_ids = _company_branch_map(db, [user], uc_company_id).get(user.id, (None, []))[1]
        new_branch_ids = _validate_branch_ids(db, data.branch_ids, uc_company_id, keep_ids=cur_ids)
    # Filial majburiyligi tahrirda faqat rol yoki filial O'ZGARTIRILGANDA tekshiriladi —
    # mavjud filialsiz xodimning boshqa maydonlari tahriri bloklanmaydi (T1.1 bo'yicha "Filial biriktirilmagan").
    role_changed = data.role is not None and data.role != old_role
    # T3.4: rol o'zgarganda yoki `branch_id` aniq yuborilganda (model_fields_set) tekshiriladi
    if role_changed or branch_field_set:
        eff_role = data.role if data.role is not None else old_role
        eff_ids = new_branch_ids if new_branch_ids is not None else \
            _company_branch_map(db, [user], uc_company_id).get(user.id, (None, []))[1]
        _require_branch_for_role(db, eff_role, new_branch_id, [b for b in eff_ids if b != old_primary], uc_company_id)
    if branch_field_set:
        if uc is not None:
            uc.branch_id = new_branch_id
        if user.company_id in (None, uc_company_id):
            user.branch_id = new_branch_id
    if new_branch_ids is not None:
        _replace_user_branches(db, user.id, uc_company_id, new_branch_ids)
    if branch_field_set:
        _sync_personal_wallet_branch(db, user.id, uc_company_id, new_branch_id)

    log_action(
        db=db,
        action="UPDATE",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        old_values=old,
        new_values=data.model_dump(mode='json', exclude_none=True),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return _user_out_for_company(
        db, user, current_user.company_id if current_user.role != UserRole.super_admin else uc_company_id,
        is_shared=user.id in _shared_user_ids(db, [user], current_user.company_id),
    )


def _sync_personal_wallet_branch(db: Session, user_id: int, company_id, branch_id) -> None:
    """T3.14: xodim filiali o'zgarganda uning shaxsiy "qo'l kassasi" (`UserWallet.is_default`,
    `Wallet.is_personal`) filiali ham yangilanadi; umumiy kassalarga tegilmaydi."""
    from app.models.moliya import Wallet
    from app.models.user import UserWallet
    ids = [r[0] for r in db.query(UserWallet.wallet_id).filter(
        UserWallet.user_id == user_id, UserWallet.is_default == True,  # noqa: E712
    ).all()]
    if not ids:
        return
    db.query(Wallet).filter(
        Wallet.id.in_(ids), Wallet.company_id == company_id, Wallet.is_personal == True,  # noqa: E712
    ).update({"branch_id": branch_id}, synchronize_session=False)


@router.patch("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    user_id: int,
    data: UserPasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    from app.models.user_company import UserCompany
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    if current_user.role != UserRole.super_admin:
        in_company = (
            user.company_id == current_user.company_id or
            db.query(UserCompany).filter(
                UserCompany.user_id == user_id,
                UserCompany.company_id == current_user.company_id,
                UserCompany.is_active == True
            ).first() is not None
        )
        if not in_company:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
        # T0.38: parol global — bir nechta korxonada ishlaydigan foydalanuvchiniki faqat o'zi
        if user.id != current_user.id and _is_shared_user(db, user, current_user.company_id):
            _deny_shared(db, request, current_user, user, _SHARED_PASSWORD_MSG, {"field": "password"})

    user.hashed_password = hash_password(data.new_password)

    log_action(
        db=db,
        action="PASSWORD_CHANGE",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="O'zingizni o'chira olmaysiz")

    from app.models.user_company import UserCompany
    user = db.query(User).filter(User.id == user_id).first()
    if user and current_user.role != UserRole.super_admin:
        in_company = (
            user.company_id == current_user.company_id or
            db.query(UserCompany).filter(
                UserCompany.user_id == user_id,
                UserCompany.company_id == current_user.company_id,
                UserCompany.is_active == True
            ).first() is not None
        )
        if not in_company:
            user = None
    
    uc = None
    if user:
        uc = db.query(UserCompany).filter(
            UserCompany.user_id == user.id,
            UserCompany.company_id == current_user.company_id
        ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    if uc:
        uc.is_active = False

    # Agar boshqa ochiq kompaniyalari qolmagan bo'lsa, butunlay o'chiramiz
    from app.models.user_company import UserCompany
    has_active_comp = db.query(UserCompany).filter(
        UserCompany.user_id == user.id, 
        UserCompany.is_active == True,
        UserCompany.company_id != current_user.company_id
    ).first()
    
    if not has_active_comp:
        user.status = UserStatus.inactive
        # Telegram bog'lanishini uzamiz — o'chirilgan rahbarga hisobot/bildirishnoma ketmasin (T0.16)
        user.tg_chat_id = None

    log_action(
        db=db,
        action="DELETE",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()

@router.post("/{user_id}/unlink-telegram")
def unlink_user_telegram(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Xodimning admin-bot Telegram bog'lanishini uzadi (botda qayta /start + kontakt bilan ulanadi)."""
    from app.models.user_company import UserCompany
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    in_company = (
        target.company_id == current_user.company_id or
        db.query(UserCompany).filter(
            UserCompany.user_id == target.id,
            UserCompany.company_id == current_user.company_id,
            UserCompany.is_active == True
        ).first() is not None
    )
    if not in_company:
        raise HTTPException(status_code=403, detail="Boshqa korxona foydalanuvchisi")
    target.tg_chat_id = None
    db.commit()
    return {"ok": True}


@router.post("/{user_id}/toggle-status")
def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.user_company import UserCompany
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    if current_user.role not in (UserRole.admin, UserRole.director, UserRole.super_admin):
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")

    company_id = current_user.company_id
    uc = db.query(UserCompany).filter(
        UserCompany.user_id == target.id,
        UserCompany.company_id == company_id,
    ).first()
    if current_user.role != UserRole.super_admin and target.company_id != company_id and uc is None:
        raise HTTPException(status_code=403, detail="Boshqa korxona foydalanuvchisi")

    # T0.38: bir nechta korxonada ishlaydigan foydalanuvchi — faqat shu korxona a'zoligi almashadi,
    # global users.status (barcha korxonalardan bloklash) ga tegilmaydi.
    if (
        current_user.role != UserRole.super_admin
        and target.id != current_user.id
        and _is_shared_user(db, target, company_id)
    ):
        if uc is None:
            raise HTTPException(status_code=403, detail="Boshqa korxona foydalanuvchisi")
        uc.is_active = not uc.is_active
        db.commit()
        return {"ok": True, "status": "active" if uc.is_active else "inactive"}

    if target.status == UserStatus.active:
        target.status = UserStatus.inactive
    else:
        target.status = UserStatus.active
    db.commit()
    return {"ok": True, "status": target.status.value}


@router.post("/{user_id}/activate-trial")
def activate_user_trial(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Faqat Super Admin uchun: Agent yoki xodimga probniy (sinov) muddatini yoqib berish."""
    if current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Sinov (probniy) muddatini faqat Super Admin yoqishi mumkin")
        
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
        
    from datetime import datetime, timezone, timedelta
    target.is_trial = True
    target.status = UserStatus.active
    target.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=days)
    db.commit()
    return {
        "ok": True,
        "detail": f"{target.name} uchun {days} kunlik sinov muddati yoqildi",
        "subscription_ends_at": target.subscription_ends_at.isoformat() if target.subscription_ends_at else None,
        "is_trial": True,
        "status": target.status.value,
    }

