from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator


# ── Mir-maza webhook (T0.18) ───────────────────────────────────────────────

class MirmazaItem(BaseModel):
    externalId: str = Field(..., min_length=1, max_length=100)
    quantity: Decimal = Field(Decimal("1"), gt=0)
    total: Decimal = Field(..., ge=0)


class MirmazaWebhookIn(BaseModel):
    marketOrderId: int = Field(..., validation_alias=AliasChoices("marketOrderId", "orderId"))
    items: List[MirmazaItem] = Field(default_factory=list)


class AgentSendCodeIn(BaseModel):
    org_code: str = Field(..., min_length=3, max_length=20, description="Distribyutor korxona kodi")
    phone: str = Field(..., min_length=9, max_length=20)

class AgentRegisterIn(BaseModel):
    org_code: str = Field(..., min_length=3, max_length=20, description="Distribyutor korxona kodi")
    name: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., min_length=9, max_length=20)
    sms_code: str = Field(..., min_length=4, max_length=10)
    password: str = Field(..., min_length=6, max_length=128)
    device_id: str = Field(..., min_length=8, max_length=100)
    platform: Optional[str] = Field(None, max_length=20)
    model: Optional[str] = Field(None, max_length=100)
    app_version: Optional[str] = Field(None, max_length=20)

    @field_validator("phone")
    @classmethod
    def _digits(cls, v: str) -> str:
        d = v.strip().replace("+", "").replace(" ", "").replace("-", "")
        if not d.isdigit() or not (9 <= len(d) <= 15):
            raise ValueError("Telefon raqami noto'g'ri")
        return v


class AgentLoginIn(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)
    password: str = Field(..., min_length=1, max_length=128)
    device_id: str = Field(..., min_length=8, max_length=100)
    platform: Optional[str] = Field(None, max_length=20)
    model: Optional[str] = Field(None, max_length=100)
    app_version: Optional[str] = Field(None, max_length=20)


class AgentRefreshIn(BaseModel):
    refresh_token: str


class AgentCategoriesIn(BaseModel):
    category_ids: List[int] = Field(..., min_length=1, max_length=50)


class ProductIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    price: Decimal = Field(..., gt=0, max_digits=18, decimal_places=2)
    qty: Decimal = Field(0, ge=0, max_digits=18, decimal_places=2)
    category_id: int
    barcode: Optional[str] = Field(None, max_length=100)
    sku: Optional[str] = Field(None, max_length=100)
    images: List[str] = Field(default_factory=list, max_length=8)
    submit: bool = Field(True, description="True — darhol tekshiruvga yuboriladi, False — qoralama")
    preferred_warehouse_id: Optional[int] = Field(None, description="Agent topshirmoqchi bo'lgan ombor (ixtiyoriy)")


class ProductUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    price: Optional[Decimal] = Field(None, gt=0, max_digits=18, decimal_places=2)
    qty: Optional[Decimal] = Field(None, ge=0, max_digits=18, decimal_places=2)
    category_id: Optional[int] = None
    barcode: Optional[str] = Field(None, max_length=100)
    sku: Optional[str] = Field(None, max_length=100)
    images: Optional[List[str]] = Field(None, max_length=8)
    submit: bool = True
    preferred_warehouse_id: Optional[int] = None


class RejectIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


class AgentStatusIn(BaseModel):
    status: str = Field(..., pattern="^(active|blocked|pending)$")
    reason: Optional[str] = Field(None, max_length=300)


class ApproveIn(BaseModel):
    # T3.17: tasdiqlashda kirim qilinadigan ombor (berilmasa — tanlangan/standart ombor)
    warehouse_id: Optional[int] = None
    receive_stock: bool = True


class ReceiveIn(BaseModel):
    warehouse_id: int


class PayoutIn(BaseModel):
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=2)
    wallet_id: int
    payment_type: Literal["cash", "card"] = "cash"
    note: Optional[str] = Field(None, max_length=300)
