from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from decimal import Decimal

class PromotionProductIn(BaseModel):
    product_id: int

class PromotionProductOut(BaseModel):
    id: int
    product_id: int
    model_config = ConfigDict(from_attributes=True)

class PromotionBase(BaseModel):
    name: str
    discount_type: str = "percent"  # percent, amount
    discount_value: Decimal
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_active: bool = True

class PromotionCreate(PromotionBase):
    products: Optional[List[PromotionProductIn]] = []

class PromotionUpdate(PromotionBase):
    name: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None
    products: Optional[List[PromotionProductIn]] = None

class PromotionOut(PromotionBase):
    id: int
    company_id: int
    created_at: datetime
    updated_at: datetime
    products: List[PromotionProductOut] = []

    model_config = ConfigDict(from_attributes=True)
