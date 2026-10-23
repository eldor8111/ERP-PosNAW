from datetime import datetime, date
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

class ExpiringBatchOut(BaseModel):
    batch_id: int
    product_name: str
    variant_name: Optional[str] = None
    expiry_date: Optional[date] = None
    days_left: Optional[int] = None
    quantity: Decimal
    is_expired: bool
    # T1.8: partiya qaysi omborda/filialda turibdi
    product_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    branch_id: Optional[int] = None

class WriteOffExpiredRequest(BaseModel):
    # T1.8: bitta partiya (batch_id) yoki bir nechta (batch_ids); kamida bittasi kerak
    batch_id: Optional[int] = None
    batch_ids: Optional[List[int]] = None

    @model_validator(mode="after")
    def need_any_batch(self):
        if self.batch_id is None and not self.batch_ids:
            raise ValueError("batch_id yoki batch_ids ko'rsatilishi kerak")
        return self

from app.models.inventory import MovementType


class StockReceiveItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: Decimal
    reason: Optional[str] = None
    purchase_price: Optional[Decimal] = None  # FIFO/FEFO uchun tannarx (UZS, ixtiyoriy)
    cost_price: Optional[Decimal] = None      # frontend nomi — purchase_price bilan bir xil
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None  # CD.1 (dorixona): ishlab chiqarilgan sana; qolgan muddat foizi shundan hisoblanadi
    # CD.1/D3.2 (dorixona): markirovkali dori kodlari (Data Matrix) — partiya bilan bir tranzaksiyada in_stock bo'lib yoziladi
    marking_codes: Optional[List[str]] = None

    @field_validator("quantity")
    @classmethod
    def must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("Miqdor musbat bo'lishi kerak")
        return v

    @field_validator("purchase_price", "cost_price")
    @classmethod
    def price_not_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Narx manfiy bo'lishi mumkin emas")
        return v


class StockReceiveRequest(BaseModel):
    items: List[StockReceiveItem]
    note: Optional[str] = None
    warehouse_id: Optional[int] = None
    supplier_id: Optional[int] = None


class StockAdjustRequest(BaseModel):
    product_id: int
    warehouse_id: int
    variant_id: Optional[int] = None
    new_quantity: Decimal
    reason: str = Field(..., min_length=3)

    @field_validator("new_quantity")
    @classmethod
    def must_not_be_negative(cls, v):
        if v < 0:
            raise ValueError("Qoldiq manfiy bo'lishi mumkin emas")
        return v


class StockLevelOut(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    product_name: str
    product_sku: str
    product_barcode: str
    quantity: Decimal
    # T4.4: samarali qiymatlar — ombor sozlamasi (min_qty/max_qty) yoki mahsulotniki
    min_stock: float
    max_stock: Optional[float] = None
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
    # T1.7: harakat ombori (eski aniqlanmagan ADJUST harakatlarida None bo'lishi mumkin)
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class StockMovementUpdate(BaseModel):
    # Faqat izoh o'zgaradi. quantity/reference_type/reference_id yuborilsa 422 —
    # harakatni "return_from_customer" + begona mijoz ID ga soxtalashtirish yopildi.
    reason: Optional[str] = None

    model_config = {"from_attributes": True, "extra": "forbid"}


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
    # Servisda majburiy tekshiriladi (eski mijoz yubormasa — yagona mos ombor olinadi)
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
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None


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
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None


class SupplierReturnItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: Decimal
    unit_cost: Decimal  # The price at which the item is being returned
    batch_id: Optional[int] = None  # D3.3 (dorixona): aynan shu partiyadan qaytarish (oddiy korxonada e'tiborsiz)

    @field_validator("quantity", "unit_cost")
    @classmethod
    def must_be_positive_val(cls, v):
        if v < 0:
            raise ValueError("Qiymat manfiy bo'lishi mumkin emas")
        return v


class SupplierReturnRequest(BaseModel):
    supplier_id: int
    # T1.16: servisda majburiy tekshiriladi (ko'p omborli korxonada ko'rsatilmasa 400;
    # yagona faol ombor bo'lsa avtomatik tanlanadi)
    warehouse_id: Optional[int] = None
    items: List[SupplierReturnItem]
    received_amount: Decimal = Decimal("0")
    wallet_id: Optional[int] = None
    payment_type: Optional[str] = "cash"
    note: Optional[str] = None

    @field_validator("received_amount")
    @classmethod
    def received_not_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Qaytgan summa manfiy bo'lishi mumkin emas")
        return v


# ── Mijozdan qaytarish (mustaqil operatsiya) ──────────────────────────────

class CustomerReturnItem(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: Decimal
    unit_price: Decimal  # Qaytarish narxi

    @field_validator("quantity")
    @classmethod
    def must_be_positive_qty(cls, v):
        if v <= 0:
            raise ValueError("Miqdor musbat bo'lishi kerak")
        return v

    @field_validator("unit_price")
    @classmethod
    def must_be_positive_val(cls, v):
        if v < 0:
            raise ValueError("Qiymat manfiy bo'lishi mumkin emas")
        return v


class CustomerReturnRequest(BaseModel):
    customer_id: Optional[int] = None
    warehouse_id: int
    items: List[CustomerReturnItem] = Field(min_length=1)
    # To'lov turi: debt (qarzga yopish), cash (naqd qaytarish), card (karta), mixed (aralash)
    payment_type: Literal["debt", "cash", "card", "mixed"] = "debt"
    paid_cash: Decimal = Decimal("0")
    paid_card: Decimal = Decimal("0")
    wallet_id: Optional[int] = None   # Naqd/karta uchun kassa
    note: Optional[str] = None

    @field_validator("paid_cash", "paid_card")
    @classmethod
    def paid_not_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("To'lov summasi manfiy bo'lishi mumkin emas")
        return v


# ─── T4.4: ombor bo'yicha min/max qoldiq va to'ldirish ───

class StockSettingIn(BaseModel):
    """Ombor x mahsulot chegarasi. Berilmagan maydon o'zgarmaydi, `null` — qiymatni olib tashlaydi.
    Qiymat tekshiruvlari (manfiy, max < min, manba = ombor) router'da 400 beradi."""
    min_qty: Optional[Decimal] = None
    max_qty: Optional[Decimal] = None
    reorder_qty: Optional[Decimal] = None
    source_warehouse_id: Optional[int] = None


class StockSettingBulkItem(StockSettingIn):
    product_id: int


class StockSettingBulkIn(BaseModel):
    warehouse_id: int
    items: List[StockSettingBulkItem] = Field(max_length=1000)


class StockSettingOut(BaseModel):
    product_id: int
    product_name: str
    product_sku: Optional[str] = None
    company_min_stock: Optional[float] = None
    company_max_stock: Optional[float] = None
    min_qty: Optional[float] = None
    max_qty: Optional[float] = None
    reorder_qty: Optional[float] = None
    source_warehouse_id: Optional[int] = None
    current_qty: float = 0


class ReplenishmentItem(BaseModel):
    warehouse_id: int
    warehouse_name: Optional[str] = None
    branch_id: Optional[int] = None
    product_id: int
    product_name: str
    sku: Optional[str] = None
    unit: Optional[str] = None
    current_qty: float
    min: float
    max: Optional[float] = None
    reorder_qty: Optional[float] = None
    shortage: float
    need_qty: float
    source_warehouse_id: Optional[int] = None
    source_warehouse_name: Optional[str] = None
    source_qty: Optional[float] = None
    source_min: Optional[float] = None
    transfer_qty: float
    purchase_needed: float


class ReplenishmentTransferItem(BaseModel):
    product_id: int
    qty: Decimal


class ReplenishmentTransferIn(BaseModel):
    source_warehouse_id: int
    destination_warehouse_id: int
    items: List[ReplenishmentTransferItem] = Field(min_length=1)

