from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import get_current_user, require_roles
from app.core.security import hash_password
from app.database import get_db
from app.models.user import User, UserRole, UserStatus
from app.schemas.user import UserCreate, UserOut, UserPasswordChange, UserUpdate
from app.utils.tariff_check import check_user_limit

router = APIRouter(prefix="/users", tags=["Users"])

ADMIN_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)


@router.get("/", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import or_
    from app.models.user_company import UserCompany
    q = db.query(User).outerjoin(UserCompany).filter(User.status == UserStatus.active)
    q = q.filter(
        or_(
            User.company_id == current_user.company_id,
            (UserCompany.company_id == current_user.company_id) & (UserCompany.is_active == True)
        )
    ).distinct()
    return q.all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    from sqlalchemy import or_
    from app.models.user_company import UserCompany
    q = db.query(User).outerjoin(UserCompany).filter(User.id == user_id)
    q = q.filter(
        or_(
            User.company_id == current_user.company_id,
            (UserCompany.company_id == current_user.company_id) & (UserCompany.is_active == True)
        )
    ).distinct()
    user = q.first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    return user


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    company_id = current_user.company_id if current_user.role != UserRole.super_admin else getattr(data, 'company_id', None)

    from app.routers.auth import _get_otp_bot_token, _find_chat_id_by_phone
    bot_token = _get_otp_bot_token()
    is_dev_mode = not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE"

    if not is_dev_mode:
        if not data.otp_verified_token:
            raise HTTPException(status_code=400, detail="Telegram OTP tasdiqlash talab qilinadi")
        from app.core.security import decode_token
        token_data = decode_token(data.otp_verified_token)
        if not token_data or token_data.get("type") != "otp_verified":
            raise HTTPException(status_code=400, detail="OTP token noto'g'ri yoki muddati o'tgan")
        if token_data.get("phone") != data.phone:
            raise HTTPException(status_code=400, detail="OTP token bu telefon uchun emas")

    active_existing = db.query(User).filter(
        User.phone == data.phone,
        User.status == UserStatus.active
    ).first()

    # Nofaol (o'chirilgan) foydalanuvchi topilsa — uni qayta faollashtirish
    inactive_existing = db.query(User).filter(
        User.phone == data.phone,
        User.status == UserStatus.inactive
    ).first()

    # ── Tarif limit tekshiruvi (inline) ──────────────────────
    # Faqat yangi foydalanuvchi qo'shilayotganda tekshiramiz
    # (mavjud faol foydalanuvchi boshqa korxonaga qo'shilayotganda tekshirmaymiz)
    is_existing_user = active_existing or inactive_existing
    if current_user.role != UserRole.super_admin and not (active_existing):
        from app.models.company import Company as Co
        from app.models.billing import Tariff as Tf
        from app.models.user_company import UserCompany as UCt
        from datetime import datetime, timezone

        co = db.query(Co).filter(Co.id == company_id).first()
        max_usr = 5  # default
        if co and co.tariff:
            sub_end = co.subscription_ends_at
            if sub_end:
                if sub_end.tzinfo is None:
                    sub_end = sub_end.replace(tzinfo=timezone.utc)
                if sub_end > datetime.now(timezone.utc):
                    max_usr = co.tariff.max_users or 5

        # UserCompany jadvalidan hisoblash — to'g'ri count
        current_count = (
            db.query(UCt)
            .join(User, User.id == UCt.user_id)
            .filter(
                UCt.company_id == company_id,
                UCt.is_active == True,
                User.status != UserStatus.inactive,
                User.role != UserRole.super_admin,
            )
            .count()
        )
        if current_count >= max_usr:
            tariff_name = co.tariff.name if (co and co.tariff) else "Sinov"
            raise HTTPException(
                status_code=403,
                detail=(
                    f"'{tariff_name}' tarifi bo'yicha maksimal xodimlar soni: {max_usr}. "
                    f"Hozir: {current_count}. Tarif yangilang yoki administrator bilan bog'laning."
                ),
            )
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

        # Yangi korxonaga qo'shish
        new_uc = UserCompany(
            user_id=active_existing.id,
            company_id=company_id,
            role=data.role,
            is_active=True
        )
        db.add(new_uc)
        db.commit()
        db.refresh(active_existing)

        log_action(
            db=db,
            action="ADD_USER_COMPANY",
            entity_type="user",
            entity_id=active_existing.id,
            user_id=current_user.id,
            new_values={"company_id": company_id, "role": data.role.value},
            ip_address=request.client.host if request.client else None,
        )
        if not active_existing.tg_chat_id:
            reg_chat_id = _find_chat_id_by_phone(data.phone) if not is_dev_mode else None
            if reg_chat_id:
                active_existing.tg_chat_id = reg_chat_id

        return active_existing

    if inactive_existing:
        # Mavjud nofaol foydalanuvchini yangilash va qayta faollashtirish
        user = inactive_existing
        user.name = data.name
        user.email = data.email
        user.hashed_password = hash_password(data.password)
        user.role = data.role
        user.branch_id = data.branch_id
        user.company_id = company_id
        user.status = UserStatus.active

        if not user.tg_chat_id:
            reg_chat_id = _find_chat_id_by_phone(data.phone) if not is_dev_mode else None
            if reg_chat_id:
                user.tg_chat_id = reg_chat_id

        uc_inactive = db.query(UserCompany).filter(UserCompany.user_id == user.id, UserCompany.company_id == company_id).first()
        if not uc_inactive:
            db.add(UserCompany(user_id=user.id, company_id=company_id, role=data.role, is_active=True))
        else:
            uc_inactive.is_active = True
            uc_inactive.role = data.role
    else:
        user = User(
            name=data.name,
            phone=data.phone,
            email=data.email,
            hashed_password=hash_password(data.password),
            role=data.role,
            branch_id=data.branch_id,
            company_id=company_id,
            tg_chat_id=_find_chat_id_by_phone(data.phone) if not is_dev_mode else None,
        )
        db.add(user)
        db.flush()
        db.add(UserCompany(user_id=user.id, company_id=company_id, role=data.role, is_active=True))

    db.flush()

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
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    from sqlalchemy import or_
    from app.models.user_company import UserCompany
    q = db.query(User).outerjoin(UserCompany).filter(User.id == user_id)
    q = q.filter(
        or_(
            User.company_id == current_user.company_id,
            (UserCompany.company_id == current_user.company_id) & (UserCompany.is_active == True)
        )
    ).distinct()
    user = q.first()
    
    uc = None
    if user:
        uc = db.query(UserCompany).filter(
            UserCompany.user_id == user.id,
            UserCompany.company_id == current_user.company_id
        ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    old = {"name": user.name, "phone": user.phone, "role": user.role.value, "status": user.status.value}

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
    if data.status is not None:
        user.status = data.status
        if uc:
            uc.is_active = (data.status == UserStatus.active)
    if data.branch_id is not None:
        user.branch_id = data.branch_id
    elif 'branch_id' in data.model_fields_set:
        user.branch_id = None

    log_action(
        db=db,
        action="UPDATE",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        old_values=old,
        new_values=data.model_dump(exclude_none=True),
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    user_id: int,
    data: UserPasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    from sqlalchemy import or_
    from app.models.user_company import UserCompany
    q = db.query(User).outerjoin(UserCompany).filter(User.id == user_id)
    q = q.filter(
        or_(
            User.company_id == current_user.company_id,
            (UserCompany.company_id == current_user.company_id) & (UserCompany.is_active == True)
        )
    ).distinct()
    user = q.first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

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

    from sqlalchemy import or_
    from app.models.user_company import UserCompany
    q = db.query(User).outerjoin(UserCompany).filter(User.id == user_id)
    q = q.filter(
        or_(
            User.company_id == current_user.company_id,
            (UserCompany.company_id == current_user.company_id) & (UserCompany.is_active == True)
        )
    ).distinct()
    user = q.first()
    
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

    log_action(
        db=db,
        action="DELETE",
        entity_type="user",
        entity_id=user.id,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
