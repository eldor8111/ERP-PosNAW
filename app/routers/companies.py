"""
Companies (Korxonalar) CRUD API
super_admin va admin/director uchun
"""
from datetime import datetime
from typing import List, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore
from pydantic import BaseModel

from app.config import settings  # type: ignore
from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.user import User, UserRole  # type: ignore

router = APIRouter(prefix="/companies", tags=["Companies"])

MANAGE_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director)


def _telegram_setup_bot(token: str, webhook_url: str) -> str:
    """Token tekshiradi, bot username oladi, webhook o'rnatadi. Bot username qaytaradi."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = r.json()
            if not data.get("ok"):
                raise HTTPException(status_code=400, detail="Bot tokeni noto'g'ri yoki bot mavjud emas!")
            bot_username = data["result"].get("username", "")
            client.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
            )
            return bot_username
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Telegram API bilan bog'lanishda xatolik: {e}")


def _telegram_delete_webhook(token: str) -> None:
    """Webhookni o'chiradi (bot uzilganda)."""
    try:
        with httpx.Client(timeout=10) as client:
            client.post(f"https://api.telegram.org/bot{token}/deleteWebhook")
    except Exception:
        pass


class CompanyCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    tg_bot_token: Optional[str] = None
    tg_bot_username: Optional[str] = None


class ReceiptTemplatesUpdate(BaseModel):
    receipt_templates: dict

class CompanyOut(BaseModel):
    id: int
    name: str
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    created_at: datetime
    branches_count: int = 0
    tg_bot_token: Optional[str] = None
    tg_bot_username: Optional[str] = None
    receipt_templates: Optional[dict] = None

    class Config:
        from_attributes = True


@router.get("", response_model=List[CompanyOut])
def list_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.super_admin:
        companies = db.query(Company).order_by(Company.id).all()
    else:
        companies = db.query(Company).filter(Company.id == current_user.company_id).order_by(Company.id).all()
        
    result = []
    for c in companies:
        bc = db.query(func.count(Branch.id)).filter(Branch.company_id == c.id).scalar() or 0
        result.append(CompanyOut(
            id=c.id, name=c.name, address=c.address, phone=c.phone, 
            email=c.email, is_active=c.is_active, created_at=c.created_at, 
            branches_count=bc, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username, receipt_templates=c.receipt_templates))  # type: ignore[call-arg]
    return result

@router.get("/me/receipt_templates")
def get_my_receipt_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        return {"receipt_templates": {}}
    try:
        c = db.query(Company).filter(Company.id == current_user.company_id).first()
        if not c:
            return {"receipt_templates": {}}
        return {"receipt_templates": c.receipt_templates or {}}
    except Exception:
        return {"receipt_templates": {}}

@router.put("/me/receipt_templates")
def update_my_receipt_templates(
    data: ReceiptTemplatesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyangiz topilmadi")
    c = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
    c.receipt_templates = data.receipt_templates
    db.commit()
    return {"ok": True, "receipt_templates": c.receipt_templates}

@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director)),
):
    c = Company(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return CompanyOut(
        id=c.id, name=c.name, address=c.address, phone=c.phone, 
        email=c.email, is_active=c.is_active, created_at=c.created_at, 
        branches_count=0, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username, receipt_templates=c.receipt_templates)  # type: ignore[call-arg]


@router.put("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    data: CompanyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director)),
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    update_data = data.model_dump(exclude_unset=True)

    if "tg_bot_token" in update_data:
        new_token = update_data["tg_bot_token"]
        if new_token:
            base_url = settings.SERVER_URL.rstrip("/") if settings.SERVER_URL else str(request.base_url).rstrip("/")
            webhook_url = f"{base_url}/api/telegram/webhook/{new_token}"
            bot_username = _telegram_setup_bot(new_token, webhook_url)
            update_data["tg_bot_username"] = bot_username
        else:
            if c.tg_bot_token:
                _telegram_delete_webhook(c.tg_bot_token)
            update_data["tg_bot_username"] = None

    for k, v in update_data.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    bc = db.query(func.count(Branch.id)).filter(Branch.company_id == c.id).scalar() or 0
    return CompanyOut(
        id=c.id, name=c.name, address=c.address, phone=c.phone,
        email=c.email, is_active=c.is_active, created_at=c.created_at,
        branches_count=bc, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username, receipt_templates=c.receipt_templates)  # type: ignore[call-arg]


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin)),
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    db.delete(c)
    db.commit()
