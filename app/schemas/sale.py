from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator  # type: ignore

from app.models.sale import PaymentType, SaleStatus  # type: ignore


class SaleItemCreate(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    quantity: Decimal
    unit_price: Optional[Decimal] = None  # None bo'lsa mahsulot narxidan oladi
    # T3.19: kassir narxni qo'lda o'zgartirdimi (True — unit_price saqlanadi, False — server ro'yxat narxi,
    # None — eski klient: ro'yxat narxiga teng narx individual narx bilan almashtiriladi)
    price_manual: Optional[bool] = None
    discount: Decimal = Decimal("0")
    # T4.3: qo'llangan aksiya — server faollik/sana/filial/mahsulot bo'yicha tekshiradi (mos kelmasa 400).
    # Aksiya ulushi `discount` ICHIDA (qo'shimcha chegirma emas): promotion_discount = min(server hisobi, discount)
    promotion_id: Optional[int] = None
    warehouse_id: Optional[int] = None    # Desktop POS har item uchun sklad yuboradi
    currency_code: Optional[str] = "UZS"
    exchange_rate: Optional[Decimal] = Decimal("1.0")
    # Har bir sotilgan birlik uchun skanerlangan Data Matrix (markirovka) kodi.
    # Markirovka talab qilinadigan mahsulotlar uchun uzunligi quantity ga teng bo'lishi shart.
    marking_codes: Optional[List[str]] = None

    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("Miqdor musbat bo'lishi kerak")
        return v

    @field_validator("discount")
    @classmethod
    def discount_not_negative(cls, v):
        if v < 0:
            raise ValueError("Chegirma manfiy bo'lishi mumkin emas")
        return v

class PaymentItem(BaseModel):
    type: PaymentType
    amount: Decimal
    currency: Optional[str] = "UZS"
    rate: Optional[Decimal] = Decimal("1.0")
    # T3.18: provayder (click/payme/uzum) tranzaksiya raqami va filial to'lov terminali
    reference: Optional[str] = Field(None, max_length=64)
    terminal_id: Optional[int] = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v):
        if v <= 0:
            raise ValueError("To'lov miqdori musbat bo'lishi kerak")
        return v


class DeliveryIn(BaseModel):
    """Ulgurji sotuvni yetkazib berish. enabled=False — mavjud yetkazmani
    bekor qiladi (tahrirlashda). Bo'sh manzil/koordinata mijozdan olinadi."""
    enabled: bool = True
    address: Optional[str] = Field(None, max_length=500)
    lat: Optional[Decimal] = Field(None, ge=-90, le=90)
    lng: Optional[Decimal] = Field(None, ge=-180, le=180)
    contact_phone: Optional[str] = Field(None, max_length=32)
    delivery_fee: Decimal = Field(Decimal("0"), ge=0)
    planned_date: Optional[date] = None
    note: Optional[str] = Field(None, max_length=1000)


class SaleCreate(BaseModel):
    items: List[SaleItemCreate]
    payment_type: PaymentType
    # Umumiy to'langan summa
    paid_amount: Decimal
    # To'lov turlari bo'yicha alohida maydonlar (POS dan keladi)
    paid_cash: Decimal = Decimal("0")
    paid_card: Decimal = Decimal("0")
    paid_uzcard: Decimal = Decimal("0")
    paid_humo: Decimal = Decimal("0")
    paid_click: Decimal = Decimal("0")
    paid_payme: Decimal = Decimal("0")
    paid_uzum: Decimal = Decimal("0")
    paid_cashback: Decimal = Decimal("0")   # Mijoz bonus_balance dan to'lov
    # Ko'p to'lovli format (ixtiyoriy, yuqoridagi maydonlardan ustun turadi)
    payments: Optional[List[PaymentItem]] = []
    discount_amount: Decimal = Decimal("0")
    # Sotuv holati: POS "completed" yubora oladi (ulgurji uchun "pending")
    status: Optional[str] = None

    @field_validator("discount_amount")
    @classmethod
    def total_discount_not_negative(cls, v):
        if v < 0:
            raise ValueError("Umumiy chegirma manfiy bo'lishi mumkin emas")
        return v
    note: Optional[str] = None
    customer_id: Optional[int] = None
    currency_id: Optional[int] = None
    loyalty_points_used: int = 0
    warehouse_id: Optional[int] = None
    debt_due_date: Optional[date] = None
    # Qarz miqdori (POS dan debt_amount ham kelishi mumkin)
    debt_amount: Optional[Decimal] = None
    # Valyutalar kesimida qarzlar (Ulgurji sotuvdan keladi)
    currency_totals: Optional[dict] = None
    wallet_id: Optional[int] = None
    # Faqat /sales/return uchun: qaytarilayotgan asl sotuv (T0.31)
    original_sale_id: Optional[int] = None
    # Oflayn POS uchun: sotuv qilingan haqiqiy vaqt (server vaqti emas)
    created_at: Optional[datetime] = None
    # Oflayn POS: lokal UUID (takroriy yuborishlarni oldini olish)
    local_id: Optional[str] = None
    # Ulgurji sotuvdan yetkazib berish (ixtiyoriy)
    delivery: Optional[DeliveryIn] = None
    # T4.6: limitdan oshgan chegirma/narx/qaytarish uchun tasdiqlangan so'rov (menejer tasdig'i)
    approval_id: Optional[int] = None

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v):
        if not v:
            raise ValueError("Savdo elementi bo'sh bo'lishi mumkin emas")
        return v


class SaleItemOut(BaseModel):
    id: int
    product_id: int
    variant_id: Optional[int] = None
    product_name: str
    sku: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    cost_price: Optional[Decimal] = None   # kassir uchun yashiriladi (None)
    discount: Decimal
    promotion_id: Optional[int] = None            # T4.3: qo'llangan aksiya
    promotion_discount: Optional[Decimal] = None  # T4.3: chegirma ichidagi aksiya ulushi
    subtotal: Decimal
    returned_quantity: Optional[Decimal] = Decimal("0")
    unit: Optional[str] = "dona"           # O'lchov birligi (kg, litr, dona...)
    warehouse_id: Optional[int] = None      # Qaysi ombordan sotildi
    warehouse_name: Optional[str] = None    # Ombor nomi
    currency_code: Optional[str] = "UZS"
    exchange_rate: Optional[Decimal] = Decimal("1.0")

    model_config = {"from_attributes": True}

class SalePaymentOut(BaseModel):
    id: int
    payment_type: PaymentType
    amount: Decimal
    reference: Optional[str] = None
    terminal_id: Optional[int] = None

    model_config = {"from_attributes": True}


class SaleOut(BaseModel):
    id: int
    number: str
    cashier_id: int
    cashier_name: str
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None  # Chekda mijoz ismini ko'rsatish uchun
    total_amount: Decimal
    discount_amount: Decimal
    paid_amount: Decimal
    paid_cash: Decimal
    paid_card: Decimal
    paid_cashback: Decimal = Decimal("0")
    payment_type: PaymentType
    status: SaleStatus
    note: Optional[str]
    items: List[SaleItemOut]
    payments: List[SalePaymentOut] = []
    created_at: datetime
    debt_due_date: Optional[date] = None
    warehouse_id: Optional[int] = None
    # T1.9: sotuv filiali (snapshot) va uning rekvizitlari — chek uchun
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    branch_address: Optional[str] = None
    branch_phone: Optional[str] = None
    # T4.2: filial yuridik nomi va STIR
    branch_legal_name: Optional[str] = None
    branch_stir: Optional[str] = None
    # T3.7: chek uchun ombor va korxona nomi
    warehouse_name: Optional[str] = None
    company_name: Optional[str] = None
    currency_code: Optional[str] = "UZS"
    exchange_rate: Optional[Decimal] = Decimal("1.0")
    debt_amounts: Optional[dict] = None
    before_debt_balances: Optional[dict] = None
    # Fiskal chek ma'lumotlari (Hippo Communicator natijasi)
    fiscal_sign: Optional[str] = None
    fiscal_qr_url: Optional[str] = None
    fiscal_receipt_seq: Optional[int] = None
    fiscal_transaction_id: Optional[str] = None
    fiscal_at: Optional[datetime] = None
    fiscal_factory_id: Optional[str] = None
    delivery: Optional[dict] = None
    # Qaytarish hujjati (R...) uchun asl sotuv (T0.30)
    original_sale_id: Optional[int] = None

    model_config = {"from_attributes": True}


class SaleFiscalUpdate(BaseModel):
    """PATCH /sales/{id}/fiscal — faqat fiskal maydonlarni yangilaydi."""
    fiscal_sign: Optional[str] = Field(None, max_length=64)
    fiscal_qr_url: Optional[str] = Field(None, max_length=2000)
    fiscal_receipt_seq: Optional[int] = Field(None, ge=0, le=2147483647)
    fiscal_transaction_id: Optional[str] = Field(None, max_length=64)
    fiscal_at: Optional[datetime] = None
    fiscal_factory_id: Optional[str] = Field(None, max_length=64)


class SaleListOut(BaseModel):
    id: int
    number: str
    cashier_name: str
    total_amount: Decimal
    discount_amount: Decimal
    paid_amount: Decimal
    paid_cash: Decimal
    paid_card: Decimal
    paid_cashback: Decimal = Decimal("0")
    payment_type: PaymentType
    status: SaleStatus
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    items_count: int
    created_at: datetime
    debt_due_date: Optional[date] = None
    currency_code: Optional[str] = "UZS"
    debt_amounts: Optional[dict] = None
    before_debt_balances: Optional[dict] = None
    delivery_status: Optional[str] = None
    # Qaytarish hujjati (R...) uchun asl sotuv (T0.30)
    original_sale_id: Optional[int] = None
    # T1.9: sotuv filiali (snapshot)
    branch_id: Optional[int] = None
    branch_name: Optional[str] = None
    # T3.7: POS chekni qo'shimcha so'rovsiz chiqarishi uchun filial rekvizitlari
    branch_address: Optional[str] = None
    branch_phone: Optional[str] = None
    branch_legal_name: Optional[str] = None   # T4.2
    branch_stir: Optional[str] = None         # T4.2
    warehouse_name: Optional[str] = None
    company_name: Optional[str] = None

    model_config = {"from_attributes": True}


class SaleUpdate(BaseModel):
    status: Optional[SaleStatus] = None
    note: Optional[str] = None
    paid_amount: Optional[Decimal] = None
    # Full edit fields
    items: Optional[List[SaleItemCreate]] = None
    payment_type: Optional[PaymentType] = None
    paid_cash: Optional[Decimal] = None
    paid_card: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    customer_id: Optional[int] = None
    payments: Optional[List[PaymentItem]] = None
    debt_due_date: Optional[date] = None
    warehouse_id: Optional[int] = None
    currency_totals: Optional[dict] = None
    currency_id: Optional[int] = None
    currency_code: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    delivery: Optional[DeliveryIn] = None


class PartialReturnItem(BaseModel):
    sale_item_id: int
    quantity: Decimal
    
    @field_validator("quantity")
    @classmethod
    def qty_positive(cls, v):
        if v <= 0:
            raise ValueError("Qaytarish miqdori musbat bo'lishi kerak")
        return v

class SaleAssignCustomer(BaseModel):
    customer_id: int


class SaleReturnRequest(BaseModel):
    items: List[PartialReturnItem]
    payment_type: PaymentType = PaymentType.cash
    note: Optional[str] = None
    # Ixtiyoriy: pul chiqadigan kassa va tovar qaytadigan ombor (T0.31)
    wallet_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    # T4.6: limitdan katta qaytarish uchun tasdiqlangan so'rov
    approval_id: Optional[int] = None

class SaleBulkCreate(BaseModel):
    sales: List[SaleCreate]


class SalePage(BaseModel):
    """GET /sales/?with_total=true javob shakli."""
    items: List["SaleListOut"]
    total: int

