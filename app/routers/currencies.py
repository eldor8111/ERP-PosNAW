from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from pydantic import BaseModel  # type: ignore
from typing import Optional
from sqlalchemy.orm import Session  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.currency import Currency  # type: ignore

router = APIRouter(prefix="/currencies", tags=["Currencies"])


class CurrencyCreate(BaseModel):
    name: str
    code: str
    rate: float
    is_default: bool = False
    is_active: bool = True


class CurrencyUpdate(BaseModel):
    rate: Optional[float] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    name: Optional[str] = None


class CurrencyResponse(BaseModel):
    id: int
    name: str
    code: str
    rate: float
    is_default: bool
    is_active: Optional[bool] = True

    class Config:
        from_attributes = True


@router.post("/", response_model=CurrencyResponse)
def create_currency(
    data: CurrencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin))
):
    company_id = current_user.company_id if current_user.role != UserRole.super_admin else None
    if data.is_default:
        db.query(Currency).filter(Currency.company_id == company_id).update({"is_default": False})
    new_currency = Currency(
        name=data.name,
        code=data.code,
        rate=data.rate,
        is_default=data.is_default,
        is_active=data.is_active,
        company_id=company_id,
    )
    db.add(new_currency)
    db.commit()
    db.refresh(new_currency)
    return new_currency


@router.get("/", response_model=list[CurrencyResponse])
def get_currencies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(
        UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier, UserRole.super_admin
    ))
):
    q = db.query(Currency)
    q = q.filter(Currency.company_id == current_user.company_id)
    return q.all()


@router.get("/active", response_model=list[CurrencyResponse])
def get_active_currencies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(
        UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier, UserRole.super_admin
    ))
):
    """Faqat faol (is_active=True) valyutalarni qaytaradi."""
    q = db.query(Currency).filter(Currency.is_active == True)
    q = q.filter(Currency.company_id == current_user.company_id)
    return q.all()


@router.patch("/{id}", response_model=CurrencyResponse)
def update_currency(
    id: int,
    data: CurrencyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin))
):
    q = db.query(Currency).filter(Currency.id == id)
    q = q.filter(Currency.company_id == current_user.company_id)
    currency = q.first()
    if not currency:
        raise HTTPException(status_code=404, detail="Valyuta topilmadi")

    if data.rate is not None:
        currency.rate = data.rate
    if data.name is not None:
        currency.name = data.name
    if data.is_active is not None:
        # Asosiy valyutani faolsizlantirish mumkin emas
        if currency.is_default and data.is_active is False:
            raise HTTPException(status_code=400, detail="Asosiy valyutani o'chirib bo'lmaydi")
        currency.is_active = data.is_active
    if data.is_default is True:
        db.query(Currency).filter(Currency.id != id, Currency.company_id == currency.company_id).update({"is_default": False})
        currency.is_default = True
        currency.is_active = True  # Asosiy valyuta har doim faol

    db.commit()
    db.refresh(currency)
    return currency


@router.delete("/{id}")
def delete_currency(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin))
):
    q = db.query(Currency).filter(Currency.id == id)
    q = q.filter(Currency.company_id == current_user.company_id)
    currency = q.first()
    if not currency:
        raise HTTPException(status_code=404, detail="Valyuta topilmadi")
    if currency.is_default:
        raise HTTPException(status_code=400, detail="Asosiy valyutani o'chirib bo'lmaydi")
    db.delete(currency)
    db.commit()
    return {"message": "O'chirildi"}


@router.post("/seed-uzs", response_model=CurrencyResponse)
def seed_uzs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.super_admin))
):
    """UZS asosiy valyuta sifatida har doim mavjud bo'lishini ta'minlaydi."""
    company_id = current_user.company_id if current_user.role != UserRole.super_admin else None
    uzs = db.query(Currency).filter(Currency.code == "UZS", Currency.company_id == company_id).first()
    if uzs:
        return uzs
    has_default = db.query(Currency).filter(Currency.is_default == True, Currency.company_id == company_id).first()
    uzs = Currency(
        name="O'zbek so'mi",
        code="UZS",
        rate=1.0,
        is_default=(not has_default),
        is_active=True,
        company_id=company_id,
    )
    db.add(uzs)
    db.commit()
    db.refresh(uzs)
    return uzs
