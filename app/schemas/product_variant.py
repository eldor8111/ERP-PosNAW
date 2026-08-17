from pydantic import BaseModel, ConfigDict
from typing import Optional
from decimal import Decimal

class ProductVariantBase(BaseModel):
    name: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    cost_price: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    wholesale_price: Optional[Decimal] = None

class ProductVariantCreate(ProductVariantBase):
    id: Optional[int] = None
    product_id: Optional[int] = None
    quantity: Optional[Decimal] = None       # Dastlabki qoldiq (razmer matritsasidan)
    colorHex: Optional[str] = None           # Rang kodi (UI uchun)

class ProductVariantUpdate(ProductVariantBase):
    pass

class ProductVariantOut(ProductVariantBase):
    id: int
    product_id: int
    stock_quantity: Optional[Decimal] = None  # qoldiq (UI uchun)
    color: Optional[str] = None
    size: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
