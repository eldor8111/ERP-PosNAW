from typing import Optional
from pydantic import BaseModel  # type: ignore


class BranchCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    company_id: Optional[int] = None


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    company_id: Optional[int] = None


class BranchOut(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    company_id: Optional[int] = None
    company_name: Optional[str] = None

    model_config = {"from_attributes": True}
