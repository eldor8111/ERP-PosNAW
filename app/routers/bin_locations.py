from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.bin_location import BinLocation
from app.models.user import UserRole
from app.models.warehouse import Warehouse
from app.schemas.bin_location import BinLocationCreate, BinLocationOut, BinLocationUpdate

router = APIRouter(prefix="/bin-locations", tags=["BinLocations"])

# products.py dagi WRITE_ROLES bilan bir xil (mahsulotlarni boshqaruvchi rollar)
BIN_WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _require_company(current_user) -> int:
    cid = current_user.company_id
    if not cid:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return cid


def _check_warehouse(db: Session, cid: int, warehouse_id: int) -> None:
    wh = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id,
        Warehouse.company_id == cid,
        Warehouse.is_active == True,
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")


def _find_in_scope(db: Session, cid: int, warehouse_id: Optional[int], code: str, exclude_id: Optional[int] = None):
    """Shu korxona va ombor doirasidagi (warehouse_id NULL = 0) shu kodli qator."""
    q = db.query(BinLocation).filter(
        BinLocation.company_id == cid,
        func.coalesce(BinLocation.warehouse_id, 0) == (warehouse_id or 0),
        BinLocation.code == code,
    )
    if exclude_id is not None:
        q = q.filter(BinLocation.id != exclude_id)
    return q.first()


@router.get("", response_model=List[BinLocationOut])
def list_bin_locations(
    warehouse_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user.company_id:
        return []
    q = db.query(BinLocation).filter(
        BinLocation.company_id == current_user.company_id,
        BinLocation.is_active == True,
    )
    if warehouse_id is not None:
        q = q.filter(BinLocation.warehouse_id == warehouse_id)
    return q.order_by(BinLocation.code).all()


@router.post("", response_model=BinLocationOut)
def create_bin_location(
    data: BinLocationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(*BIN_WRITE_ROLES)),
):
    cid = _require_company(current_user)
    if data.warehouse_id is not None:
        _check_warehouse(db, cid, data.warehouse_id)
    existing = _find_in_scope(db, cid, data.warehouse_id, data.code)
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.label = data.label
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Bu kod allaqachon mavjud")
    bl = BinLocation(
        company_id=cid,
        warehouse_id=data.warehouse_id,
        code=data.code,
        label=data.label,
    )
    db.add(bl)
    db.commit()
    db.refresh(bl)
    return bl


@router.put("/{bl_id}", response_model=BinLocationOut)
def update_bin_location(
    bl_id: int,
    data: BinLocationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(*BIN_WRITE_ROLES)),
):
    cid = _require_company(current_user)
    bl = db.query(BinLocation).filter(
        BinLocation.id == bl_id,
        BinLocation.company_id == cid,
    ).first()
    if not bl:
        raise HTTPException(status_code=404, detail="Joylashuv topilmadi")

    changes = data.model_dump(exclude_none=True)
    # Omborni "barcha omborlar"ga (NULL) qaytarish uchun aniq null yuborish mumkin
    if "warehouse_id" in data.model_fields_set and data.warehouse_id is None:
        changes["warehouse_id"] = None

    new_code = changes.get("code", bl.code)
    new_wh = changes["warehouse_id"] if "warehouse_id" in changes else bl.warehouse_id
    if changes.get("warehouse_id") is not None:
        _check_warehouse(db, cid, changes["warehouse_id"])

    if new_code != bl.code or (new_wh or 0) != (bl.warehouse_id or 0):
        clash = _find_in_scope(db, cid, new_wh, new_code, exclude_id=bl.id)
        if clash:
            if clash.is_active:
                raise HTTPException(status_code=400, detail="Bu kod allaqachon mavjud")
            # Nofaol (o'chirilgan) qator unikal indeksni band qilib turmasin
            db.delete(clash)
            db.flush()

    for k, v in changes.items():
        setattr(bl, k, v)
    db.commit()
    db.refresh(bl)
    return bl


@router.delete("/{bl_id}", status_code=204)
def delete_bin_location(
    bl_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(*BIN_WRITE_ROLES)),
):
    cid = _require_company(current_user)
    bl = db.query(BinLocation).filter(
        BinLocation.id == bl_id,
        BinLocation.company_id == cid,
    ).first()
    if not bl:
        raise HTTPException(status_code=404, detail="Joylashuv topilmadi")
    bl.is_active = False
    db.commit()
