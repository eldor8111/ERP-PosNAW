from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.bin_location import BinLocation
from app.schemas.bin_location import BinLocationCreate, BinLocationOut, BinLocationUpdate

router = APIRouter(prefix="/bin-locations", tags=["BinLocations"])


@router.get("", response_model=List[BinLocationOut])
def list_bin_locations(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return (
        db.query(BinLocation)
        .filter(BinLocation.is_active == True)
        .order_by(BinLocation.code)
        .all()
    )


@router.post("", response_model=BinLocationOut)
def create_bin_location(
    data: BinLocationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    existing = db.query(BinLocation).filter(BinLocation.code == data.code).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.label = data.label
            db.commit()
            db.refresh(existing)
            return existing
        raise HTTPException(status_code=400, detail="Bu kod allaqachon mavjud")
    bl = BinLocation(**data.model_dump())
    db.add(bl)
    db.commit()
    db.refresh(bl)
    return bl


@router.put("/{bl_id}", response_model=BinLocationOut)
def update_bin_location(
    bl_id: int,
    data: BinLocationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    bl = db.query(BinLocation).filter(BinLocation.id == bl_id).first()
    if not bl:
        raise HTTPException(status_code=404, detail="Joylashuv topilmadi")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(bl, k, v)
    db.commit()
    db.refresh(bl)
    return bl


@router.delete("/{bl_id}", status_code=204)
def delete_bin_location(
    bl_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    bl = db.query(BinLocation).filter(BinLocation.id == bl_id).first()
    if not bl:
        raise HTTPException(status_code=404, detail="Joylashuv topilmadi")
    bl.is_active = False
    db.commit()
