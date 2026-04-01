import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status  # type: ignore
from pydantic import BaseModel  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.core.audit import log_action  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.core.security import (  # type: ignore
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db  # type: ignore
from app.models.agent import Agent  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.currency import Currency  # type: ignore
from app.models.user import User, UserRole, UserStatus  # type: ignore
from app.schemas.user import LoginRequest, RefreshRequest, TokenResponse, UserOut  # type: ignore

router = APIRouter(prefix="/auth", tags=["Auth"])


def _generate_org_code(db: Session) -> str:
    while True:
        code = str(random.randint(10000000, 99999999))
        exists = db.query(Company).filter(Company.org_code == code).first()
        if not exists:
            return code
    raise RuntimeError("unreachable")  # type: ignore[unreachable]  # for static analysis


class AgentCodeCheck(BaseModel):
    code: str


@router.post("/check-agent-code")
def check_agent_code(data: AgentCodeCheck, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(
        Agent.code == data.code.strip().upper(),
        Agent.is_active == True
    ).first()
    if agent:
        return {"valid": True, "agent_name": agent.name}
    return {"valid": False, "agent_name": None}


class CompanyRegisterRequest(BaseModel):
    company_name: str
    name: str
    phone: str
    region: str
    district: str
    password: str
    agent_code: Optional[str] = None


@router.post("/register", status_code=201)
def register_company(data: CompanyRegisterRequest, db: Session = Depends(get_db)):
    # Telefon normalizatsiya
    data.phone = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    # Telefon tekshirish
    existing_user = db.query(User).filter(User.phone == data.phone).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Bu telefon raqam allaqachon ro'yxatdan o'tgan")

    # Korxona nomi tekshirish
    existing_company = db.query(Company).filter(Company.name == data.company_name).first()
    if existing_company:
        raise HTTPException(status_code=400, detail="Bu korxona nomi allaqachon mavjud")

    # Agent kodi tekshirish
    agent_id = None
    agent_name = None
    if data.agent_code:
        code_val = str(data.agent_code).strip().upper()
        agent = db.query(Agent).filter(
            Agent.code == code_val,
            Agent.is_active == True
        ).first()
        if not agent:
            raise HTTPException(status_code=400, detail="Agent kodi topilmadi yoki faol emas")
        agent_id = agent.id
        agent_name = agent.name

    # Org code yaratish
    org_code = _generate_org_code(db)

    # Korxona yaratish
    company = Company(
        name=data.company_name,
        org_code=org_code,
        region=data.region,
        district=data.district,
        phone=data.phone,
        is_active=True,
        agent_id=agent_id,
    )
    db.add(company)
    db.flush()  # company.id olish uchun

    # Asosiy filial yaratish
    branch = Branch(
        name=f"{data.company_name} (Asosiy)",
        company_id=company.id,
        is_active=True,
    )
    db.add(branch)
    db.flush()

    # Admin foydalanuvchi yaratish
    user = User(
        name=data.name,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role=UserRole.admin,
        branch_id=branch.id,
        company_id=company.id,
        status=UserStatus.active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Birlamchi UZS valyutasini yaratish (agar mavjud bo'lmasa)
    existing_currency = db.query(Currency).filter(
        Currency.company_id == company.id,
        Currency.code == "UZS"
    ).first()
    if not existing_currency:
        default_currency = Currency(
            name="O'zbek so'mi",
            code="UZS",
            rate=1.0,
            is_default=True,
            is_active=True,
            company_id=company.id,
        )
        db.add(default_currency)
        db.commit()

    # Token yaratish (avtomatik login)
    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "org_code": org_code,
        "company_name": company.name,
        "user": UserOut.model_validate(user),
    }


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    try:
        normalized_phone = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
        user = db.query(User).filter(User.phone == normalized_phone, User.status == UserStatus.active).first()

        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Telefon yoki parol noto'g'ri",
            )

        access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        log_action(
            db=db,
            action="LOGIN",
            entity_type="user",
            entity_id=user.id,
            user_id=user.id,
            ip_address=request.client.host if request.client else None,
        )
        db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserOut.model_validate(user),
        )
    except HTTPException:
        raise
    except Exception:
        import traceback
        print("LOGIN ERROR TRACEBACK:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token yaroqsiz")

    user = db.query(User).filter(User.id == int(payload["sub"]), User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Foydalanuvchi topilmadi")

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_refresh_token = create_refresh_token({"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# In-memory reset token store: {token: {"phone": str, "expires": datetime}}
_reset_tokens: dict = {}


class CheckPhoneRequest(BaseModel):
    phone: str


class ResetPasswordRequest(BaseModel):
    phone: str
    reset_token: str
    new_password: str


@router.post("/check-phone")
def check_phone(data: CheckPhoneRequest, db: Session = Depends(get_db)):
    """Telefon bazada borligini tekshiradi va reset token qaytaradi"""
    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    user = db.query(User).filter(User.phone == normalized, User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=404, detail="Bu telefon raqam tizimda topilmadi")
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    _reset_tokens[token] = {"phone": normalized, "expires": expires}
    return {"exists": True, "name": user.name, "reset_token": token}


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Telefon raqam va reset token orqali parolni tiklash"""
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak")
    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    token_data = _reset_tokens.get(data.reset_token)
    if not token_data:
        raise HTTPException(status_code=400, detail="Reset token noto'g'ri yoki muddati o'tgan")
    if token_data["phone"] != normalized:
        raise HTTPException(status_code=400, detail="Reset token bu telefon raqam uchun emas")
    if datetime.now(timezone.utc) > token_data["expires"]:
        del _reset_tokens[data.reset_token]
        raise HTTPException(status_code=400, detail="Reset token muddati tugagan, qaytadan so'rang")
    user = db.query(User).filter(User.phone == normalized, User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=404, detail="Bu telefon raqam tizimda topilmadi")
    user.hashed_password = hash_password(data.new_password)
    db.commit()
    del _reset_tokens[data.reset_token]
    return {"message": "Parol muvaffaqiyatli yangilandi"}
