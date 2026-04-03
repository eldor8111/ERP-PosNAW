from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, field_validator

from app.models.inventory import MovementType


class StockReceiveItem(BaseModel):
    product_id: int
    quantity: Decimal
    reason: Optional[str] = None
    purchase_price: Optional[Decimal] = None  # FIFO uchun tannarx (ixtiyoriy)

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


class ChiqimBatchItem(BaseModel):
    product_id: int
    quantity: Decimal
    type: str
    doc_num: Optional[str] = None
    reason: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def must_be_positive_qty(cls, v):
        if v <= 0:
            raise ValueError("Miqdor musbat bo'lishi kerak")
        return v


class ChiqimBatchRequest(BaseModel):
    items: List[ChiqimBatchItem]


class ChiqimDocumentOut(BaseModel):
    reference_id: int
    created_at: datetime
    type_hints: List[str]
    doc_nums: List[str]
    reasons: List[str]
    total_qty: Decimal
    item_count: int
    user_name: Optional[str]


class ChiqimDetailOut(BaseModel):
    id: int  # movement id
    product_id: int
    product_name: str
    product_sku: str
    product_unit: str
    type: str  # The specific type given, we'll parse it from reason if needed, or we can just send reason text.
    quantity: Decimal
    doc_num: Optional[str]
    reason: Optional[str]

