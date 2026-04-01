import secrets
import hashlib
from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from pydantic import BaseModel  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.api_key import ApiKey  # type: ignore

router = APIRouter(prefix="/api-keys", tags=["Integration API Keys"])

class ApiKeyCreate(BaseModel):
    name: str 

class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_hash: str # Faqat generatsiya vaqtidagina ochiq token beriladi, bu yerda gash

    class Config:
        from_attributes = True

@router.post("/")
def generate_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin))
):
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    new_key = ApiKey(
        name=data.name,
        key_hash=key_hash
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)

    return {
        "id": new_key.id,
        "name": new_key.name,
        "token": raw_key,
        "message": "Tokenni faqat bir marta nusxalab oling!"
    }


@router.get("/", response_model=list[ApiKeyResponse])
def get_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin))
):
    return db.query(ApiKey).all()


@router.delete("/{id}")
def delete_api_key(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin))
):
    key = db.query(ApiKey).filter(ApiKey.id == id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API Key topilmadi")
    db.delete(key)
    db.commit()
    return {"message": "API Key o'chirildi"}
