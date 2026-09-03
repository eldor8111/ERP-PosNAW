from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, field_validator

class ExpiringBatchOut(BaseModel):
    batch_id: int
    product_name: str
    variant_name: Optional[str] = None
    expiry_date: Optional[date] = None
    days_left: Optional[int] = None
    quantity: Decimal
    is_expired: bool

class WriteOffExpiredRequest(BaseModel):
    batch_id: int

from app.models.inventory import MovementType


class StockReceiveItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: Decimal
    reason: Optional[str] = None
    purchase_price: Optional[Decimal] = None  # FIFO/FEFO uchun tannarx (ixtiyoriy)
    expiry_date: Optional[date] = None

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
    variant_id: Optional[int] = None
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
    variant_id: Optional[int] = None
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
    variant_id: Optional[int] = None
    product_name: str
    product_sku: Optional[str] = None
    product_unit: Optional[str] = None
    type: MovementType
    qty_before: Decimal
    qty_after: Decimal
    quantity: Decimal
    reference_type: Optional[str]
    reference_id: Optional[int]
    reason: Optional[str]
    contragent_name: Optional[str] = None
    user_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class StockMovementUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    reason: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None

    model_config = {"from_attributes": True}


class ChiqimBatchItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
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
    warehouse_id: Optional[int] = None


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
    variant_id: Optional[int] = None
    product_name: str
    product_sku: str
    product_unit: str
    type: str  # The specific type given, we'll parse it from reason if needed, or we can just send reason text.
    quantity: Decimal
    doc_num: Optional[str]
    reason: Optional[str]


class SupplierReturnItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: Decimal
    unit_cost: Decimal  # The price at which the item is being returned

    @field_validator("quantity", "unit_cost")
    @classmethod
    def must_be_positive_val(cls, v):
        if v < 0:
            raise ValueError("Qiymat manfiy bo'lishi mumkin emas")
        return v


class SupplierReturnRequest(BaseModel):
    supplier_id: int
    warehouse_id: Optional[int] = None
    items: List[SupplierReturnItem]
    received_amount: Decimal = Decimal("0")
    wallet_id: Optional[int] = None
    note: Optional[str] = None


# ── Mijozdan qaytarish (mustaqil operatsiya) ──────────────────────────────

class CustomerReturnItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: Decimal
    unit_price: Decimal  # Qaytarish narxi

    @field_validator("quantity", "unit_price")
    @classmethod
    def must_be_positive_val(cls, v):
        if v < 0:
            raise ValueError("Qiymat manfiy bo'lishi mumkin emas")
        return v


class CustomerReturnRequest(BaseModel):
    customer_id: Optional[int] = None
    warehouse_id: int
    items: List[CustomerReturnItem]
    # To'lov turi: debt (qarzga yopish), cash (naqd qaytarish), card (karta)
    payment_type: str = "debt"
    paid_cash: Decimal = Decimal("0")
    paid_card: Decimal = Decimal("0")
    wallet_id: Optional[int] = None   # Naqd/karta uchun kassa
    note: Optional[str] = None
