import json
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator

from app.models.product import ProductStatus


class WarehouseStockOut(BaseModel):
    warehouse_id: int
    warehouse_name: str
    quantity: Decimal

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    name: str
    sku: Optional[str] = None
    barcode: str
    extra_barcodes: Optional[List[str]] = None
    name_ru: Optional[str] = None
    category_id: Optional[int] = None
    unit: str = "dona"
    cost_price: Decimal = Decimal("0")
    wholesale_price: Optional[Decimal] = None
    sale_price: Decimal
    min_stock: int = 0
    max_stock: Optional[int] = None
    bin_location: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None   # list of uploaded image URLs
    weight: Optional[Decimal] = None
    dimensions: Optional[str] = None
    brand: Optional[str] = None
    status: ProductStatus = ProductStatus.active
    initial_stock: Optional[Decimal] = None

    @field_validator("cost_price", "sale_price")
    @classmethod
    def must_be_positive(cls, v):
        if v < 0:
            raise ValueError("Narx manfiy bo'lishi mumkin emas")
        return v


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    name_ru: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    extra_barcodes: Optional[List[str]] = None
    brand: Optional[str] = None
    category_id: Optional[int] = None
    unit: Optional[str] = None
    cost_price: Optional[Decimal] = None
    wholesale_price: Optional[Decimal] = None
    sale_price: Optional[Decimal] = None
    min_stock: Optional[int] = None
    max_stock: Optional[int] = None
    bin_location: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    weight: Optional[Decimal] = None
    dimensions: Optional[str] = None
    status: Optional[ProductStatus] = None


class ProductStatusUpdate(BaseModel):
    status: ProductStatus


class ProductOut(BaseModel):
    id: int
    sku: str
    barcode: str
    extra_barcodes: Optional[List[str]] = None
    name: str
    name_ru: Optional[str]
    category_id: Optional[int]
    unit: str
    cost_price: Decimal
    wholesale_price: Optional[Decimal] = None
    sale_price: Decimal
    min_stock: int
    max_stock: Optional[int]
    bin_location: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    weight: Optional[Decimal] = None
    dimensions: Optional[str] = None
    brand: Optional[str] = None
    status: ProductStatus
    created_at: datetime
    stock_quantity: Optional[Decimal] = None

    model_config = {"from_attributes": True}

    @field_validator("images", mode="before")
    @classmethod
    def parse_images(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v

    @field_validator("extra_barcodes", mode="before")
    @classmethod
    def parse_extra_barcodes(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v


class ProductListOut(BaseModel):
    id: int
    sku: str
    barcode: str
    extra_barcodes: Optional[List[str]] = None
    name: str
    unit: str
    cost_price: Decimal
    wholesale_price: Optional[Decimal] = None
    sale_price: Decimal
    bin_location: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[List[str]] = None
    brand: Optional[str] = None
    status: ProductStatus
    stock_quantity: Optional[Decimal] = None
    warehouse_stocks: List[WarehouseStockOut] = []

    model_config = {"from_attributes": True}

    @field_validator("images", mode="before")
    @classmethod
    def parse_images(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v

    @field_validator("extra_barcodes", mode="before")
    @classmethod
    def parse_extra_barcodes(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return v
