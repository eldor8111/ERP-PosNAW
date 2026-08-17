from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.role import Role
from app.models.user import User, UserRole
from app.schemas.role import RoleCreate, RoleUpdate, RoleResponse
from app.core.dependencies import get_current_user

router = APIRouter(prefix="/roles", tags=["Roles"])

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in (UserRole.admin, UserRole.director, UserRole.super_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission")
    return current_user


@router.get("/", response_model=List[RoleResponse])
def get_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    if current_user.role == UserRole.super_admin:
        return db.query(Role).all()
    else:
        return db.query(Role).filter(
            (Role.company_id == current_user.company_id) | (Role.company_id == None)
        ).all()


@router.post("/", response_model=RoleResponse)
def create_role(
    data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    if current_user.role != UserRole.super_admin and not current_user.company_id:
        raise HTTPException(status_code=400, detail="Company ID missing")

    new_role = Role(
        name=data.name,
        company_id=None if current_user.role == UserRole.super_admin else current_user.company_id,
        permissions=data.permissions,
        is_system=False
    )
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    return new_role


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: int,
    data: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    if current_user.role != UserRole.super_admin and role.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Not your role")

    if role.is_system and current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Cannot edit system role")

    role.name = data.name
    role.permissions = data.permissions
    db.commit()
    db.refresh(role)
    return role


@router.delete("/{role_id}")
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    if current_user.role != UserRole.super_admin and role.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Not your role")

    if role.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system role")

    # Prevent deleting if it's assigned to users
    if db.query(User).filter(User.role_id == role_id).first():
        raise HTTPException(status_code=400, detail="Role is assigned to users")

    db.delete(role)
    db.commit()
    return {"detail": "Role deleted"}
