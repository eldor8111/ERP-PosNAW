from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None


class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    sort_order: int
    created_at: datetime
    children: List["CategoryOut"] = []
    products_count: int = 0

    model_config = {"from_attributes": True}


CategoryOut.model_rebuild()
