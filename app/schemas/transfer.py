from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator
from app.models.transfer import TransferStatus


class TransferItemCreate(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    # Miqdor musbat bo'lishi shart (manfiy/nol — 422)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    # Ixtiyoriy: maqsad omborda boshqa mahsulotga kirim qilish
    target_product_id: Optional[int] = None


def _check_duplicate_items(items: List[TransferItemCreate]) -> None:
    """(product_id, variant_id, target_product_id) takrorlansa — xato (422)"""
    seen = set()
    for it in items:
        key = (it.product_id, it.variant_id or None, it.target_product_id or None)
        if key in seen:
            raise ValueError("Takroriy qator")
        seen.add(key)


class TransferItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    variant_id: Optional[int] = None
    variant_name: Optional[str] = None
    # Mapping ma'lumotlari (agar boshqa mahsulotga yo'naltirilgan bo'lsa)
    target_product_id: Optional[int] = None
    target_product_name: Optional[str] = None
    quantity: Decimal
    # T4.1: yuborilgan / qabul qilingan haqiqiy miqdor va kamomad sababi
    qty_sent: Optional[Decimal] = None
    qty_received: Optional[Decimal] = None
    discrepancy_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class TransferCreate(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    note: Optional[str] = None
    items: List[TransferItemCreate] = Field(min_length=1)
    # T4.1: None — avtomatik (omborlar farqli filiallarda bo'lsa ikki bosqichli); True/False — majburan
    two_step: Optional[bool] = None
    # Ikki bosqichli rejimda: True — darhol yuboriladi (in_transit), False — qoralama (pending)
    send: bool = True

    @model_validator(mode="after")
    def _no_duplicates(self):
        _check_duplicate_items(self.items)
        return self


class TransferReceiveItem(BaseModel):
    item_id: int
    qty_received: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    reason: Optional[str] = Field(default=None, max_length=200)


class TransferReceive(BaseModel):
    items: List[TransferReceiveItem] = []
    note: Optional[str] = None


class TransferCancel(BaseModel):
    reason: Optional[str] = None


class InTransitRow(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    qty: Decimal


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
    # T4.1
    sent_by: Optional[int] = None
    sender_name: Optional[str] = None
    sent_at: Optional[datetime] = None
    confirmer_name: Optional[str] = None
    cancel_reason: Optional[str] = None
    from_branch_id: Optional[int] = None
    from_branch_name: Optional[str] = None
    to_branch_id: Optional[int] = None
    to_branch_name: Optional[str] = None
    two_step: bool = False
    # Joriy foydalanuvchi uchun ruxsat etilgan amallar (filial qoidasi bo'yicha)
    can_send: bool = False
    can_receive: bool = False
    can_cancel: bool = False

    model_config = {"from_attributes": True}


class TransferListOut(BaseModel):
    id: int
    number: str
    from_warehouse_name: str
    to_warehouse_name: str
    status: TransferStatus
    created_at: datetime
    # T4.1
    from_warehouse_id: Optional[int] = None
    to_warehouse_id: Optional[int] = None
    from_branch_name: Optional[str] = None
    to_branch_name: Optional[str] = None
    total_qty: Decimal = Decimal(0)
    direction: Optional[str] = None   # incoming | outgoing | internal (foydalanuvchi filialiga nisbatan)
    can_send: bool = False
    can_receive: bool = False
    can_cancel: bool = False

    model_config = {"from_attributes": True}


class TransferUpdate(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int
    note: Optional[str] = None
    items: List[TransferItemCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_duplicates(self):
        _check_duplicate_items(self.items)
        return self
