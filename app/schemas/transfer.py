from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from app.models.transfer import TransferStatus


class TransferItemCreate(BaseModel):
    product_id: int
    quantity: Decimal


class TransferItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: Decimal

    model_config = {"from_attributes": True}


class TransferCreate(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    note: Optional[str] = None
    items: List[TransferItemCreate]


class TransferOut(BaseModel):
    id: int
    number: str
    from_warehouse_id: int
    from_warehouse_name: str
    to_warehouse_id: int
    to_warehouse_name: str
    status: TransferStatus
    note: Optional[str]
    created_by: int
    creator_name: str
    confirmed_by: Optional[int]
    confirmed_at: Optional[datetime]
    created_at: datetime
    items: List[TransferItemOut] = []

    model_config = {"from_attributes": True}


class TransferListOut(BaseModel):
    id: int
    number: str
    from_warehouse_name: str
    to_warehouse_name: str
    status: TransferStatus
    created_at: datetime

    model_config = {"from_attributes": True}
