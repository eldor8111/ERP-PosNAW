from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.models.inventory_count import CountStatus


class CountItemUpdate(BaseModel):
    product_id: int
    counted_qty: Decimal
    variance_reason: Optional[str] = None


class CountCreate(BaseModel):
    warehouse_id: int
    note: Optional[str] = None
    category_ids: Optional[List[int]] = None  # None = to'liq, list = qisman


class CountItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_sku: str
    product_unit: str
    product_category_id: Optional[int] = None
    system_qty: Decimal
    counted_qty: Optional[Decimal]
    variance: Optional[Decimal]
    variance_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class InventoryCountOut(BaseModel):
    id: int
    number: str
    warehouse_id: int
    warehouse_name: str
    status: CountStatus
    note: Optional[str]
    created_by: int
    creator_name: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
    items: List[CountItemOut] = []

    model_config = {"from_attributes": True}


class InventoryCountListOut(BaseModel):
    id: int
    number: str
    warehouse_name: str
    status: CountStatus
    created_at: datetime
    item_count: int = 0

    model_config = {"from_attributes": True}
