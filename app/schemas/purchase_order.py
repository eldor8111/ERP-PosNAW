from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.models.purchase_order import POStatus


class POItemCreate(BaseModel):
    product_id: int
    qty_ordered: Decimal
    unit_cost: Decimal
    new_sale_price: Optional[Decimal] = None
    new_wholesale_price: Optional[Decimal] = None


class POItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    qty_ordered: Decimal
    qty_received: Decimal
    unit_cost: Decimal

    model_config = {"from_attributes": True}


class POCreate(BaseModel):
    supplier_id: int
    warehouse_id: int
    status: Optional[POStatus] = None
    note: Optional[str] = None
    expected_date: Optional[datetime] = None
    paid_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    payment_type: str = "cash"
    wallet_id: Optional[int] = None
    items: List[POItemCreate]


class POReceiveItem(BaseModel):
    po_item_id: int
    qty_received: Decimal
    lot_number: Optional[str] = None
    expiry_date: Optional[datetime] = None


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

    model_config = {"from_attributes": True}
