from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.warehouse import WarehouseType


class WarehouseCreate(BaseModel):
    name: str
    type: WarehouseType = WarehouseType.main
    branch_id: Optional[int] = None


class WarehouseUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[WarehouseType] = None
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None


class WarehouseOut(BaseModel):
    id: int
    name: str
    type: WarehouseType
    branch_id: Optional[int] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
