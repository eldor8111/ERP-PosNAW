from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.schemas.branch import BranchCreate, BranchOut, BranchUpdate

router = APIRouter(prefix="/branches", tags=["Branches"])

ADMIN_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)


@router.get("", response_model=List[BranchOut])
def list_branches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Branch).filter(Branch.is_active == True)
    q = q.filter(Branch.company_id == current_user.company_id)
    return q.order_by(Branch.name).all()


@router.post("", response_model=BranchOut)
def create_branch(
    data: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    branch = Branch(**data.model_dump())
    if current_user.role != UserRole.super_admin:
        branch.company_id = current_user.company_id
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


@router.get("/{branch_id}", response_model=BranchOut)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Branch).filter(Branch.id == branch_id)
    q = q.filter(Branch.company_id == current_user.company_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    return branch


@router.patch("/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: int,
    data: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    q = db.query(Branch).filter(Branch.id == branch_id)
    q = q.filter(Branch.company_id == current_user.company_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(branch, field, value)
    db.commit()
    db.refresh(branch)
    return branch


@router.delete("/{branch_id}", status_code=204)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    q = db.query(Branch).filter(Branch.id == branch_id)
    q = q.filter(Branch.company_id == current_user.company_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    branch.is_active = False
    db.commit()
