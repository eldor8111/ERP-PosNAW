from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.core.audit import log_action  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.database import get_db  # type: ignore
from app.models.supplier import Supplier  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.schemas.supplier import SupplierCreate, SupplierOut, SupplierUpdate  # type: ignore

router = APIRouter(prefix="/suppliers", tags=["Suppliers"])

ALLOWED = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)


@router.get("", response_model=List[SupplierOut])
def list_suppliers(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.is_active == True)
    q = q.filter(Supplier.company_id == current_user.company_id)
    if search:
        q = q.filter(Supplier.name.ilike(f"%{search}%"))
    return q.offset(skip).limit(limit).all()


@router.post("", response_model=SupplierOut)
def create_supplier(
    data: SupplierCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    supplier_data = data.model_dump()
    supplier_data["company_id"] = current_user.company_id
    supplier = Supplier(**supplier_data)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    log_action(db, current_user.id, "CREATE", "supplier", supplier.id, new_values={"name": supplier.name})
    db.commit()
    return supplier


@router.get("/{supplier_id}", response_model=SupplierOut)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierOut)
def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    old = {"name": supplier.name}
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    log_action(db, current_user.id, "UPDATE", "supplier", supplier.id, old_values=old, new_values={"name": supplier.name})
    db.commit()
    return supplier


@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ALLOWED)),
):
    """Soft-delete: is_active = False"""
    q = db.query(Supplier).filter(Supplier.id == supplier_id)
    q = q.filter(Supplier.company_id == current_user.company_id)
    supplier = q.first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    supplier.is_active = False
    db.commit()
    log_action(db, current_user.id, "DELETE", "supplier", supplier.id, old_values={"name": supplier.name})
    db.commit()
