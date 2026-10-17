from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.models.warehouse import WarehouseType


class WarehouseCreate(BaseModel):
    name: str
    type: WarehouseType = WarehouseType.main
    branch_id: Optional[int] = None
    is_default: bool = False  # T1.4: filialning asosiy savdo ombori


class WarehouseUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[WarehouseType] = None
    branch_id: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None  # T1.4


class WarehouseOut(BaseModel):
    id: int
    name: str
    type: WarehouseType
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None  # T1.3: ro'yxatlarda filial nomi (aks holda None)
    is_active: bool
    is_default: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}
