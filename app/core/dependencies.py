from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.database import get_db
from app.models.company import Company
from app.models.user import User, UserRole, UserStatus

bearer_scheme = HTTPBearer()


def _check_company_subscription(user: User, db: Session) -> None:
    """Foydalanuvchining kompaniyasi obuna muddatini tekshiradi. Super admin tekshirilmaydi."""
    if not user.company_id:
        return  # super_admin yoki kompaniyasiz foydalanuvchi
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        return
    if not company.is_active:
        raise HTTPException(status_code=402, detail="Kompaniya bloklangan. Iltimos admin bilan bog'laning.")
    if company.subscription_ends_at:
        ends_at = company.subscription_ends_at
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        if ends_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=402,
                detail="Obuna muddati tugagan. Iltimos to'lov qiling yoki admin bilan bog'laning.",
            )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token yaroqsiz yoki muddati o'tgan",
        )

    user_id: int = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token noto'g'ri")

    user = db.query(User).filter(User.id == int(user_id), User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Foydalanuvchi topilmadi")

    _check_company_subscription(user, db)

    return user


def get_current_user_allow_expired(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """get_current_user kabi, lekin obuna muddati tugagan bo'lsa ham o'tkazadi.
    Billing sahifalari uchun ishlatiladi."""
    token = credentials.credentials
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token yaroqsiz yoki muddati o'tgan")
    user_id: int = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token noto'g'ri")
    user = db.query(User).filter(User.id == int(user_id), User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Foydalanuvchi topilmadi")
    return user


def require_roles(*roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        # super_admin barcha amallardan o'ta oladi
        if current_user.role == UserRole.super_admin:
            return current_user
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu amal uchun ruxsat yo'q. Kerakli rol: {[r.value for r in roles]}",
            )
        return current_user

    return checker
