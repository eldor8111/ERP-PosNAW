from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator
from typing import List, Optional

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
    branch_id: Optional[int] = None

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v):
        return _validate_phone(v)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    branch_id: Optional[int] = None


class UserPasswordChange(BaseModel):
    new_password: str


class UserOut(BaseModel):
    id: int
    name: str
    phone: str
    email: Optional[str]
    role: UserRole
    status: UserStatus
    branch_id: Optional[int] = None
    company_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


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

