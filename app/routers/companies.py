"""
Companies (Korxonalar) CRUD API
super_admin va admin/director uchun
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore
from pydantic import BaseModel

from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.user import User, UserRole  # type: ignore

router = APIRouter(prefix="/companies", tags=["Companies"])

MANAGE_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director)


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
            branches_count=bc, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username))  # type: ignore[call-arg]
    return result


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
        branches_count=0, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username)  # type: ignore[call-arg]


@router.put("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director)),
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    bc = db.query(func.count(Branch.id)).filter(Branch.company_id == c.id).scalar() or 0
    return CompanyOut(
        id=c.id, name=c.name, address=c.address, phone=c.phone, 
        email=c.email, is_active=c.is_active, created_at=c.created_at, 
        branches_count=bc, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username)  # type: ignore[call-arg]


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
