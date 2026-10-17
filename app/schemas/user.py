from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, EmailStr, field_validator, model_validator

from app.models.user import UserRole, UserStatus


def _validate_phone(v: str) -> str:
    clean = v.strip().replace("+", "").replace(" ", "").replace("-", "")
    if not clean.isdigit() or not (7 <= len(clean) <= 15):
        raise ValueError("Telefon raqam noto'g'ri (faqat raqamlar, 7-15 ta belgi)")
    return clean  # + belgisi va probellarsiz saqlash


class UserCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    password: str
    role: UserRole = UserRole.cashier
    role_id: Optional[int] = None
    permissions: Optional[Dict[str, Any]] = {}
    branch_id: Optional[int] = None
    # T1.2: qo'shimcha filiallar (manager/accountant uchun bir nechta filial)
    branch_ids: Optional[List[int]] = None
    otp_verified_token: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v):
        return _validate_phone(v)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None
    role_id: Optional[int] = None
    permissions: Optional[Dict[str, Any]] = None
    branch_id: Optional[int] = None
    # T1.2: berilsa shu korxona uchun user_branches to'liq almashtiriladi
    branch_ids: Optional[List[int]] = None
    status: Optional[UserStatus] = None


class UserPasswordChange(BaseModel):
    new_password: str


class UserOut(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    role: UserRole
    role_id: Optional[int] = None
    permissions: Optional[Dict[str, Any]] = {}
    status: UserStatus
    branch_id: Optional[int] = None
    # T1.2: joriy korxona bo'yicha ruxsat etilgan filiallar (uc.branch_id ∪ user_branches)
    branch_ids: List[int] = []
    company_id: Optional[int] = None
    created_at: Optional[datetime] = None
    subscription_ends_at: Optional[datetime] = None
    is_trial: Optional[bool] = False
    paid_amount: Optional[float] = 0
    # Foydalanuvchi bir nechta korxonada ishlaydi (T0.38): shaxsiy maydonlarni faqat o'zi o'zgartiradi
    is_shared: bool = False
    # Telegram bog'langanmi (T0.16): tg_chat_id ning o'zi chiqarilmaydi, faqat belgisi
    tg_linked: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _set_tg_linked(cls, data):
        # ORM obyekti (model_validate) yoki dict — ikkalasida ham tg_chat_id dan hisoblanadi
        if isinstance(data, dict):
            if "tg_linked" not in data and data.get("tg_chat_id") is not None:
                return {**data, "tg_linked": True}
            return data
        if isinstance(data, BaseModel) or not hasattr(data, "tg_chat_id"):
            return data
        # ORM obyekti o'zgartirilmaydi — maydonlar dict ga ko'chiriladi
        values = {f: getattr(data, f) for f in cls.model_fields if hasattr(data, f)}
        if "tg_linked" not in values:
            values["tg_linked"] = getattr(data, "tg_chat_id", None) is not None
        return values


class LoginRequest(BaseModel):
    phone: str
    password: str


class UserCompanyOut(BaseModel):
    company_id: int
    company_name: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserOut] = None
    companies: Optional[List[UserCompanyOut]] = None
    needs_company_selection: bool = False
    temp_token: Optional[str] = None


class RefreshRequest(BaseModel):
    refresh_token: str

