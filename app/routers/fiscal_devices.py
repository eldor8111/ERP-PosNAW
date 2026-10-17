"""T3.18: fiskal qurilmalar (Hippo `factory_id`) — filial/kassaga serverda biriktirish.

Avval `factory_id` faqat brauzer localStorage'ida turardi va server uni hech narsaga bog'lamasdi.
Endi admin/direktor qurilmani filialga (va ixtiyoriy kassaga) biriktiradi; kassir `/mine` dan faqat
o'z filiali qurilmalarini ko'radi; `PATCH /sales/{id}/fiscal` va (yoqilgan bo'lsa) `/hippo/*` shu
ro'yxat bo'yicha tekshiriladi."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.branch_context import build_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.fiscal_device import FiscalDevice
from app.models.moliya import Wallet
from app.models.user import User, UserRole

router = APIRouter(prefix="/fiscal-devices", tags=["Fiscal devices"])

ADMIN_ROLES = (UserRole.admin, UserRole.director)
POS_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier)

DEVICE_NOT_FOUND = "Fiskal qurilma topilmadi"
FACTORY_FORBIDDEN = "Bu fiskal modul sizning korxonangiz/filialingizga biriktirilmagan"
FACTORY_DUPLICATE = "Bu fiskal modul korxonada allaqachon ro'yxatdan o'tgan"


class FiscalDeviceIn(BaseModel):
    factory_id: str = Field(..., min_length=1, max_length=64)
    branch_id: Optional[int] = None
    wallet_id: Optional[int] = None
    label: Optional[str] = Field(None, max_length=100)
    is_active: bool = True


class FiscalDeviceUpdate(BaseModel):
    factory_id: Optional[str] = Field(None, min_length=1, max_length=64)
    branch_id: Optional[int] = None   # model_fields_set da bo'lsa o'zgaradi (None = butun korxona)
    wallet_id: Optional[int] = None   # model_fields_set da bo'lsa o'zgaradi (None = kassa biriktirilmagan)
    label: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class FiscalDeviceOut(BaseModel):
    id: int
    factory_id: str
    branch_id: Optional[int] = None
    wallet_id: Optional[int] = None
    label: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


def _require_company(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def _check_branch(db: Session, cid: int, branch_id: Optional[int]) -> None:
    """Filial shu korxonaga tegishli bo'lishi shart — aks holda 404 (begona filial sizib chiqmaydi)."""
    if branch_id is None:
        return
    if not db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first():
        raise HTTPException(status_code=404, detail="Filial topilmadi")


def _check_wallet(db: Session, cid: int, wallet_id: Optional[int]) -> None:
    if wallet_id is None:
        return
    if not db.query(Wallet.id).filter(Wallet.id == wallet_id, Wallet.company_id == cid).first():
        raise HTTPException(status_code=404, detail="Kassa topilmadi")


def _get_own(db: Session, cid: int, device_id: int) -> FiscalDevice:
    dev = db.query(FiscalDevice).filter(FiscalDevice.id == device_id, FiscalDevice.company_id == cid).first()
    if not dev:
        raise HTTPException(status_code=404, detail=DEVICE_NOT_FOUND)
    return dev


# ── Boshqa routerlar/servislar uchun yordamchilar ─────────────────────────────

def company_has_active_devices(db: Session, company_id: int) -> bool:
    """Korxonada kamida bitta faol fiskal qurilma ro'yxatdan o'tganmi (bo'sh registr — tekshiruv yo'q)."""
    return db.query(FiscalDevice.id).filter(
        FiscalDevice.company_id == company_id, FiscalDevice.is_active == True,  # noqa: E712
    ).first() is not None


def device_allowed_for_branch(db: Session, company_id: int, factory_id: str, branch_id: Optional[int]) -> bool:
    """`factory_id` korxonaning faol qurilmasi va `branch_id` filialida (yoki butun korxonada) ishlatilishi mumkinmi."""
    q = db.query(FiscalDevice.id).filter(
        FiscalDevice.company_id == company_id,
        FiscalDevice.factory_id == factory_id,
        FiscalDevice.is_active == True,  # noqa: E712
    )
    if branch_id is not None:
        q = q.filter(or_(FiscalDevice.branch_id.is_(None), FiscalDevice.branch_id == branch_id))
    else:
        q = q.filter(FiscalDevice.branch_id.is_(None))
    return q.first() is not None


def user_device_query(db: Session, user: User):
    """Foydalanuvchi ko'ra oladigan faol qurilmalar: o'z korxonasi, o'z filiali(lari) yoki butun korxona."""
    q = db.query(FiscalDevice).filter(
        FiscalDevice.company_id == user.company_id, FiscalDevice.is_active == True,  # noqa: E712
    )
    ids = build_branch_context(db, user, None).scope_ids()
    if ids is not None:
        q = q.filter(or_(FiscalDevice.branch_id.is_(None), FiscalDevice.branch_id.in_(list(ids))))
    return q


def allowed_factory_ids(db: Session, user: User) -> Optional[set]:
    """Foydalanuvchi ishlata oladigan `factory_id` lar; super_admin uchun None (cheklanmagan)."""
    if user.role == UserRole.super_admin:
        return None
    return {d.factory_id for d in user_device_query(db, user).all()}


def ensure_factory_access(db: Session, user: User, factory_id: str) -> None:
    """`/hippo/*`: `factory_id` foydalanuvchi korxonasi/filialidagi faol qurilma bo'lishi shart, aks holda 403."""
    if user.role == UserRole.super_admin:
        return
    fid = (factory_id or "").strip()
    if not fid or fid not in allowed_factory_ids(db, user):
        raise HTTPException(status_code=403, detail=FACTORY_FORBIDDEN)


def fiscal_device_for_user(
    factory_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> str:
    """FastAPI dependency: yo'l/so'rov parametridagi `factory_id` ni tekshiradi va qaytaradi."""
    ensure_factory_access(db, user, factory_id)
    return factory_id


# ── Endpointlar ───────────────────────────────────────────────────────────────

@router.get("/mine", response_model=List[FiscalDeviceOut])
def my_fiscal_devices(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POS_ROLES)),
):
    """Kassir uchun: faqat o'z filiali (va butun korxonaga ochiq) faol qurilmalar."""
    _require_company(user)
    return user_device_query(db, user).order_by(FiscalDevice.label, FiscalDevice.id).all()


@router.get("", response_model=List[FiscalDeviceOut])
def list_fiscal_devices(
    branch_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    q = db.query(FiscalDevice).filter(FiscalDevice.company_id == cid)
    if branch_id is not None:
        _check_branch(db, cid, branch_id)
        q = q.filter(FiscalDevice.branch_id == branch_id)
    return q.order_by(FiscalDevice.id).all()


@router.post("", response_model=FiscalDeviceOut, status_code=201)
def create_fiscal_device(
    data: FiscalDeviceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    factory_id = data.factory_id.strip()
    if not factory_id:
        raise HTTPException(status_code=422, detail="factory_id bo'sh bo'lmasin")
    _check_branch(db, cid, data.branch_id)
    _check_wallet(db, cid, data.wallet_id)
    if db.query(FiscalDevice.id).filter(FiscalDevice.company_id == cid, FiscalDevice.factory_id == factory_id).first():
        raise HTTPException(status_code=409, detail=FACTORY_DUPLICATE)
    dev = FiscalDevice(
        company_id=cid, branch_id=data.branch_id, wallet_id=data.wallet_id,
        factory_id=factory_id, label=(data.label or "").strip() or None, is_active=data.is_active,
    )
    db.add(dev)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=FACTORY_DUPLICATE)
    db.refresh(dev)
    return dev


@router.put("/{device_id}", response_model=FiscalDeviceOut)
def update_fiscal_device(
    device_id: int,
    data: FiscalDeviceUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    dev = _get_own(db, cid, device_id)
    fields = data.model_fields_set
    if "factory_id" in fields and data.factory_id is not None:
        fid = data.factory_id.strip()
        if not fid:
            raise HTTPException(status_code=422, detail="factory_id bo'sh bo'lmasin")
        if fid != dev.factory_id:
            if db.query(FiscalDevice.id).filter(
                FiscalDevice.company_id == cid, FiscalDevice.factory_id == fid, FiscalDevice.id != dev.id,
            ).first():
                raise HTTPException(status_code=409, detail=FACTORY_DUPLICATE)
            dev.factory_id = fid
    if "branch_id" in fields:
        _check_branch(db, cid, data.branch_id)
        dev.branch_id = data.branch_id
    if "wallet_id" in fields:
        _check_wallet(db, cid, data.wallet_id)
        dev.wallet_id = data.wallet_id
    if "label" in fields:
        dev.label = (data.label or "").strip() or None
    if "is_active" in fields and data.is_active is not None:
        dev.is_active = data.is_active
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=FACTORY_DUPLICATE)
    db.refresh(dev)
    return dev


@router.delete("/{device_id}")
def delete_fiscal_device(
    device_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    dev = _get_own(db, cid, device_id)
    db.delete(dev)
    db.commit()
    return {"ok": True}
