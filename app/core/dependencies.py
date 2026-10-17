from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, joinedload

from app.core.security import decode_token, find_api_key, touch_api_key
from app.database import get_db
from app.models.company import Company
from app.models.user import MOBILE_ONLY_ROLES, User, UserRole, UserStatus

bearer_scheme = HTTPBearer()
# Authorization sarlavhasi bo'lmasa ham so'rov o'tadi (X-API-Key bilan kiruvchi endpointlar uchun)
optional_bearer = HTTPBearer(auto_error=False)

# Kuryer/agent tokeni faqat shu yo'llarda ishlaydi — qolgan admin API'lar
# (moliya, hisobotlar, to'liq mijozlar ro'yxati...) ularga yopiq.
MOBILE_ALLOWED_PREFIXES = ("/api/mobile/",)


def _enforce_mobile_boundary(user: User, payload: dict, request: Request, db: Session) -> None:
    dev_id = payload.get("dev")
    if dev_id is not None:
        from app.models.mobile_device import MobileDevice
        device = db.query(MobileDevice).filter(
            MobileDevice.id == int(dev_id), MobileDevice.user_id == user.id,
        ).first()
        if not device or device.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Qurilma sessiyasi bekor qilingan")
    if user.role in MOBILE_ONLY_ROLES:
        if dev_id is None or not request.url.path.startswith(MOBILE_ALLOWED_PREFIXES):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bu bo'lim mobil xodimlar uchun yopiq")


def _check_company_subscription(user: User, db: Session) -> None:
    """Foydalanuvchining kompaniyasi obuna muddatini tekshiradi. Super admin tekshirilmaydi."""
    if user.role == UserRole.super_admin:
        return  # super_admin hech qachon bloklanmaydi
    if not user.company_id:
        return  # kompaniyasiz foydalanuvchi
    company = db.query(Company).filter(Company.id == user.company_id).first()
    if not company:
        return
    # T1.12: qo'lda bloklangan korxona (qat'iy `is False` — NULL/True o'tadi). Billing endpointlari
    # `get_current_user_allow_expired` ni ishlatadi (u bu funksiyani chaqirmaydi) — to'lov sahifasi ochiq qoladi.
    if company.is_active is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Korxona bloklangan")
    _check_subscription_end(company)


def assert_company_active(db: Session, company_id: int) -> Company:
    """API kalit orqali kirishda: korxona mavjud, faol va obunasi tugamagan bo'lishi shart
    (403 — nofaol/yo'q korxona, 402 — obuna tugagan)."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company or company.is_active is False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Korxona faol emas")
    _check_subscription_end(company)
    return company


def _check_subscription_end(company: Company) -> None:
    if company.subscription_ends_at:
        ends_at = company.subscription_ends_at
        if ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        if ends_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=402,
                detail="Obuna muddati tugagan. Iltimos to'lov qiling yoki admin bilan bog'laning.",
            )


def _load_context_user(db: Session, payload: dict) -> User:
    """Token bo'yicha foydalanuvchini yuklab, korxona/rol/huquq kontekstini qo'llaydi.

    MUHIM: token qiymatlari (company_id/role/permissions) ORM obyektiga yoziladi, shuning
    uchun obyekt AVVAL sessiyadan ajratiladi (expunge). Aks holda so'rovdagi har qanday
    db.commit() ularni `users` jadvaliga UPDATE qilib yuborardi (ko'p korxonali
    foydalanuvchining global roli/korxonasi buzilardi). Foydalanuvchini o'zgartirish
    kerak bo'lsa — db.query(User).get(current_user.id) dan olinadi.
    """
    from app.models.user_company import UserCompany

    user = (
        db.query(User)
        .options(joinedload(User.custom_role))
        .filter(User.id == int(payload["sub"]), User.status == UserStatus.active)
        .first()
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Foydalanuvchi topilmadi")

    # Detached obyekt commit() da expire bo'lmaydi va UPDATE yaratmaydi.
    # custom_role yuqorida joinedload bilan yuklangan (DetachedInstanceError bo'lmaydi).
    db.expunge(user)

    payload_company_id = payload.get("company_id")
    payload_role = payload.get("role")
    effective_role = None

    if payload_company_id is not None:
        cid = int(payload_company_id)
        uc = db.query(UserCompany).filter(
            UserCompany.user_id == user.id,
            UserCompany.company_id == cid,
            UserCompany.is_active == True,  # noqa: E712
        ).first()
        if uc is None:
            # Faol a'zolik yo'q: bekor qilingan a'zolik yoki begona korxona -> 401.
            # Faqat user_companies qatori umuman yo'q eski/bot yaratgan foydalanuvchi
            # o'z asosiy korxonasida ishlashda davom etadi.
            revoked = db.query(UserCompany.id).filter(
                UserCompany.user_id == user.id, UserCompany.company_id == cid,
            ).first()
            if revoked is not None or cid != user.company_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Korxonaga a'zolik bekor qilingan",
                )
        user.company_id = cid
        if uc is not None:
            effective_role = uc.role
            if uc.permissions:
                user.permissions = uc.permissions

    if effective_role is None and payload_role:
        effective_role = UserRole(payload_role)
    if effective_role is not None:
        user.role = effective_role  # type: ignore

    return user


def get_current_user(
    request: Request,
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

    user = _load_context_user(db, payload)

    _enforce_mobile_boundary(user, payload, request, db)
    _check_company_subscription(user, db)

    return user


def get_current_user_allow_expired(
    request: Request,
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
        
    user = _load_context_user(db, payload)

    _enforce_mobile_boundary(user, payload, request, db)
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


def require_roles_allow_expired(*roles: UserRole):
    """`require_roles` bilan bir xil rol tekshiruvi, lekin `get_current_user_allow_expired` ustiga
    qurilgan: obuna muddati tugagan bo'lsa ham o'tkazadi (T2.1: `/finance/cash-balance`).
    super_admin barcha amallardan o'tadi."""
    flat_roles = []
    for r in roles:
        if isinstance(r, (list, tuple)):
            flat_roles.extend(r)
        else:
            flat_roles.append(r)

    def checker(current_user: User = Depends(get_current_user_allow_expired)) -> User:
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


def require_module_roles(module: str, *roles: UserRole):
    """Rol bo'yicha default + permissions deny-override.

    Avval `require_roles(*roles)`; keyin super_admin bo'lmagan foydalanuvchida
    `permissions[module] is False` bo'lsa — 403 (frontend tekis {kalit: bool} formati).
    """
    role_checker = require_roles(*roles)

    def checker(current_user: User = Depends(role_checker)) -> User:
        if current_user.role == UserRole.super_admin:
            return current_user
        perms = current_user.permissions or {}
        if isinstance(perms, dict) and perms.get(module) is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu bo'limga ruxsat berilmagan (maxsus cheklov)",
            )
        return current_user

    return checker


def company_scope_by_key_or_roles(*roles: UserRole):
    """Korxona ID (int) qaytaradi: yoki `X-API-Key` (faqat o'z korxonasi, faqat o'qish endpointlari uchun),
    yoki `Authorization: Bearer` (foydalanuvchi roli `roles` dan yoki super_admin).

    X-API-Key berilgan bo'lsa — FALLBACK YO'Q: kalit yaroqsiz bo'lsa yaroqli JWT bo'lsa ham 403.
    Hech narsa berilmasa — 401. Kalit boshqa endpointlarda ishlamaydi (ular get_current_user/JWT talab qiladi).
    """
    flat_roles = []
    for r in roles:
        if isinstance(r, (list, tuple)):
            flat_roles.extend(r)
        else:
            flat_roles.append(r)

    def checker(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        db: Session = Depends(get_db),
    ) -> int:
        if x_api_key:
            rec = find_api_key(db, x_api_key)
            assert_company_active(db, rec.company_id)
            touch_api_key(db, rec)
            return rec.company_id
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autentifikatsiya talab qilinadi")
        user = get_current_user(request, credentials, db)
        if user.role != UserRole.super_admin and user.role not in flat_roles:
            role_names = [r.value if hasattr(r, 'value') else str(r) for r in flat_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bu amal uchun ruxsat yo'q. Kerakli rol: {role_names}",
            )
        return user.company_id

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
