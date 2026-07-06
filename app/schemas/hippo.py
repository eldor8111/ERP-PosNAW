import enum
from typing import Optional

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
    name: str = Field(..., description="Maxsulot name")
    mxik_code: Optional[str] = Field(None, description="MXIK code")
    package_code: Optional[int] = Field(None, description="Sotuvchi talgan paket kodi")
    barcode: Optional[str] = None
    price: int = Field(..., description="Maxsulot narxi so'mda")
    quantity: int = Field(..., gt=0, description="Sanoq")
    vat_percent: Optional[float] = Field(12, description="QQS foizi")
    discount: Optional[int] = Field(0, description="Qator bo'uyicha chigirma, so'mda")
    unit: Optional[str] = Field("dona", description="Maxsulot birligi")


# CHek (Receipt)

class ReceiptRequestModel(BaseModel):
    type: ReceiptType = ReceiptType.sale
    operation: OperationType = OperationType.sale
    received_cash: Optional[int] = Field(0, description="Naqd qabul qilingan so'mma")
    received_card: Optional[int] = Field(0, description="Karta orqali qabul qilingan so'mma")
    time: Optional[str] = Field(None,
                                description="YYYY-MM-DD HH:MM:SS. Server yuboriladi, lekin server o'z vaqtini ishlatadi")


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
