from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, field_validator
from app.models.purchase_order import POStatus


def _positive(v, name):
    if v is not None and v <= 0:
        raise ValueError(f"{name} musbat bo'lishi kerak")
    return v


def _not_negative(v, name):
    if v is not None and v < 0:
        raise ValueError(f"{name} manfiy bo'lishi mumkin emas")
    return v


class POItemCreate(BaseModel):
    product_id: int
    qty_ordered: Decimal
    unit_cost: Decimal  # UZS (sof, chegirmadan keyin)
    cost_currency: Optional[str] = "UZS"
    original_unit_cost: Optional[Decimal] = None
    new_sale_price: Optional[Decimal] = None
    new_wholesale_price: Optional[Decimal] = None
    expiry_date: Optional[datetime] = None

    @field_validator("qty_ordered")
    @classmethod
    def _qty(cls, v):
        return _positive(v, "Miqdor")

    @field_validator("unit_cost", "original_unit_cost", "new_sale_price", "new_wholesale_price")
    @classmethod
    def _prices(cls, v):
        return _not_negative(v, "Narx")


class POItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    qty_ordered: Decimal
    qty_received: Decimal
    unit_cost: Decimal
    cost_currency: Optional[str] = "UZS"
    original_unit_cost: Optional[Decimal] = None
    expiry_date: Optional[datetime] = None
    new_sale_price: Optional[Decimal] = None
    new_wholesale_price: Optional[Decimal] = None

    model_config = {"from_attributes": True}


class _PaymentFields(BaseModel):
    # To'lov: paid_amount — UZS da (qarz hisobi uchun); payment_amount/payment_currency —
    # kassadan haqiqatan chiqqan summa va uning valyutasi (berilmasa UZS).
    payment_type: Optional[str] = None
    payment_currency: Optional[str] = None
    payment_amount: Optional[Decimal] = None

    @field_validator("payment_amount")
    @classmethod
    def _pay_amount(cls, v):
        return _not_negative(v, "To'lov summasi")


class POCreate(_PaymentFields):
    supplier_id: int
    warehouse_id: int
    status: Optional[POStatus] = None
    note: Optional[str] = None
    expected_date: Optional[datetime] = None
    paid_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    wallet_id: Optional[int] = None
    currency: Optional[str] = "UZS"
    items: List[POItemCreate]

    @field_validator("paid_amount", "discount_amount")
    @classmethod
    def _amounts(cls, v):
        return _not_negative(v, "Summa")

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in (POStatus.draft, POStatus.sent, POStatus.received):
            raise ValueError("Yangi xarid faqat qoralama, yuborilgan yoki qabul qilingan holatda yaratiladi")
        return v

    @field_validator("items")
    @classmethod
    def _items(cls, v):
        if not v:
            raise ValueError("Kamida bitta mahsulot kerak")
        return v


class POUpdate(_PaymentFields):
    supplier_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    note: Optional[str] = None
    expected_date: Optional[datetime] = None
    paid_amount: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    wallet_id: Optional[int] = None
    currency: Optional[str] = None
    items: Optional[List[POItemCreate]] = None

    @field_validator("paid_amount", "discount_amount")
    @classmethod
    def _amounts(cls, v):
        return _not_negative(v, "Summa")


class POReceiveItem(BaseModel):
    po_item_id: int
    qty_received: Decimal
    lot_number: Optional[str] = None
    expiry_date: Optional[datetime] = None

    @field_validator("qty_received")
    @classmethod
    def _qty(cls, v):
        return _not_negative(v, "Qabul miqdori")


class POReceiveRequest(BaseModel):
    items: List[POReceiveItem]
    note: Optional[str] = None


class POOut(BaseModel):
    id: int
    number: str
    supplier_id: int
    supplier_name: str
    warehouse_id: int
    warehouse_name: str
    status: POStatus
    total_amount: Decimal
    note: Optional[str]
    expected_date: Optional[datetime]
    created_by: int
    creator_name: str
    created_at: datetime
    paid_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    currency: Optional[str] = "UZS"
    exchange_rate: Optional[Decimal] = None
    items: List[POItemOut] = []

    model_config = {"from_attributes": True}


class POListOut(BaseModel):
    id: int
    number: str
    supplier_name: str
    warehouse_name: str
    status: POStatus
    total_amount: Decimal
    created_at: datetime
    paid_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    currency: Optional[str] = "UZS"
    original_total_amount: Optional[Decimal] = None
    original_paid_amount: Optional[Decimal] = None
    debt_amount: Optional[Decimal] = None

    model_config = {"from_attributes": True}
