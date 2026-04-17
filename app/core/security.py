from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt  # type: ignore
from jose import JWTError, jwt  # type: ignore

from app.config import settings  # type: ignore


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": to_encode.get("type", "access")})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

from fastapi import Security, HTTPException, status, Depends  # type: ignore
from fastapi.security.api_key import APIKeyHeader  # type: ignore
from app.database import get_db  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
import hashlib
from app.models.api_key import ApiKey  # type: ignore

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def get_api_key(
    api_key_header: str = Security(api_key_header),
    db: Session = Depends(get_db)
):
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tashqi xizmat ulanishi uchun X-API-Key kiritilmagan",
        )
    key_hash = hashlib.sha256(api_key_header.encode()).hexdigest()
    key_record = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True).first()
    
    if not key_record:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key noto'g'ri yoki faol emas!",
        )
    return key_record
