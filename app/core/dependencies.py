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
    if user.role == UserRole.super_admin:
        return  # super_admin hech qachon bloklanmaydi
    if not user.company_id:
        return  # kompaniyasiz foydalanuvchi
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        return
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

    # Multi-company: agar tokenda company_id va role bo'lsa, ularni dinamik override qilamiz
    payload_company_id = payload.get("company_id")
    if payload_company_id is not None:
        user.company_id = int(payload_company_id)
        
    payload_role = payload.get("role")
    if payload_role:
        user.role = UserRole(payload_role)  # type: ignore

    if payload_company_id:
        from app.models.user_company import UserCompany
        uc = db.query(UserCompany).filter(UserCompany.user_id == user.id, UserCompany.company_id == int(payload_company_id)).first()
        if uc and uc.permissions:
            user.permissions = uc.permissions

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
    
    payload_company_id = payload.get("company_id")
    if payload_company_id is not None:
        user.company_id = int(payload_company_id)
        
    payload_role = payload.get("role")
    if payload_role:
        user.role = UserRole(payload_role)  # type: ignore
        
    if payload_company_id:
        from app.models.user_company import UserCompany
        uc = db.query(UserCompany).filter(UserCompany.user_id == user.id, UserCompany.company_id == int(payload_company_id)).first()
        if uc and uc.permissions:
            user.permissions = uc.permissions
        
    return user


def require_roles(*roles: UserRole):
    # Flatten: agar kimdir require_roles([role1, role2]) kabi chaqirsa
    flat_roles = []
    for r in roles:
        if isinstance(r, (list, tuple)):
            flat_roles.extend(r)
        else:
            flat_roles.append(r)

    def checker(current_user: User = Depends(get_current_user)) -> User:
        # super_admin barcha amallardan o'ta oladi
        if current_user.role == UserRole.super_admin:
            return current_user
        if current_user.role not in flat_roles:
            role_names = [r.value if hasattr(r, 'value') else str(r) for r in flat_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu amal uchun ruxsat yo'q. Kerakli rol: {role_names}",
            )
        return current_user

    return checker


def require_permissions(module: str, action: str):
    """
    Yangi granular huquqlarni tekshiruvchi dependency.
    module: masalan 'products', 'sales'
    action: masalan 'view', 'create', 'edit', 'delete'
    """
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role == UserRole.super_admin:
            return current_user

        # user.permissions orqali individual huquqlarni tekshiramiz (e.g. override)
        user_perms = current_user.permissions or {}
        if module in user_perms:
            if user_perms[module].get(action) is True:
                return current_user
            elif user_perms[module].get(action) is False:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sizda ushbu amalni bajarish uchun huquq yo'q (Maxsus cheklov).")

        # Agar individual override bo'lmasa, user.custom_role (dynamic role) dan qaraymiz
        if current_user.custom_role:
            role_perms = current_user.custom_role.permissions or {}
            if role_perms.get(module, {}).get(action) is True:
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Bu amal uchun ruxsat yo'q. Ruxsat etilmagan: {module}.{action}",
        )
    return checker
