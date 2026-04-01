from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class BatchOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    warehouse_id: int
    warehouse_name: str
    lot_number: str
    manufacture_date: Optional[datetime]
    expiry_date: Optional[datetime]
    quantity: Decimal
    po_id: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}
