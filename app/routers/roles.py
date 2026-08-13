from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from app.database import get_db
from app.core.dependencies import get_current_user, require_roles
from app.models.user import User, UserRole

router = APIRouter(tags=["roles"])

class RoleCreate(BaseModel):
    name: str
    permissions: Dict[str, Any]

class RoleOut(BaseModel):
    id: int
    name: str
    permissions: Dict[str, Any]

@router.get("/", response_model=List[RoleOut])
def get_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director))
):
    # Using raw SQL to avoid needing a full SQLAlchemy model for a simple feature
    sql = """
        SELECT id, name, permissions FROM custom_roles
        WHERE company_id = :company_id
    """
    roles = db.execute(db.bind.text(sql), {"company_id": current_user.company_id}).fetchall()
    return [{"id": r[0], "name": r[1], "permissions": r[2]} for r in roles]

@router.post("/", response_model=RoleOut)
def create_role(
    data: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director))
):
    sql = """
        INSERT INTO custom_roles (company_id, name, permissions)
        VALUES (:company_id, :name, :permissions)
        RETURNING id, name, permissions
    """
    import json
    result = db.execute(db.bind.text(sql), {
        "company_id": current_user.company_id,
        "name": data.name,
        "permissions": json.dumps(data.permissions)
    }).fetchone()
    db.commit()
    return {"id": result[0], "name": result[1], "permissions": result[2]}
