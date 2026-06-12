from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from app.models.mxik import VatRateType


class MxikPackageOut(BaseModel):
    id:             int
    code:           int
    parent_code:    Optional[int]   = None
    container_code: Optional[int]   = None
    container_name: Optional[str]   = None
    unit_id:        Optional[int]   = None
    unit_name:      Optional[str]   = None
    parent_value:   Optional[Decimal] = None
    name:           Optional[str]   = None
    type:           Optional[int]   = None
    is_unit_package: Optional[int]  = None

    model_config = {"from_attributes": True}


class MxikReferenceOut(BaseModel):
    id:           int
    mxik_code:    str
    mxik_name:    Optional[str] = None
    short_name:   Optional[str] = None

    group_code:        Optional[str] = None
    group_name:        Optional[str] = None
    class_code:        Optional[str] = None
    class_name:        Optional[str] = None
    position_code:     Optional[str] = None
    position_name:     Optional[str] = None
    sub_position_code: Optional[str] = None
    sub_position_name: Optional[str] = None

    brand_code:        Optional[str] = None
    brand_name:        Optional[str] = None
    attribute_name:    Optional[str] = None
    international_code: Optional[str] = None

    label:    int = 0
    use_card: int = 0

    lgota_id:      Optional[int] = None
    lgota_name:    Optional[str] = None
    vat_rate_type: VatRateType   = VatRateType.standard

    last_synced_at: Optional[datetime] = None
    packages:       List[MxikPackageOut] = []

    model_config = {"from_attributes": True}


class MxikSyncRequest(BaseModel):
    mxik_code:     str
    terminal_id:   Optional[str] = None  # None bo'lsa config dan olinadi
    force_refresh: bool = False           # True = har doim API dan yangilaydi
