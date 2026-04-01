from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.warehouse import WarehouseCreate, WarehouseOut, WarehouseUpdate

router = APIRouter(prefix="/warehouses", tags=["Warehouses"])

ADMIN_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)


@router.get("", response_model=List[WarehouseOut])
def list_warehouses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Warehouse).filter(Warehouse.is_active == True)
    q = q.filter(Warehouse.company_id == current_user.company_id)
    if current_user.branch_id:
        q = q.filter(Warehouse.branch_id == current_user.branch_id)
    return q.all()


@router.post("", response_model=WarehouseOut)
def create_warehouse(
    data: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    wh = Warehouse(**data.model_dump())
    if current_user.role != UserRole.super_admin:
        wh.company_id = current_user.company_id
    db.add(wh)
    db.commit()
    db.refresh(wh)
    log_action(db, "CREATE", "warehouse", wh.id, user_id=current_user.id, new_values={"name": wh.name})
    db.commit()
    return wh


@router.get("/{wh_id}", response_model=WarehouseOut)
def get_warehouse(
    wh_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Warehouse).filter(Warehouse.id == wh_id)
    q = q.filter(Warehouse.company_id == current_user.company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    return wh


@router.patch("/{wh_id}", response_model=WarehouseOut)
def update_warehouse(
    wh_id: int,
    data: WarehouseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    q = db.query(Warehouse).filter(Warehouse.id == wh_id)
    q = q.filter(Warehouse.company_id == current_user.company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(wh, field, value)
    db.commit()
    db.refresh(wh)
    return wh


@router.delete("/{wh_id}", status_code=204)
def delete_warehouse(
    wh_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    q = db.query(Warehouse).filter(Warehouse.id == wh_id)
    q = q.filter(Warehouse.company_id == current_user.company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    wh.is_active = False
    db.commit()
