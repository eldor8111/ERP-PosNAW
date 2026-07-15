import enum
from typing import List, Optional

from pydantic import BaseModel, Field


# Enumlar(API hujjatidagi sanab o'tilgan ma'lumotlar)

class ReceiptType(int, enum.Enum):
    sale = 0
    advance = 1
    credit = 2


class OperationType(int, enum.Enum):
    sale = 0
    refund = 1


class FiscalStatus(int, enum.Enum):
    failed = 0
    success = 1


# CHek qatorlari

class ReceiptItemModel(BaseModel):
    name: str = Field(..., description="Mahsulot nomi")
    barcode: Optional[str] = Field("", description="Shtrix-kod")
    labels: Optional[List[str]] = Field(default_factory=list, description="Markirovka belgilari")
    spic: Optional[str] = Field(None, description="IKPU/SPIC kodi")
    package_code: Optional[str] = Field(None, description="Qadoq kodi (IKPU)")
    quantity: int = Field(..., gt=0, description="Miqdor (dona)")
    price: int = Field(..., description="Dona narxi, so'mda")
    discount: Optional[int] = Field(0, description="Mahsulot chegirmasi, so'mda")
    vat_percent: Optional[int] = Field(12, description="QQS foizi, masalan 12")


# CHek (Receipt)

class ReceiptRequestModel(BaseModel):
    time: Optional[str] = Field(None,
                                description="YYYY-MM-DD HH:MM:SS. Server qabul qiladi, lekin o'z vaqtini ishlatadi")
    receivedCash: Optional[int] = Field(0, description="Naqd qabul qilingan so'mma, so'mda")
    received_card: Optional[int] = Field(0, description="Karta orqali qabul qilingan so'mma, so'mda")
    discount: Optional[int] = Field(0, description="Chek darajasidagi chegirma, so'mda (itemlarga taqsimlanadi)")
    type: ReceiptType = ReceiptType.sale
    operation: OperationType = OperationType.sale
    items: Optional[List[ReceiptItemModel]] = Field(default_factory=list, description="Chek qatorlari")


class RegisterReceiptRequest(BaseModel):
    factory_id: str = Field(..., description="Fiskal qurilma factory_id raqami")
    receipt: ReceiptRequestModel


class ReceiptDTO(BaseModel):
    id: Optional[int] = None
    factory_id: Optional[str] = None
    fiscal_sign: Optional[str] = None
    fiscal_status: Optional[FiscalStatus] = None
    qr_code_url: Optional[str] = None
    receipt_pdf_base64_content: Optional[str] = None
    acknowledged: Optional[bool] = None
    created_at: Optional[str] = None

    class Config:
        extra = "allow"


class ReceiptGetRequest(BaseModel):
    factory_id: str
    receipt_index: int = Field(0, description="0=oxirgi, 1=undan oldingi, ...")


class PrintReceiptRequest(BaseModel):
    id: int = Field(..., description="Lokal bazadagi chek idsi")


# Fiskla modul

class FiscalDriveDTO(BaseModel):
    factory_id: Optional[str] = None
    status: Optional[str] = None

    class Config:
        extra = "allow"


class FiscalModuleSyncRequest(BaseModel):
    factory_id: str


# Z-report

class ZReportRequest(BaseModel):
    factory_id: str


class ZReportDTO(BaseModel):
    index: Optional[int] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    total_sale: Optional[int] = None
    total_refund: Optional[int] = None

    class Config:
        extra = "allow"


class CurrentShiftDTO(BaseModel):
    class Config:
        extra = "allow"


# Sync

class SyncRequestModel(BaseModel):
    factory_id: str
    items_count: int = Field(50, gt=0)


class SyncResultDTO(BaseModel):
    class Config:
        extra = "allow"


# Sozlamalar

class SettingsDTO(BaseModel):
    class Config:
        extra = "allow"


class UpdateSettingsRequestModel(BaseModel):
    class Config:
        extra = "allow"
