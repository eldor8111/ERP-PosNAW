import enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Enumlar ───────────────────────────────────────────────────────────────────

class ReceiptType(int, enum.Enum):
    sale    = 0
    advance = 1
    credit  = 2


class OperationType(int, enum.Enum):
    sale   = 0
    refund = 1


class FiscalStatus(int, enum.Enum):
    failed  = 0
    success = 1


# ── Chek qatorlari ───────────────────────────────────────────────────────────

class ReceiptItemModel(BaseModel):
    """
    UC formatiga mos chek qatori.

    UC maydon nomlari:
        classCode   = MXIK/SPIC kodi     (bizda: spic)
        packageCode = qadoq kodi          (bizda: package_code)
        amount      = miqdor (dona)       (bizda: quantity)
        vatPercent  = QQS %               (bizda: vat_percent)
        label       = markirovka (string) (bizda: labels[0])
        vat         = hisoblangan QQS     (avtomatik hisoblanadi)
        ownerType   = 0=o'z, 1=komissioner
    """
    name:         str             = Field(..., description="Mahsulot nomi")
    barcode:      Optional[str]   = Field("", description="Shtrix-kod")
    spic:         Optional[str]   = Field("", description="MXIK/classCode kodi")
    package_code: Optional[str]   = Field("", description="Qadoq kodi (packageCode)")
    labels:       Optional[List[str]] = Field(default_factory=list, description="Markirovka kodlari")
    quantity:     int             = Field(..., gt=0, description="Miqdor (dona) — UC: amount")
    price:        int             = Field(..., description="Dona narxi, so'mda")
    discount:     Optional[int]   = Field(0, description="Mahsulot chegirmasi, so'mda")
    vat_percent:  Optional[int]   = Field(12, description="QQS foizi — UC: vatPercent")
    # UC qo'shimcha maydonlar (ixtiyoriy)
    owner_type:   Optional[int]   = Field(0, description="0=o'z tovar, 1=komissioner — UC: ownerType")
    commission_tin: Optional[str] = Field(None, description="Komissioner STIR — UC: commissionTIN")


# ── Chek (Receipt) ────────────────────────────────────────────────────────────

class ReceiptRequestModel(BaseModel):
    """
    UC `params` bloki bilan mos chek modeli.

    UC da pul maydonlari:
        receivedCash  = naqd (camelCase)
        receivedCard  = karta (camelCase, bizda received_card ham qabul qilinadi)
    """
    time:           Optional[str]  = Field(None, description="YYYY-MM-DD HH:MM:SS (ixtiyoriy)")
    receivedCash:   Optional[int]  = Field(0, description="Naqd qabul qilingan so'mma — UC: receivedCash")
    received_card:  Optional[int]  = Field(0, description="Karta orqali so'mma — UC: receivedCard")
    discount:       Optional[int]  = Field(0, description="Chek darajasidagi chegirma, so'mda")
    type:           ReceiptType    = ReceiptType.sale
    operation:      OperationType  = OperationType.sale
    items:          Optional[List[ReceiptItemModel]] = Field(default_factory=list, description="Chek qatorlari")


class RegisterReceiptRequest(BaseModel):
    factory_id: str             = Field(..., description="Fiskal qurilma factory_id raqami")
    receipt:    ReceiptRequestModel


# ── Chek DTO ──────────────────────────────────────────────────────────────────

class ReceiptDTO(BaseModel):
    id:                          Optional[int]         = None
    factory_id:                  Optional[str]         = None
    fiscal_sign:                 Optional[str]         = None
    fiscal_status:               Optional[FiscalStatus] = None
    qr_code_url:                 Optional[str]         = None
    receipt_pdf_base64_content:  Optional[str]         = None
    acknowledged:                Optional[bool]        = None
    created_at:                  Optional[str]         = None

    class Config:
        extra = "allow"


class ReceiptGetRequest(BaseModel):
    factory_id:    str
    receipt_index: int = Field(0, description="0=oxirgi, 1=undan oldingi, ...")


class PrintReceiptRequest(BaseModel):
    id: int = Field(..., description="Lokal bazadagi chek idsi")


# ── Fiskal modul ─────────────────────────────────────────────────────────────

class FiscalDriveDTO(BaseModel):
    factory_id: Optional[str] = None
    status:     Optional[str] = None

    class Config:
        extra = "allow"


class FiscalModuleSyncRequest(BaseModel):
    factory_id: str


# ── Z-report ─────────────────────────────────────────────────────────────────

class ZReportRequest(BaseModel):
    factory_id: str


class ZReportDTO(BaseModel):
    index:        Optional[int] = None
    opened_at:    Optional[str] = None
    closed_at:    Optional[str] = None
    total_sale:   Optional[int] = None
    total_refund: Optional[int] = None

    class Config:
        extra = "allow"


class CurrentShiftDTO(BaseModel):
    class Config:
        extra = "allow"


# ── Sync ──────────────────────────────────────────────────────────────────────

class SyncRequestModel(BaseModel):
    factory_id:  str
    items_count: int = Field(50, gt=0)


class SyncResultDTO(BaseModel):
    class Config:
        extra = "allow"


# ── Sozlamalar ────────────────────────────────────────────────────────────────

class SettingsDTO(BaseModel):
    class Config:
        extra = "allow"


class UpdateSettingsRequestModel(BaseModel):
    class Config:
        extra = "allow"


# ── Markirovka ────────────────────────────────────────────────────────────────

class LabelValidationRequest(BaseModel):
    marking:    str = Field(..., description="Markirovka kodi")
    class_code: str = Field(..., description="MXIK/classCode")


class OnlineLabelValidationRequest(BaseModel):
    marking:       str           = ""
    class_code:    str           = ""
    package_code:  str           = ""
    commitent_tin: Optional[str] = None
    owner_tin:     Optional[str] = None


class MultipleLabelItem(BaseModel):
    marking:    str
    class_code: str


class MultipleLabelValidationRequest(BaseModel):
    markings: List[MultipleLabelItem] = Field(..., min_length=1)
