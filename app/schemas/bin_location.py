from typing import Optional

from pydantic import BaseModel


class BinLocationCreate(BaseModel):
    code: str
    label: Optional[str] = None


class BinLocationUpdate(BaseModel):
    code: Optional[str] = None
    label: Optional[str] = None
    is_active: Optional[bool] = None


class BinLocationOut(BaseModel):
    id: int
    code: str
    label: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}
