from typing import Optional

from pydantic import BaseModel, Field, field_validator


def _strip_code(v):
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("Kod bo'sh bo'lishi mumkin emas")
    return v


class BinLocationCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    label: Optional[str] = None
    warehouse_id: Optional[int] = None

    @field_validator("code", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("code")
    @classmethod
    def _not_blank(cls, v):
        return _strip_code(v)


class BinLocationUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    label: Optional[str] = None
    is_active: Optional[bool] = None
    warehouse_id: Optional[int] = None

    @field_validator("code", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("code")
    @classmethod
    def _not_blank(cls, v):
        return _strip_code(v)


class BinLocationOut(BaseModel):
    id: int
    code: str
    label: Optional[str] = None
    is_active: bool
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None

    model_config = {"from_attributes": True}
