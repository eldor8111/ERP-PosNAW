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
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    q = db.query(User).filter(User.status == UserStatus.active)
    q = q.filter(User.company_id == current_user.company_id)
    return q.all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin)),
):
    q = db.query(User).filter(User.id == user_id)
    q = q.filter(User.company_id == current_user.company_id)
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
    existing = db.query(User).filter(
        User.phone == data.phone,
        User.status == UserStatus.active
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Bu telefon raqam allaqachon ro'yxatdan o'tgan")

    company_id = current_user.company_id if current_user.role != UserRole.super_admin else getattr(data, 'company_id', None)
    
    # ── Tarif limit tekshiruvi (inline) ──────────────────────
    if current_user.role != UserRole.super_admin:
        from app.models.company import Company as Co
        from app.models.billing import Tariff as Tf
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

        current_count = (
            db.query(User)
            .filter(
                User.company_id == company_id,
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

    user = User(
        name=data.name,
        phone=data.phone,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
        branch_id=data.branch_id,
        company_id=company_id,
    )
    db.add(user)
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
    q = db.query(User).filter(User.id == user_id)
    q = q.filter(User.company_id == current_user.company_id)
    user = q.first()
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
    if data.status is not None:
        user.status = data.status
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
    q = db.query(User).filter(User.id == user_id)
    q = q.filter(User.company_id == current_user.company_id)
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

    q = db.query(User).filter(User.id == user_id)
    q = q.filter(User.company_id == current_user.company_id)
    user = q.first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

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
