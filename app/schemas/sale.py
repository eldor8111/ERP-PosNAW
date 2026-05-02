from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, field_validator  # type: ignore

from app.models.sale import PaymentType, SaleStatus  # type: ignore


class SaleItemCreate(BaseModel):
    product_id: int
    quantity: Decimal
    unit_price: Optional[Decimal] = None  # None bo'lsa mahsulot narxidan oladi
    discount: Decimal = Decimal("0")

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("Miqdor musbat bo'lishi kerak")
        return v

    @field_validator("discount")
    @classmethod
    def discount_not_negative(cls, v):
        if v < 0:
            raise ValueError("Chegirma manfiy bo'lishi mumkin emas")
        return v

class PaymentItem(BaseModel):
    type: PaymentType
    amount: Decimal

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v):
        if v <= 0:
            raise ValueError("To'lov miqdori musbat bo'lishi kerak")
        return v


class SaleCreate(BaseModel):
    items: List[SaleItemCreate]
    payment_type: PaymentType
    paid_amount: Decimal
    paid_cash: Decimal = Decimal("0")
    paid_card: Decimal = Decimal("0")
    payments: Optional[List[PaymentItem]] = []
    discount_amount: Decimal = Decimal("0")

    @field_validator("discount_amount")
    @classmethod
    def total_discount_not_negative(cls, v):
        if v < 0:
            raise ValueError("Umumiy chegirma manfiy bo'lishi mumkin emas")
        return v
    note: Optional[str] = None
    customer_id: Optional[int] = None
    currency_id: Optional[int] = None
    loyalty_points_used: int = 0
    warehouse_id: Optional[int] = None
    debt_due_date: Optional[date] = None

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v):
        if not v:
            raise ValueError("Savdo elementi bo'sh bo'lishi mumkin emas")
        return v


class SaleItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: Decimal
    unit_price: Decimal
    cost_price: Decimal
    discount: Decimal
    subtotal: Decimal

    model_config = {"from_attributes": True}

class SalePaymentOut(BaseModel):
    id: int
    payment_type: PaymentType
    amount: Decimal

    model_config = {"from_attributes": True}


class SaleOut(BaseModel):
    id: int
    number: str
    cashier_id: int
    cashier_name: str
    customer_id: Optional[int] = None
    total_amount: Decimal
    discount_amount: Decimal
    paid_amount: Decimal
    paid_cash: Decimal
    paid_card: Decimal
    payment_type: PaymentType
    status: SaleStatus
    note: Optional[str]
    items: List[SaleItemOut]
    payments: List[SalePaymentOut] = []
    created_at: datetime
    debt_due_date: Optional[date] = None
    warehouse_id: Optional[int] = None

    model_config = {"from_attributes": True}


class SaleListOut(BaseModel):
    id: int
    number: str
    cashier_name: str
    total_amount: Decimal
    discount_amount: Decimal
    paid_amount: Decimal
    paid_cash: Decimal
    paid_card: Decimal
    payment_type: PaymentType
    status: SaleStatus
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    items_count: int
    created_at: datetime
    debt_due_date: Optional[date] = None

    model_config = {"from_attributes": True}


class SaleUpdate(BaseModel):
    status: Optional[SaleStatus] = None
    note: Optional[str] = None
    paid_amount: Optional[Decimal] = None
    # Full edit fields
    items: Optional[List[SaleItemCreate]] = None
    payment_type: Optional[PaymentType] = None
    paid_cash: Optional[Decimal] = None
    paid_card: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    customer_id: Optional[int] = None
    payments: Optional[List[PaymentItem]] = None
    debt_due_date: Optional[date] = None
    warehouse_id: Optional[int] = None
