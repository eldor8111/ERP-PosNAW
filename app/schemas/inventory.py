from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, field_validator

from app.models.inventory import MovementType


class StockReceiveItem(BaseModel):
    product_id: int
    quantity: Decimal
    reason: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Miqdor musbat bo'lishi kerak")
        return v


class StockReceiveRequest(BaseModel):
    items: List[StockReceiveItem]
    note: Optional[str] = None


class StockAdjustRequest(BaseModel):
    product_id: int
    new_quantity: Decimal
    reason: str

    @field_validator("new_quantity")
    @classmethod
    def must_not_be_negative(cls, v):
        if v < 0:
            raise ValueError("Qoldiq manfiy bo'lishi mumkin emas")
        return v


class StockLevelOut(BaseModel):
    product_id: int
    product_name: str
    product_sku: str
    product_barcode: str
    quantity: Decimal
    min_stock: int
    is_low_stock: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class StockMovementOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    type: MovementType
    qty_before: Decimal
    qty_after: Decimal
    quantity: Decimal
    reference_type: Optional[str]
    reference_id: Optional[int]
    reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
