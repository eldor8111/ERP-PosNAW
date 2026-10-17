import secrets
import hashlib
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from pydantic import BaseModel, Field, field_validator  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.database import get_db  # type: ignore
from app.core.audit import log_action  # type: ignore
from app.core.dependencies import require_roles  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.api_key import ApiKey  # type: ignore

router = APIRouter(prefix="/api-keys", tags=["Integration API Keys"])

class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nom bo'sh bo'lmasligi kerak")
        return v

class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: Optional[str] = None  # tokenning dastlabki belgilari; hash mijozga QAYTARILMAYDI
    is_active: bool
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True

@router.post("/")
def generate_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin))
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")

    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    new_key = ApiKey(
        name=data.name,
        key_hash=key_hash,
        company_id=current_user.company_id,
        created_by=current_user.id,
        key_prefix=raw_key[:8],
    )
    db.add(new_key)
    db.flush()
    log_action(db, "api_key.create", "api_key", new_key.id, current_user.id, new_values={"name": data.name})
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
    # Faqat o'z korxonasi kalitlari; company_id IS NULL (egasiz eski) kalitlar hech kimga ko'rinmaydi
    if not current_user.company_id:
        return []  # `company_id == None` SQLda IS NULL bo'lib qolmasligi uchun
    return (
        db.query(ApiKey)
        .filter(ApiKey.company_id == current_user.company_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.delete("/{id}")
def delete_api_key(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin))
):
    key = None
    if current_user.company_id:
        key = db.query(ApiKey).filter(ApiKey.id == id, ApiKey.company_id == current_user.company_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API Key topilmadi")
    log_action(db, "api_key.delete", "api_key", key.id, current_user.id, old_values={"name": key.name})
    db.delete(key)
    db.commit()
    return {"message": "API Key o'chirildi"}
