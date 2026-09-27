from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from app.models.production_order import ProductionOrderStatus


# ─── BOM (Retseptura) ──────────────────────────────────────────────────────

class BOMItemIn(BaseModel):
    component_product_id: int
    component_variant_id: Optional[int] = None
    quantity_per_unit: Decimal


class BOMItemOut(BaseModel):
    id: int
    component_product_id: int
    component_product_name: str
    component_variant_id: Optional[int] = None
    component_variant_name: Optional[str] = None
    component_unit: str
    quantity_per_unit: Decimal

    model_config = {"from_attributes": True}


class BOMCreate(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    name: str
    items: List[BOMItemIn]


class BOMUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    items: Optional[List[BOMItemIn]] = None


class BOMOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    variant_id: Optional[int] = None
    variant_name: Optional[str] = None
    name: str
    is_active: bool
    created_at: datetime
    items: List[BOMItemOut] = []

    model_config = {"from_attributes": True}


class BOMListOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    name: str
    is_active: bool
    item_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Ishlab chiqarish buyurtmasi ───────────────────────────────────────────

class ProductionOrderCreate(BaseModel):
    bom_id: int
    planned_quantity: Decimal
    warehouse_id: int
    target_warehouse_id: int
    note: Optional[str] = None


class ShortageItem(BaseModel):
    component_product_id: int
    component_product_name: str
    required_quantity: Decimal
    available_quantity: Decimal
    shortage: Decimal


class ProductionOrderCostIn(BaseModel):
    cost_type: str  # labor, utility, overhead, other
    amount: Decimal
    note: Optional[str] = None


class CompleteProductionOrderRequest(BaseModel):
    produced_quantity: Decimal
    defect_quantity: Decimal = Decimal("0")
    costs: List[ProductionOrderCostIn] = []


class ProductionOrderCostOut(BaseModel):
    id: int
    cost_type: str
    amount: Decimal
    note: Optional[str] = None

    model_config = {"from_attributes": True}


class ProductionOrderOut(BaseModel):
    id: int
    number: str
    bom_id: int
    bom_name: str
    product_id: int
    product_name: str
    variant_id: Optional[int] = None
    variant_name: Optional[str] = None
    planned_quantity: Decimal
    produced_quantity: Decimal
    defect_quantity: Decimal
    warehouse_id: int
    warehouse_name: str
    target_warehouse_id: int
    target_warehouse_name: str
    status: ProductionOrderStatus
    note: Optional[str] = None
    created_by: int
    creator_name: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    unit_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    shortages: List[ShortageItem] = []
    costs: List[ProductionOrderCostOut] = []

    model_config = {"from_attributes": True}


class ProductionOrderListOut(BaseModel):
    id: int
    number: str
    product_name: str
    planned_quantity: Decimal
    produced_quantity: Decimal
    status: ProductionOrderStatus
    warehouse_name: str
    target_warehouse_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
