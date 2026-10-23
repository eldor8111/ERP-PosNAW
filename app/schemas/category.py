from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator


def _check_markup(v):
    if v is not None and not 0 <= v <= 1000:
        raise ValueError("Ustama foizi 0 dan 1000 gacha bo'lishi kerak")
    return v


class CategoryCreate(BaseModel):
    name: str
    parent_id: Optional[int] = None
    sort_order: int = 0
    is_perishable: bool = False
    markup_pct: Optional[float] = None

    @field_validator("markup_pct")
    @classmethod
    def _markup(cls, v):
        return _check_markup(v)


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_perishable: Optional[bool] = None
    markup_pct: Optional[float] = None  # null yuborilsa (model_fields_set da bo'lsa) — ustama tozalanadi

    @field_validator("markup_pct")
    @classmethod
    def _markup(cls, v):
        return _check_markup(v)


class BulkDeleteCategoriesIn(BaseModel):
    category_ids: Optional[List[int]] = None
    delete_all: bool = False


class CategoryOut(BaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    sort_order: int
    is_perishable: bool
    markup_pct: Optional[float] = None
    created_at: datetime
    children: List["CategoryOut"] = []
    products_count: int = 0

    model_config = {"from_attributes": True}


CategoryOut.model_rebuild()
