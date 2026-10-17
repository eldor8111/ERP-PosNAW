import re
from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator  # type: ignore


class BranchContextBranch(BaseModel):
    id: int
    name: str


class BranchContextOut(BaseModel):
    """T1.1: GET /branches/my-context javobi."""
    branches: List[BranchContextBranch]
    current_branch_id: Optional[int] = None
    assigned_branch_id: Optional[int] = None
    can_select_all: bool
    can_switch: bool
    needs_branch_assignment: bool


def _strip_name(v):
    """T1.13: nomning chetidagi probellar olib tashlanadi; bo'sh/faqat probel nom min_length=1 bilan rad etiladi."""
    return v.strip() if isinstance(v, str) else v


# T4.2: filial rekvizitlari validatsiyasi
TAX_REGIMES = ("vat", "turnover")
WEEK_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _blank_to_none(v):
    """Bo'sh satr/probel -> None (maydonni bo'shatish uchun)."""
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _check_stir(v):
    """STIR 9 xonali, JSHSHIR 14 xonali raqam; boshqa uzunlik/belgi — 422."""
    v = _blank_to_none(v)
    if v is None:
        return None
    if not (isinstance(v, str) and v.isascii() and v.isdigit() and len(v) in (9, 14)):
        raise ValueError("STIR 9 xonali (JSHSHIR 14 xonali) raqam bo'lishi kerak")
    return v


def _check_tax_regime(v):
    v = _blank_to_none(v)
    if v is None:
        return None
    v = str(v).lower()
    if v not in TAX_REGIMES:
        raise ValueError("Soliq rejimi 'vat' yoki 'turnover' bo'lishi kerak")
    return v


def _check_working_hours(v):
    """{'mon': {'open': '09:00', 'close': '18:00', 'closed': False}, ...} — noma'lum kun/vaqt formati 422."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise ValueError("Ish vaqti obyekt bo'lishi kerak")
    out = {}
    for day, row in v.items():
        if day not in WEEK_DAYS:
            raise ValueError(f"Noma'lum hafta kuni: {day}")
        if not isinstance(row, dict):
            raise ValueError("Ish vaqti qatori obyekt bo'lishi kerak")
        closed = bool(row.get("closed", False))
        opn, cls = _blank_to_none(row.get("open")), _blank_to_none(row.get("close"))
        for t in (opn, cls):
            if t is not None and not (isinstance(t, str) and _HHMM.match(t)):
                raise ValueError("Vaqt HH:MM ko'rinishida bo'lishi kerak")
        if not closed and opn and cls and opn >= cls:
            raise ValueError("Ochilish vaqti yopilish vaqtidan oldin bo'lishi kerak")
        out[day] = {"open": opn, "close": cls, "closed": closed}
    return out


class BranchCreate(BaseModel):
    # T1.13: uzunliklar bazadagi ustunlarga mos (String(100)/(200)/(20)) — oshsa 500 emas, 422
    name: str = Field(min_length=1, max_length=100)
    address: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=20)
    company_id: Optional[int] = None
    # T4.2: rekvizitlar (ixtiyoriy)
    code: Optional[str] = Field(default=None, max_length=20)
    legal_name: Optional[str] = Field(default=None, max_length=200)
    stir: Optional[str] = None
    tax_regime: Optional[str] = None
    working_hours: Optional[dict] = None
    # T1.4: filial bilan birga default ombor va kassa yaratish (eski klientlar uchun default yoqilgan)
    create_warehouse: bool = True
    create_wallet: bool = True
    warehouse_name: Optional[str] = None
    wallet_name: Optional[str] = None

    _strip_name = field_validator("name", mode="before")(_strip_name)
    _blank_code = field_validator("code", "legal_name", mode="before")(_blank_to_none)
    _v_stir = field_validator("stir", mode="before")(_check_stir)
    _v_regime = field_validator("tax_regime", mode="before")(_check_tax_regime)
    _v_hours = field_validator("working_hours", mode="before")(_check_working_hours)


class BranchUpdate(BaseModel):
    # Bo'sh/faqat probel nom PATCH da router tomonidan 400 qaytariladi (T0.8 shartnomasi), uzunlik -> 422
    name: Optional[str] = Field(default=None, max_length=100)
    address: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=20)
    is_active: Optional[bool] = None
    # T4.2: rekvizitlar. PATCH `exclude_unset` bilan ishlaydi: null yuborilsa maydon bo'shatiladi
    code: Optional[str] = Field(default=None, max_length=20)
    legal_name: Optional[str] = Field(default=None, max_length=200)
    stir: Optional[str] = None
    tax_regime: Optional[str] = None
    working_hours: Optional[dict] = None
    # T0.8: company_id olib tashlandi — filialni boshqa korxonaga ko'chirib bo'lmaydi
    # (eski klient yuborsa Pydantic uni e'tiborsiz qoldiradi)

    _strip_name = field_validator("name", mode="before")(_strip_name)
    _blank_code = field_validator("code", "legal_name", mode="before")(_blank_to_none)
    _v_stir = field_validator("stir", mode="before")(_check_stir)
    _v_regime = field_validator("tax_regime", mode="before")(_check_tax_regime)
    _v_hours = field_validator("working_hours", mode="before")(_check_working_hours)


class BranchReceiptTemplates(BaseModel):
    """T4.2: PUT /branches/{id}/receipt_templates tanasi — korxona shabloni bilan bir xil tuzilma."""
    r58: Optional[dict] = None
    r80: Optional[dict] = None
    nak: Optional[dict] = None


class BranchOut(BaseModel):
    id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    # T4.2
    code: Optional[str] = None
    legal_name: Optional[str] = None
    stir: Optional[str] = None
    tax_regime: Optional[str] = None
    working_hours: Optional[dict] = None
    has_receipt_templates: bool = False
    # T1.4
    is_main: bool = False
    default_warehouse_id: Optional[int] = None
    warehouse_count: int = 0
    # T3.1: faol omborlar va faol xodimlar soni (filial kartasi uchun)
    warehouses_count: Optional[int] = None
    users_count: Optional[int] = None
    # T1.12: yopilgan (arxivlangan) filial izi
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _fill_has_templates(cls, data):
        """ORM Branch uchun `has_receipt_templates` (JSON tanasi ro'yxatda qaytarilmaydi)."""
        if not isinstance(data, dict) and hasattr(data, "receipt_templates"):
            tpl = getattr(data, "receipt_templates", None)
            return {
                **{k: getattr(data, k, None) for k in cls.model_fields if k != "has_receipt_templates" and hasattr(data, k)},
                "has_receipt_templates": bool(tpl and any(tpl.values())),
            }
        return data


class BranchCreateOut(BranchOut):
    """T1.4: POST /branches javobi — yaratilgan default ombor va kassa id'lari."""
    warehouse_id: Optional[int] = None
    wallet_id: Optional[int] = None


class BranchArchive(BaseModel):
    """T1.12: POST /branches/{id}/archive so'rovi."""
    reason: Optional[str] = Field(default=None, max_length=255)
    # Faol xodimlar shu filialga ko'chiriladi (berilmasa faol xodim bloker hisoblanadi)
    reassign_users_to_branch_id: Optional[int] = None


BRANCH_REASSIGN_MAX_IDS = 1000


class BranchReassignIn(BaseModel):
    """T4.5: POST /branches/reassign — mijoz/xodim/ombor/kassalarni ommaviy filialga ko'chirish.
    `to_branch_id=null` faqat `warehouses` uchun (filialdan ajratish)."""
    entity: Literal["customers", "users", "warehouses", "wallets"]
    ids: List[int] = Field(min_length=1, max_length=BRANCH_REASSIGN_MAX_IDS)
    to_branch_id: Optional[int] = None
