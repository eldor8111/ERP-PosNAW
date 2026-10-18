"""
Customers API: CRM module for managing customers, debt and loyalty.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Response  # type: ignore
from sqlalchemy import func, or_, text  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy.exc import SQLAlchemyError  # type: ignore
from pydantic import BaseModel, Field, field_validator, model_validator  # type: ignore
from app.utils.translit import name_phone_search_filter  # type: ignore
from app.utils.import_errors import row_db_error  # type: ignore
from decimal import Decimal
from sqlalchemy.orm.attributes import flag_modified  # type: ignore

from app.database import get_db  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.customer_prices import CustomerPrice  # type: ignore
from app.core.audit import log_action  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.services.customer_service import lock_customer  # type: ignore
from app.services import customer_ledger as ledger  # type: ignore  # T2.6: yagona qarz servisi/jurnali
from app.core.branch_context import BranchContext, get_branch_context  # type: ignore
from app.utils.loyalty_card import normalize_card  # type: ignore
from app.services.loyalty_service import get_loyalty_rules, tier_for  # type: ignore
from app.models.moliya import Wallet  # type: ignore
from app.models.currency import Currency  # type: ignore
from app.models.company import Company  # type: ignore
from app.services.branch_helpers import get_active_branch, active_branch_id  # type: ignore

def parse_decimal_clean(val) -> Optional[Decimal]:
    if val is None or str(val).strip() == "":
        return None
    s = str(val).strip().replace(" ", "").replace("\xa0", "")
    
    # If there are both dots and commas:
    if "." in s and "," in s:
        if s.index(",") < s.index("."):
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        parts = s.split(",")
        if len(parts) > 2:
            s = s.replace(",", "")
        else:
            if len(parts[1]) == 3:
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2:
            s = s.replace(".", "")

    try:
        return Decimal(s)
    except Exception:
        raise ValueError(f"'{val}' noto'g'ri son formati")

router = APIRouter(prefix="/customers", tags=["customers"])
logger = logging.getLogger(__name__)

CUSTOMER_TYPES = ("retail", "distributor")

# T0.26: mijozning moliyaviy maydonlari bo'yicha rollar (namuna: suppliers.py DEBT_ADJUST_ROLES).
# super_admin require_roles'da avtomatik o'tadi; qo'lda tekshiruvda _has_role() hisobga oladi.
CUSTOMER_DEBT_ROLES = (UserRole.admin, UserRole.director, UserRole.accountant)       # qarz, ball, o'chirish
CUSTOMER_TERMS_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant)  # limit, keshbek, narx turi
CUSTOMER_PAY_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.cashier)
CUSTOMER_BRANCH_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)

# Qarz to'lovi qabul qilinadigan haqiqiy to'lov turlari (qarz/keshbek/aralash emas).
# DIQQAT: "bank_transfer" ni olib tashlamang — KirimTolovlar.jsx (PAYMENT_TYPES) va finance.py uni
# haqiqiy tur sifatida ishlatadi. T0.29 umumiy konstantasiga o'tilganda ham bu qiymat saqlansin.
CASH_PAYMENT_TYPES = ledger.CASH_PAYMENT_TYPES

# Mijoz tarixida jurnaldan ko'rsatiladigan qarz harakatlari (sotuv/qaytarish/to'lov alohida ko'rsatiladi)
HISTORY_DEBT_LOG_KINDS = ("opening", "edit", "writeoff", "delivery_fee", "ai", "recalc")
DEBT_LOG_LABELS = {
    "opening": "Boshlang'ich qarz", "edit": "Qarz tahriri", "writeoff": "Qarz hisobdan chiqarildi",
    "delivery_fee": "Yetkazish haqi", "ai": "AI orqali qarz", "recalc": "Jurnalni tuzatish",
}

# PUT orqali hech qachon yozilmaydigan maydonlar (qarz/ball) va shartlar maydonlari
DEBT_PROTECTED_FIELDS = ("debt_balance", "debt_balances", "debt_currency", "loyalty_points")
TERMS_FIELDS = ("debt_limit", "cashback_percent", "price_type", "discount_percent")


# bulk-import orqali o'zgaradigan va jurnalga yoziladigan maydonlar
BULK_TERMS_FIELDS = ("debt_limit", "cashback_percent", "loyalty_points", "bonus_balance")


def _has_role(user: User, roles) -> bool:
    return user.role == UserRole.super_admin or user.role in roles


def _check_bulk_value(field: str, val) -> None:
    """Import qiymatlari CustomerIn validatorlari bilan bir xil chegarada bo'lishi shart (CHECK cheklovlari)."""
    if field == "cashback_percent" and not (Decimal("0") <= val <= Decimal("100")):
        raise ValueError("Cashback 0-100 oralig'ida bo'lishi kerak")
    if field in ("debt_limit", "loyalty_points", "bonus_balance") and val < 0:
        raise ValueError("Qiymat manfiy bo'lmasligi kerak")


class CustomerIn(BaseModel):
    name: str
    phone: Optional[str] = None
    debt_balance: Optional[Decimal] = Decimal("0")
    debt_currency: Optional[str] = "UZS"
    debt_balances: Optional[dict] = None
    debt_limit: Optional[Decimal] = Decimal("0")
    loyalty_points: Optional[int] = 0
    card_number: Optional[str] = None
    cashback_percent: Optional[Decimal] = Field(Decimal("0"), ge=0, le=100)
    price_type: Optional[Literal["sale", "wholesale", "cost"]] = "sale"
    customer_type: Optional[str] = "retail"  # retail, distributor
    territory: Optional[str] = None
    discount_percent: Optional[Decimal] = None
    # Manzil / joylashuv va profil
    region: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[Decimal] = None
    lng: Optional[Decimal] = None
    location_source: Optional[str] = None
    extra_phones: Optional[List[str]] = None
    agent_id: Optional[int] = None
    work_days: Optional[List[int]] = None
    visit_radius_m: Optional[int] = None
    # T1.15: mijozning "uy filiali" (Telegram buyurtmalari shu filialga yo'naltiriladi)
    branch_id: Optional[int] = None
    receipt_format: Optional[str] = "text"

    @field_validator("region", "district", "address")
    @classmethod
    def text_clean(cls, v):
        if v is None:
            return None
        v = " ".join(str(v).split())
        return v or None

    @field_validator("discount_percent")
    @classmethod
    def discount_valid(cls, v):
        if v is not None and not (Decimal("0") <= v <= Decimal("100")):
            raise ValueError("Chegirma 0-100% oralig'ida bo'lishi kerak")
        return v

    @field_validator("cashback_percent")
    @classmethod
    def cashback_valid(cls, v):
        if v is not None and not (Decimal("0") <= v <= Decimal("100")):
            raise ValueError("Keshbek foizi 0-100% oralig'ida bo'lishi kerak")
        return v

    @field_validator("debt_limit")
    @classmethod
    def debt_limit_valid(cls, v):
        if v is not None and v < 0:
            raise ValueError("Kredit limit manfiy bo'lmasligi kerak")
        return v

    @field_validator("loyalty_points")
    @classmethod
    def loyalty_valid(cls, v):
        if v is not None and v < 0:
            raise ValueError("Sodiqlik ballari manfiy bo'lmasligi kerak")
        return v

    @field_validator("price_type", mode="before")
    @classmethod
    def price_type_normalize(cls, v):
        # Eski forma 'retail' yuborgan — backend narx turlari: sale / wholesale / cost
        if isinstance(v, str):
            v = v.strip().lower()
            if v in ("retail", ""):
                return "sale"
        return v

    @field_validator("lat")
    @classmethod
    def lat_valid(cls, v):
        if v is not None and not (-90 <= v <= 90):
            raise ValueError("Kenglik (lat) noto'g'ri")
        return v

    @field_validator("lng")
    @classmethod
    def lng_valid(cls, v):
        if v is not None and not (-180 <= v <= 180):
            raise ValueError("Uzunlik (lng) noto'g'ri")
        return v

    @field_validator("location_source")
    @classmethod
    def source_valid(cls, v):
        if v is not None and v not in ("map", "telegram", "manual"):
            raise ValueError("Joylashuv manbasi noto'g'ri")
        return v

    @field_validator("extra_phones")
    @classmethod
    def phones_valid(cls, v):
        if v is None:
            return None
        out = []
        for p in v:
            p = (p or "").strip()
            if not p:
                continue
            clean = p.replace("+", "").replace(" ", "").replace("-", "")
            if not clean.isdigit() or not (7 <= len(clean) <= 15):
                raise ValueError(f"Qo'shimcha telefon noto'g'ri: {p}")
            out.append(p)
        return out[:5]

    @field_validator("work_days")
    @classmethod
    def days_valid(cls, v):
        if v is None:
            return None
        if any(d not in range(1, 8) for d in v):
            raise ValueError("Ish kunlari 1 (Dushanba) dan 7 (Yakshanba) gacha bo'lishi kerak")
        return sorted(set(v))

    @field_validator("visit_radius_m")
    @classmethod
    def radius_valid(cls, v):
        if v is not None and not (0 <= v <= 100000):
            raise ValueError("Tashrif radiusi 0-100000 metr oralig'ida bo'lishi kerak")
        return v

    @field_validator("customer_type")
    @classmethod
    def type_valid(cls, v):
        v = (v or "retail").strip().lower()
        if v not in CUSTOMER_TYPES:
            raise ValueError("Mijoz turi noto'g'ri (retail yoki distributor)")
        return v

    @field_validator("territory")
    @classmethod
    def territory_clean(cls, v):
        if v is None:
            return None
        v = " ".join(str(v).split())
        return v or None

    @field_validator("card_number")
    @classmethod
    def card_valid(cls, v):
        if v is not None and str(v).strip() == "":
            return None
        return v

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v):
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            return None
        clean = stripped.replace("+", "").replace(" ", "").replace("-", "")
        if not clean.isdigit() or not (7 <= len(clean) <= 15):
            raise ValueError("Telefon raqam noto'g'ri (faqat raqamlar, 7-15 ta belgi)")
        return v


class CustomerOut(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    debt_balance: Decimal
    debt_currency: str = "UZS"
    debt_balances: Optional[dict] = {}
    debt_limit: Decimal
    loyalty_points: int
    card_number: Optional[str] = None
    cashback_percent: Decimal
    bonus_balance: Decimal = Decimal("0")
    total_spent: Decimal = Decimal("0")
    company_id: Optional[int] = None
    price_type: Optional[str] = "sale"
    discount_percent: Optional[Decimal] = Decimal("0")
    debt_edited: List[Dict[str, Any]] = []
    customer_type: str = "retail"
    territory: Optional[str] = None
    region: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    location_source: Optional[str] = None
    extra_phones: List[str] = []
    agent_id: Optional[int] = None
    work_days: List[int] = []
    visit_radius_m: Optional[int] = None
    photo_url: Optional[str] = None
    tg_connected: bool = False
    branch_id: Optional[int] = None
    receipt_format: Optional[str] = "text"

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def normalize_debts(cls, data):
        is_dict = isinstance(data, dict)

        # Attribute yoki Dict qiymatini olish
        if is_dict:
            debt_currency = data.get("debt_currency") or "UZS"
            debt_balance = data.get("debt_balance") or 0
            debt_balances = data.get("debt_balances")
        else:
            debt_currency = getattr(data, "debt_currency", "UZS") or "UZS"
            debt_balance = getattr(data, "debt_balance", 0) or 0
            debt_balances = getattr(data, "debt_balances", None)

        currency = str(debt_currency).strip().upper() or "UZS"

        if debt_balances is None:
            balances = {}
        else:
            balances = dict(debt_balances)

        # Agar debt_balances bo'sh bo'lib, jami debt_balance musbat bo'lsa
        if not balances and float(debt_balance) > 0:
            balances[currency] = float(debt_balance)

        if is_dict:
            data["debt_balances"] = balances
            data["debt_currency"] = "UZS"
        else:
            # ORM obyekt bo'lsa, xavfsiz va tez ishlashi uchun barcha kerakli fieldlar bilan yangi dict qaytaramiz
            data_dict = {
                "id": getattr(data, "id", None),
                "name": getattr(data, "name", None),
                "phone": getattr(data, "phone", None),
                "debt_balance": getattr(data, "debt_balance", Decimal("0")),
                "debt_currency": "UZS",
                "debt_balances": balances,
                "debt_limit": getattr(data, "debt_limit", Decimal("0")),
                "loyalty_points": getattr(data, "loyalty_points", 0),
                "card_number": getattr(data, "card_number", None),
                "cashback_percent": getattr(data, "cashback_percent", Decimal("0")),
                "bonus_balance": getattr(data, "bonus_balance", Decimal("0")),
                "total_spent": getattr(data, "total_spent", Decimal("0")),
                "company_id": getattr(data, "company_id", None),
                "price_type": getattr(data, "price_type", "sale"),
                "discount_percent": getattr(data, "discount_percent", Decimal("0")),
                "debt_edited": list(getattr(data, "debt_edited", None) or []),
                "customer_type": getattr(data, "customer_type", None) or "retail",
                "territory": getattr(data, "territory", None),
                "region": getattr(data, "region", None),
                "district": getattr(data, "district", None),
                "address": getattr(data, "address", None),
                "lat": float(data.lat) if getattr(data, "lat", None) is not None else None,
                "lng": float(data.lng) if getattr(data, "lng", None) is not None else None,
                "location_source": getattr(data, "location_source", None),
                "extra_phones": list(getattr(data, "extra_phones", None) or []),
                "agent_id": getattr(data, "agent_id", None),
                "work_days": list(getattr(data, "work_days", None) or []),
                "visit_radius_m": getattr(data, "visit_radius_m", None),
                "photo_url": getattr(data, "photo_url", None),
                "tg_connected": bool(getattr(data, "tg_chat_id", None)),
                "branch_id": getattr(data, "branch_id", None),
            }
            return data_dict

        return data


class PaginatedCustomersOut(BaseModel):
    items: list[CustomerOut]
    total: int
    debt_edited: List[Dict[str, Any]] = []


def _calc_debt_in_uzs(balances: dict, db: Session, currency_map: Optional[dict] = None,
                      company_id: Optional[int] = None) -> Decimal:
    """debt_balances dict va joriy kurslardan UZS ekvivalentini hisoblaydi.

    currency_map berilsa ({code: rate}), DB'ga so'rov qilinmaydi — bir
    nechta mijoz ustida ketma-ket chaqirilganda (masalan recalc-debts)
    N+1 so'rovning oldini olish uchun oldindan yuklab uzatiladi.
    T2.7: kurs company_id korxonasiniki (yo'q bo'lsa global); begona korxona kursi olinmaydi.
    """
    total = Decimal("0")
    for curr, amt in (balances or {}).items():
        if curr == "UZS":
            total += Decimal(str(amt))
        else:
            if currency_map is not None:
                rate = currency_map.get(curr, Decimal("1"))
            else:
                from app.services.currency_service import get_rate
                rate = get_rate(db, company_id, curr)
            total += Decimal(str(amt)) * rate
    return total


def _normalize_customer_balances(balances: Optional[dict], debt_balance: Decimal, debt_currency: str) -> dict:
    """Mijozning valyuta bo'yicha qarzlarini yagona formatga keltiradi."""
    result = {str(k).strip().upper(): float(v) for k, v in dict(balances or {}).items()}
    if not result and float(debt_balance or 0) > 0:
        currency = (debt_currency or "UZS").strip().upper() or "UZS"
        result = {currency: float(debt_balance)}
    return result


# Eski formalar (POS, import) yubormaydigan maydonlar — update'da faqat aniq
# yuborilgani yangilanadi, aks holda mavjud qiymat o'chib ketardi
OPTIONAL_PROFILE_FIELDS = (
    "customer_type", "territory", "discount_percent",
    "region", "district", "address", "lat", "lng", "location_source",
    "extra_phones", "agent_id", "work_days", "visit_radius_m", "branch_id",
)


def _check_agent(db: Session, company_id: int, agent_id: Optional[int]) -> None:
    if agent_id is None:
        return
    from sqlalchemy import or_
    from app.models.user_company import UserCompany
    linked = db.query(UserCompany).filter(
        UserCompany.user_id == User.id, UserCompany.company_id == company_id, UserCompany.is_active == True,  # noqa: E712
    ).exists()
    if not db.query(User.id).filter(User.id == agent_id, or_(User.company_id == company_id, linked)).first():
        raise HTTPException(status_code=404, detail="Agent (xodim) topilmadi")


def _check_territory_free(db: Session, company_id: int, customer_type: str,
                          territory: Optional[str], exclude_id: Optional[int] = None,
                          region: Optional[str] = None) -> None:
    """Bitta hududga faqat bitta distribyutor biriktiriladi (T4.7: viloyat/`region` hisobga olinadi).

    Ziddiyat: hudud nomi teng VA (viloyat teng, yoki ikkalasidan birining viloyati bo'sh).
    Turli viloyatda bir xil nomli hudud (masalan "Markaziy bozor") ruxsat etiladi."""
    if customer_type != "distributor" or not territory:
        return
    region = (region or "").strip()
    q = db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer.customer_type == "distributor",
        Customer.is_active.is_(True),
        func.lower(Customer.territory) == territory.lower(),
    )
    if region:
        q = q.filter(or_(
            func.lower(func.trim(func.coalesce(Customer.region, ""))) == region.lower(),
            func.trim(func.coalesce(Customer.region, "")) == "",
        ))
    if exclude_id:
        q = q.filter(Customer.id != exclude_id)
    busy = q.first()
    if busy:
        place = f"'{territory}' ({region})" if region else f"'{territory}'"
        raise HTTPException(
            status_code=409,
            detail=f"{place} hududiga allaqachon distribyutor biriktirilgan: {busy.name} (ID: {busy.id})",
        )


def _recalc_debt_uzs(balances: Optional[dict], db: Session, company_id: Optional[int] = None) -> Decimal:
    """debt_balances (valyuta -> summa) dan UZS ekvivalent jami qarzni hisoblaydi.
    create_customer, adjust-debt va bulk-import uchun yagona hisob (kurs company_id korxonasiniki)."""
    normalized = {str(k).strip().upper(): v for k, v in (balances or {}).items()}
    return _calc_debt_in_uzs(normalized, db, company_id=company_id)


def _append_debt_edit(cust: Customer, edited_from: dict, edited_to: dict,
                      user: Optional[User] = None, reason: Optional[str] = None) -> None:
    """Qarz tahriri tarixiga yangi yozuv qo'shadi: kim (edited_by), qaysi filialdan
    (branch_id) va nima sababdan (reason) o'zgartirgani bilan."""
    history = list(cust.debt_edited or [])
    entry = {
        "edited_from": edited_from,
        "edited_to": edited_to,
        "edited_at": datetime.now(timezone.utc).isoformat(),
    }
    if user is not None:
        entry["edited_by"] = {"id": user.id, "name": user.name}
        entry["user_id"] = user.id
        entry["branch_id"] = user.branch_id
    if reason:
        entry["reason"] = reason
    history.append(entry)
    cust.debt_edited = history
    flag_modified(cust, "debt_edited")


class PaymentInput(BaseModel):
    amount: Decimal
    currency: Optional[str] = "UZS"
    payment_type: Optional[str] = "cash"
    rate: Optional[Decimal] = None

class DebtUpdate(BaseModel):
    amount: Optional[Decimal] = Decimal("0")
    reason: str
    currency: Optional[str] = "UZS"
    wallet_id: Optional[int] = None
    payment_type: Optional[str] = "cash"
    payments: Optional[list[PaymentInput]] = None


class PointsAdjust(BaseModel):
    delta: int  # musbat = qo'shish, manfiy = ayirish
    reason: str = Field(..., min_length=3)  # majburiy: jurnalga yoziladi

    @field_validator("reason")
    @classmethod
    def reason_clean(cls, v):
        v = (v or "").strip()
        if len(v) < 3:
            raise ValueError("Sabab kamida 3 ta belgidan iborat bo'lishi kerak")
        return v


class DebtChange(BaseModel):
    currency: str = "UZS"
    delta: Decimal  # musbat = qarz oshadi, manfiy = qarz kamayadi


class DebtAdjust(BaseModel):
    reason: Optional[str] = None
    changes: List[DebtChange] = []


@router.post("/recalc-debts")
def recalc_all_debts(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*CUSTOMER_DEBT_ROLES)),
):
    """Barcha mijozlarning debt_balance ni debt_balances + joriy kurs asosida qayta hisoblaydi.
    Bu endpoint faqat bir martalik fix uchun yoki kurs o'zgarganda chaqiriladi."""
    # T2.7: faqat shu korxona kurslari (korxona qatori global qatorni bosadi); boshqa korxona kursi aralashmaydi
    from app.services.currency_service import rate_map
    currency_map = rate_map(db, current_user.company_id)

    customers = db.query(Customer).filter(
        Customer.company_id == current_user.company_id
    ).all()
    updated = 0
    for cust in customers:
        balances = dict(cust.debt_balances or {})
        if not balances:
            continue
        ledger.recompute_total(db, cust, currency_map)
        updated += 1
    log_action(db, "RECALC_DEBTS", "customer", None, user_id=current_user.id,
               new_values={"updated": updated})
    db.commit()
    return {"message": f"{updated} ta mijoz qarzi qayta hisoblandi", "updated": updated}


@router.get("", response_model=list[CustomerOut])
def list_customers(
        response: Response,
        search: Optional[str] = None,
        skip: int = Query(0, ge=0),
        page: Optional[int] = Query(None, ge=1, description="Sahifa raqami (berilsa skip = (page-1)*limit)"),
        limit: int = Query(100, ge=1, le=50000),
        customer_type: Optional[str] = Query(None),
        branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr (faqat ma'lumot filtri)"),
        card: Optional[str] = Query(None, description="Sodiqlik kartasi raqami (aniq moslik, bo'shliq/tire e'tiborsiz)"),
        agent_id: Optional[int] = Query(None, description="Biriktirilgan agent bo'yicha filtr (korxona doirasida)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    q = db.query(Customer)
    q = q.filter(Customer.company_id == current_user.company_id, Customer.is_active.is_(True))
    if customer_type:
        q = q.filter(Customer.customer_type == customer_type)
    if branch_id:
        q = q.filter(Customer.branch_id == branch_id)
    if agent_id:
        q = q.filter(Customer.agent_id == agent_id)
    if card is not None:
        # T2.12: karta bo'yicha aniq moslik (korxona doirasida); saqlangan qiymatdagi bo'shliq/tire ham e'tiborsiz
        _card = normalize_card(card)
        if not _card:
            q = q.filter(Customer.id == -1)
        else:
            _stored = func.replace(func.replace(Customer.card_number, " ", ""), "-", "")
            q = q.filter(Customer.card_number.isnot(None), _stored == _card)
    if search:
        # T3.8: POS karta skanerlaydi — qidiruv matni karta raqamiga aniq mos bo'lsa ham topiladi
        _conds = [name_phone_search_filter(Customer.name, Customer.phone, search),
                  Customer.card_number == search.strip()]
        _digits = normalize_card(search)
        if _digits:
            _stored = func.replace(func.replace(Customer.card_number, " ", ""), "-", "")
            _conds.append(_stored == _digits)
        q = q.filter(or_(*_conds))
    if page is not None:
        skip = (page - 1) * limit
    response.headers["X-Total-Count"] = str(q.count())
    items = q.order_by(Customer.name).offset(skip).limit(limit).all()
    return items


@router.get("/summary-stats")
def get_customers_summary_stats(
        branch_id: Optional[int] = Query(None, description="Filial bo'yicha (qarz jurnalidan); -1 — filialsiz"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Mijozlar bo'yicha umumiy statistik ma'lumotlarni qaytaradi."""
    if branch_id:
        # T2.6: filial doirasi — qarz `customer_debt_log` jurnalidan, mijozlar soni mijoz filiali bo'yicha
        bid, _ = ledger.check_branch_scope(db, current_user, ctx, branch_id)
        data = ledger.debt_by_branch(db, current_user.company_id, bid)
        debts_b: dict = {}
        for r in data["customers"]:
            for curr, amt in r["debts"].items():
                debts_b[curr] = debts_b.get(curr, 0) + amt
        cq = db.query(func.count(Customer.id)).filter(
            Customer.company_id == current_user.company_id, Customer.is_active.is_(True),
            Customer.branch_id.is_(None) if bid == -1 else Customer.branch_id == bid,
        )
        return {
            "total_customers": int(cq.scalar() or 0),
            "total_debt": debts_b.get("UZS", 0),
            "total_debts": debts_b,
            "total_debtors": len({r["customer"].id for r in data["customers"]}),
            "branch_id": bid,
        }
    base = (Customer.company_id == current_user.company_id, Customer.is_active.is_(True))
    if db.get_bind().dialect.name == "postgresql":
        # T3.8: mijozlar jadvali Python'ga yuklanmaydi — BITTA agregat so'rov (JSON ustun -> ::jsonb):
        #  cur — valyuta bo'yicha yig'indi (qoldig'i > 0.01); debtors — kamida bitta musbat qoldig'i bor mijozlar;
        #  fallback — debt_balances bo'sh eski qatorlar uchun UZS zaxirasi (debt_balance > 0); total — mijozlar soni
        rows = db.execute(text(
            "WITH pos AS ("
            "  SELECT c.id AS cid, e.key AS k, e.value::numeric AS v FROM customers c "
            "  CROSS JOIN LATERAL jsonb_each_text(CASE WHEN jsonb_typeof(c.debt_balances::jsonb) = 'object' "
            "    THEN c.debt_balances::jsonb ELSE '{}'::jsonb END) AS e "
            "  WHERE c.company_id = :cid AND c.is_active IS TRUE AND e.value::numeric > 0.01), "
            "fb AS ("
            "  SELECT c.debt_balance AS bal FROM customers c "
            "  WHERE c.company_id = :cid AND c.is_active IS TRUE AND c.debt_balance > 0 "
            "    AND (c.debt_balances IS NULL OR c.debt_balances::jsonb IN ('{}'::jsonb, 'null'::jsonb))) "
            "SELECT 'cur' AS kind, k AS key, SUM(v) AS amount, 0 AS cnt FROM pos GROUP BY k "
            "UNION ALL SELECT 'debtors', NULL, 0, COUNT(DISTINCT cid) FROM pos "
            "UNION ALL SELECT 'fallback', NULL, COALESCE(SUM(bal), 0), COUNT(*) FROM fb "
            "UNION ALL SELECT 'total', NULL, 0, COUNT(*) FROM customers c "
            "  WHERE c.company_id = :cid AND c.is_active IS TRUE"
        ), {"cid": current_user.company_id}).all()
        total_debts: dict = {}
        total_debtors = 0
        total_customers = 0
        fb_sum, fb_cnt = 0.0, 0
        for kind, key, amt, cnt in rows:
            if kind == "cur":
                total_debts[key] = float(amt or 0)
            elif kind == "debtors":
                total_debtors = int(cnt or 0)
            elif kind == "fallback":
                fb_sum, fb_cnt = float(amt or 0), int(cnt or 0)
            elif kind == "total":
                total_customers = int(cnt or 0)
        if fb_cnt:
            total_debts["UZS"] = total_debts.get("UZS", 0) + fb_sum
            total_debtors += fb_cnt
    else:
        # Postgres bo'lmagan muhit (test/SQLite): jsonb_each_text yo'q — Python'da hisoblash
        customers_data = db.query(Customer.debt_balance, Customer.debt_balances).filter(*base).all()
        total_customers = len(customers_data)
        total_debts = {}
        total_debtors = 0
        for c_debt_balance, c_debt_balances in customers_data:
            has_debt = False
            if c_debt_balances:
                for curr, amt in c_debt_balances.items():
                    if float(amt) > 0.01:
                        total_debts[curr] = total_debts.get(curr, 0) + float(amt)
                        has_debt = True
            elif c_debt_balance and float(c_debt_balance) > 0:
                total_debts["UZS"] = total_debts.get("UZS", 0) + float(c_debt_balance)
                has_debt = True
            if has_debt:
                total_debtors += 1

    return {
        "total_customers": total_customers,
        "total_debt": total_debts.get("UZS", 0),
        "total_debts": total_debts,
        "total_debtors": total_debtors,
    }


@router.get("/distributors-report")
def get_distributors_report(
        days: int = Query(30, ge=1, le=366),
        branch_id: Optional[int] = Query(None, description="Filial bo'yicha (-1 — filialsiz)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Distribyutorlar reytingi: davr bo'yicha xarid hajmi, qarz va kredit
    limitidan foydalanish darajasi."""
    from datetime import timedelta
    from app.models.sale import Sale
    from app.utils.report_utils import sale_doc_filter, sale_branch_filter

    cid = current_user.company_id
    bid = None
    branch_debt = None
    dq = db.query(Customer).filter(
        Customer.company_id == cid, Customer.customer_type == "distributor",
        Customer.is_active.is_(True),
    )
    if branch_id:
        # T2.6: filial doirasi — distribyutor mijoz filiali bo'yicha, qarz filial jurnalidan
        bid, _ = ledger.check_branch_scope(db, current_user, ctx, branch_id)
        dq = dq.filter(Customer.branch_id.is_(None) if bid == -1 else Customer.branch_id == bid)
        branch_debt = {}
        for r in ledger.debt_by_branch(db, cid, bid)["customers"]:
            branch_debt[r["customer"].id] = branch_debt.get(r["customer"].id, 0.0) + r["debt_uzs"]
    distributors = dq.all()
    if not distributors:
        return {"days": days, "items": [], "totals": {"count": 0, "sales": 0, "debt": 0, "over_limit": 0}}

    ids = [d.id for d in distributors]
    since = datetime.now(timezone.utc) - timedelta(days=days)
    sale_q = db.query(
        Sale.customer_id,
        func.coalesce(func.sum(Sale.total_amount), 0),
        func.count(Sale.id),
    ).filter(
        Sale.company_id == cid,
        Sale.customer_id.in_(ids),
        Sale.created_at >= since,
        sale_doc_filter(),
    )
    if bid:
        sale_q = sale_q.filter(sale_branch_filter(bid, db, cid))
    rows = sale_q.group_by(Sale.customer_id).all()
    period = {r[0]: (float(r[1] or 0), int(r[2] or 0)) for r in rows}

    last_rows = db.query(Sale.customer_id, func.max(Sale.created_at)).filter(
        Sale.company_id == cid, Sale.customer_id.in_(ids), sale_doc_filter(),
    ).group_by(Sale.customer_id).all()
    last_sale = {r[0]: r[1] for r in last_rows}

    items = []
    for d in distributors:
        sales, cnt = period.get(d.id, (0.0, 0))
        debt = branch_debt.get(d.id, 0.0) if branch_debt is not None else float(d.debt_balance or 0)
        limit = float(d.debt_limit or 0)
        usage = round(debt / limit * 100, 1) if limit > 0 else None
        items.append({
            "id": d.id,
            "name": d.name,
            "phone": d.phone,
            "territory": d.territory,
            "region": d.region,
            "price_type": d.price_type,
            "sales": sales,
            "sale_count": cnt,
            "last_sale_at": last_sale.get(d.id).isoformat() if last_sale.get(d.id) else None,
            "debt": debt,
            "debt_limit": limit,
            "limit_usage": usage,
            "over_limit": limit > 0 and debt > limit,
        })
    items.sort(key=lambda x: x["sales"], reverse=True)

    return {
        "days": days,
        "items": items,
        "totals": {
            "count": len(items),
            "sales": sum(i["sales"] for i in items),
            "debt": sum(i["debt"] for i in items),
            "over_limit": sum(1 for i in items if i["over_limit"]),
        },
    }


@router.get("/paginated", response_model=PaginatedCustomersOut)
def list_customers_paginated(
        search: Optional[str] = None,
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
        sort_by: Optional[str] = Query(None),  # debt_balance, name, id
        sort_order: Optional[str] = Query("asc"),  # asc, desc
        min_debt: Optional[Decimal] = Query(None),
        max_debt: Optional[Decimal] = Query(None),
        exact_debt: Optional[Decimal] = Query(None),
        customer_type: Optional[str] = Query(None),
        branch_id: Optional[int] = Query(None, description="Filial bo'yicha filtr (faqat ma'lumot filtri)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    q = db.query(Customer)
    q = q.filter(Customer.company_id == current_user.company_id, Customer.is_active.is_(True))
    if customer_type:
        q = q.filter(Customer.customer_type == customer_type)
    if branch_id:
        q = q.filter(Customer.branch_id == branch_id)
    if search:
        q = q.filter(
            name_phone_search_filter(Customer.name, Customer.phone, search)
        )

    if exact_debt is not None:
        q = q.filter(Customer.debt_balance == exact_debt)
    else:
        if min_debt is not None:
            q = q.filter(Customer.debt_balance >= min_debt)
        if max_debt is not None:
            q = q.filter(Customer.debt_balance <= max_debt)

    total = q.count()

    # Sorting
    if sort_by:
        col = getattr(Customer, sort_by, None)
        if col:
            if sort_order == "desc":
                q = q.order_by(col.desc())
            else:
                q = q.order_by(col.asc())
        else:
            q = q.order_by(Customer.name)
    else:
        q = q.order_by(Customer.name)

    items = q.offset(skip).limit(limit).all()

    return {
        "items": items,
        "total": total
    }


@router.post("", status_code=201, response_model=CustomerOut)
def create_customer(data: CustomerIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Telefon takrorlanishini bloklash — POS oflayn yaratilgan mijozni
    # sinxronlashda 4xx olsa, kassirga "yuborilmadi" deb korsatadi.
    # Taqqoslash normallashtirilgan (faqat raqamlar) — '+998 90 123-45-67'
    # va '998901234567' bir xil raqam deb topiladi.
    if data.phone and str(data.phone).strip():
        import re as _re
        from sqlalchemy import func as _f
        _norm = _re.sub(r"\D", "", str(data.phone))
        if _norm:
            _db_norm = _f.replace(_f.replace(_f.replace(_f.replace(_f.replace(
                Customer.phone, "+", ""), " ", ""), "-", ""), "(", ""), ")", "")
            _dup = db.query(Customer).filter(
                Customer.company_id == current_user.company_id,
                Customer.phone.isnot(None),
                _db_norm == _norm,
            ).first()
            if _dup:
                raise HTTPException(
                    status_code=409,
                    detail=f"Bu telefon raqami allaqachon mavjud: {_dup.name} (ID: {_dup.id})",
                )

    _check_territory_free(db, current_user.company_id, data.customer_type, data.territory, region=data.region)

    _check_agent(db, current_user.company_id, data.agent_id)

    # T1.15: filial berilsa — o'z korxonasiniki va faol bo'lishi shart (404/400); berilmasa
    # yaratuvchi filiali (GAP-15); filialsiz admin uchun None
    if data.branch_id is not None:
        new_branch_id = get_active_branch(db, data.branch_id, current_user.company_id).id
    else:
        new_branch_id = active_branch_id(db, current_user.branch_id, current_user.company_id)

    customer_data = data.model_dump()
    customer_data["company_id"] = current_user.company_id
    customer_data["branch_id"] = new_branch_id
    # Berilmagan ixtiyoriy maydonlarda model default'i ishlasin (NOT NULL JSON'lar)
    for _f in OPTIONAL_PROFILE_FIELDS:
        if customer_data.get(_f) is None:
            customer_data.pop(_f, None)

    # T0.26: moliyaviy maydonlar faqat vakolatli rollardan qabul qilinadi; boshqa rolda
    # (kassir, agent, ...) jimgina default (0 / 'sale') — POS formasi baribir hammasini yuboradi
    if not _has_role(current_user, CUSTOMER_DEBT_ROLES):
        customer_data["debt_balance"] = Decimal("0")
        customer_data["debt_balances"] = None
        customer_data["debt_currency"] = "UZS"
        customer_data["loyalty_points"] = 0
    if not _has_role(current_user, CUSTOMER_TERMS_ROLES):
        customer_data["debt_limit"] = Decimal("0")
        customer_data["cashback_percent"] = Decimal("0")
        customer_data["price_type"] = "sale"
        customer_data.pop("discount_percent", None)
    # T2.12: keshbek foizi berilmagan bo'lsa korxona sozlamasidagi sukut foiz ishlatiladi
    if "cashback_percent" not in data.model_fields_set or data.cashback_percent is None:
        _rules0 = get_loyalty_rules(db, current_user.company_id)
        if _rules0.company_enabled and _rules0.default_cashback_percent > 0:
            customer_data["cashback_percent"] = _rules0.default_cashback_percent
    # None qiymat NOT NULL/CHECK ustunlarga yozilmasin
    for _f, _default in (("debt_limit", Decimal("0")), ("cashback_percent", Decimal("0")),
                         ("loyalty_points", 0), ("price_type", "sale")):
        if customer_data.get(_f) is None:
            customer_data[_f] = _default

    # debt_balances ni normalize qilish
    balances = customer_data.get("debt_balances") or {}
    if not balances and float(customer_data.get("debt_balance") or 0) > 0:
        currency = (customer_data.get("debt_currency") or "UZS").strip().upper() or "UZS"
        balances = {currency: float(customer_data["debt_balance"])}
    customer_data["debt_balances"] = balances

    # debt_balance ni debt_balances dan hisoblash (UZS ekvivalent)
    customer_data["debt_balance"] = _recalc_debt_uzs(balances, db, current_user.company_id)
    customer_data["debt_currency"] = "UZS"

    customer = Customer(**customer_data)
    if balances:
        # Ochilish qarzi ham jurnalga yoziladi (kim, qaysi filial)
        _append_debt_edit(customer, {}, _normalize_customer_balances(balances, customer.debt_balance, "UZS"),
                          user=current_user, reason="Yangi mijoz (boshlang'ich qarz)")
    db.add(customer)
    if balances:
        db.flush()
        ledger.log_opening(db, customer, user=current_user, reason="Yangi mijoz (boshlang'ich qarz)")
    db.commit()
    db.refresh(customer)
    return customer


@router.post("/bulk-import")
def bulk_import_customers(
        rows: list[dict],
        allow_update: bool = Query(False),
        branch_id: Optional[int] = Query(None, description="Barcha qatorlar uchun filial (qatordagi 'Filial' ustuni ustun)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Excel fayldan mijozlarni yuklash yoki yangilash."""
    FIELD_MAP = {
        "Ism": ("name", str),
        "Telefon": ("phone", str),
        "Qarz": ("debt_balance", Decimal),
        "Kredit limit": ("debt_limit", Decimal),
        "Sodiqlik ballari": ("loyalty_points", int),
        "Karta raqami": ("card_number", str),
        "Cashback": ("cashback_percent", Decimal),
        "Bonus": ("bonus_balance", Decimal),
    }

    created = 0
    updated = 0
    errors: list = []
    warnings: list = []

    # T0.26: moliyaviy ustunlar faqat CUSTOMER_DEBT_ROLES uchun; boshqa rolda e'tiborsiz
    # qoldiriladi va javobda warnings bo'ladi (mavjud mijoz qarzini ustidan yozish ham shu yerda)
    FINANCIAL_COLS = ("Qarz", "Kredit limit", "Sodiqlik ballari", "Cashback", "Bonus")
    can_financial = _has_role(current_user, CUSTOMER_DEBT_ROLES)

    # T1.15: "Filial" ustuni — nom korxona filiallari orasidan (katta-kichik harfsiz) qidiriladi
    from app.models.branch import Branch
    branches_by_name: Dict[str, Branch] = {}
    for _b in db.query(Branch).filter(
        Branch.company_id == current_user.company_id, Branch.is_active.is_(True),
    ).order_by(Branch.id).all():
        branches_by_name.setdefault((_b.name or "").strip().casefold(), _b)

    # T4.5: filialni belgilash faqat admin/director/manager uchun; admin/director - istalgan filial,
    # menejer - faqat o'z (ruxsat etilgan) filiallari. Boshqa rollar filial belgilay olmaydi.
    from app.core.branch_context import effective_branch_ids
    from app.services.tenant_guards import BRANCH_FREE_ROLES
    branch_free = current_user.role in BRANCH_FREE_ROLES
    can_set_branch = branch_free or _has_role(current_user, CUSTOMER_BRANCH_ROLES)
    allowed_branch_ids = frozenset() if branch_free else effective_branch_ids(db, current_user)

    def _branch_forbidden(bid: int) -> bool:
        return not can_set_branch or (not branch_free and bid not in allowed_branch_ids)

    default_branch_id = None
    if branch_id is not None and not isinstance(branch_id, int):
        branch_id = None   # to'g'ridan-to'g'ri chaqirilganda Query() standart qiymati
    if branch_id:
        default_branch_id = get_active_branch(db, branch_id, current_user.company_id).id   # 404 / 400
        if _branch_forbidden(default_branch_id):
            raise HTTPException(status_code=403, detail="Bu filialga mijoz import qilish uchun ruxsat yo'q")

    dup_q_base = db.query(Customer).filter(
        Customer.company_id == current_user.company_id, Customer.is_active.is_(True),
    )

    for idx, row in enumerate(rows):
        row_num = row.get("__row_index", idx + 2)
        if not can_financial:
            ignored = [c for c in FINANCIAL_COLS if row.get(c) is not None and str(row.get(c)).strip() != ""]
            if ignored:
                warnings.append({
                    "row": row_num,
                    "warning": "Moliyaviy ustunlar e'tiborsiz qoldirildi (ruxsat yo'q): " + ", ".join(ignored),
                })
            row = {k: v for k, v in row.items() if k not in FINANCIAL_COLS and k != "__cur_Qarz"}
        try:
            with db.begin_nested():
                name = str(row.get("Ism") or "").strip()
                phone = str(row.get("Telefon") or "").strip()
                card = str(row.get("Karta raqami") or "").strip() or None

                if not name and not phone:
                    errors.append({"row": row_num, "error": "Mijoz ismi yoki telefoni majburiy"})
                    continue

                branch_raw = str(row.get("Filial") or "").strip()
                row_branch_id = None
                if branch_raw:
                    _br = branches_by_name.get(branch_raw.casefold())
                    if not _br:
                        errors.append({"row": row_num, "name": name or phone,
                                       "error": f"Filial topilmadi: {branch_raw}"})
                        continue
                    if _branch_forbidden(_br.id):
                        errors.append({"row": row_num, "name": name or phone,
                                       "error": f"Filialga import qilish uchun ruxsat yo'q: {branch_raw}"})
                        continue
                    row_branch_id = _br.id
                if row_branch_id is None:
                    row_branch_id = default_branch_id   # so'rov parametridagi standart filial

                qarz_raw = row.get("Qarz")
                qarz_val = None
                if qarz_raw is not None and str(qarz_raw).strip() != "":
                    try:
                        qarz_val = parse_decimal_clean(qarz_raw)
                    except Exception:
                        errors.append({"row": row_num, "name": name, "error": f"'Joriy qarz' qiymati noto'g'ri: {qarz_raw}"})
                        continue

                existing = None
                if phone:
                    existing = dup_q_base.filter(Customer.phone == phone).first()
                if not existing and name:
                    existing = dup_q_base.filter(Customer.name == name).first()
                if not existing and card:
                    existing = dup_q_base.filter(Customer.card_number == card).first()

                if existing:
                    if not allow_update:
                        errors.append({
                            "row": row_num, "name": name or phone,
                            "error": f"'{name or phone}' allaqachon mavjud — o'tkazib yuborildi"
                        })
                        continue

                    terms_before = {f: getattr(existing, f) for f in BULK_TERMS_FIELDS}
                    for row_key, (field, cast) in FIELD_MAP.items():
                        if field == "debt_balance":
                            continue
                        raw = row.get(row_key)
                        if raw is None or str(raw).strip() == "":
                            continue
                        try:
                            if cast == Decimal:
                                val = parse_decimal_clean(raw)
                            elif cast == int:
                                # integer fields like loyalty_points may have decimals (e.g. 100.0) from Excel
                                val_str = str(raw).split(".")[0].strip()
                                val = int(val_str)
                            else:
                                val = str(raw).strip()
                            _check_bulk_value(field, val)
                            setattr(existing, field, val)
                        except Exception:
                            errors.append({"row": row_num, "name": name, "error": f"'{row_key}' qiymati xato: {raw}"})
                            continue

                    # Bo'sh "Filial" qiymati mavjud filialni o'zgartirmaydi
                    if row_branch_id is not None and existing.branch_id != row_branch_id:
                        log_action(db, "CUSTOMER_BRANCH", "customer", existing.id, user_id=current_user.id,
                                   old_values={"branch_id": existing.branch_id},
                                   new_values={"branch_id": row_branch_id, "source": "bulk-import"})
                        existing.branch_id = row_branch_id

                    terms_after = {f: getattr(existing, f) for f in BULK_TERMS_FIELDS}
                    if terms_after != terms_before:
                        log_action(db, "CUSTOMER_TERMS", "customer", existing.id, user_id=current_user.id,
                                   old_values={k: str(v) for k, v in terms_before.items()},
                                   new_values={**{k: str(v) for k, v in terms_after.items()}, "source": "bulk-import"})

                    if qarz_val is not None:
                        currency = str(row.get("__cur_Qarz") or "UZS").strip().upper()
                        debt_balances = {currency: float(qarz_val)}

                        total_uzs = _recalc_debt_uzs(debt_balances, db, current_user.company_id)

                        old_balances = _normalize_customer_balances(
                            existing.debt_balances,
                            existing.debt_balance or Decimal("0"),
                            existing.debt_currency or "UZS",
                        )
                        new_balances = _normalize_customer_balances(
                            debt_balances,
                            total_uzs,
                            "UZS"
                        )
                        if old_balances != new_balances:
                            _append_debt_edit(existing, old_balances, new_balances,
                                              user=current_user, reason="bulk-import")

                        # T2.6: farq jurnalga yoziladi (kind='edit'), balans va UZS ekvivalent ledger orqali
                        ledger.set_balances(db, existing, debt_balances, user=current_user, reason="bulk-import")

                    db.flush()
                    updated += 1
                    continue

                if not name:
                    errors.append({"row": row_num, "error": "Yangi mijoz uchun Ism majburiy"})
                    continue

                kwargs = {"name": name, "company_id": current_user.company_id}
                if row_branch_id is not None:
                    kwargs["branch_id"] = row_branch_id
                for row_key, (field, cast) in FIELD_MAP.items():
                    if field in ("name", "debt_balance"):
                        continue
                    raw = row.get(row_key)
                    if raw is not None and str(raw).strip() != "":
                        try:
                            if cast == Decimal:
                                val = parse_decimal_clean(raw)
                            elif cast == int:
                                val_str = str(raw).split(".")[0].strip()
                                val = int(val_str)
                            else:
                                val = str(raw).strip()
                            _check_bulk_value(field, val)
                            kwargs[field] = val
                        except Exception:
                            warnings.append({"row": row_num, "warning": f"'{row_key}' qiymati xato, e'tiborsiz qoldirildi: {raw}"})

                if qarz_val is not None:
                    currency = str(row.get("__cur_Qarz") or "UZS").strip().upper()
                    debt_balances = {currency: float(qarz_val)}

                    kwargs["debt_balances"] = debt_balances
                    kwargs["debt_balance"] = _recalc_debt_uzs(debt_balances, db, current_user.company_id)
                    kwargs["debt_currency"] = "UZS"
                else:
                    kwargs["debt_balances"] = {}
                    kwargs["debt_balance"] = Decimal("0")
                    kwargs["debt_currency"] = "UZS"

                # check card/phone to avoid integrity errors
                check_card = kwargs.get("card_number")
                if check_card and dup_q_base.filter(Customer.card_number == check_card).first():
                    kwargs.pop("card_number")

                check_phone = kwargs.get("phone")
                if check_phone and dup_q_base.filter(Customer.phone == check_phone).first():
                    kwargs.pop("phone")

                cust = Customer(**kwargs)
                if kwargs.get("debt_balances"):
                    _append_debt_edit(cust, {}, _normalize_customer_balances(
                        kwargs["debt_balances"], kwargs["debt_balance"], "UZS"),
                        user=current_user, reason="bulk-import")
                db.add(cust)
                db.flush()
                if kwargs.get("debt_balances"):
                    ledger.log_opening(db, cust, user=current_user, reason="bulk-import")
                created += 1

        except SQLAlchemyError as exc:
            logger.warning("Bulk import row %s failed: %s", row_num, exc)
            errors.append({"row": row_num, "name": str(row.get("Ism") or row.get("Telefon") or ""), "error": row_db_error(exc)})

    db.commit()
    return {"created": created, "updated": updated, "skipped": len(errors), "errors": errors, "warnings": warnings}


@router.post("/{customer_id}", response_model=CustomerOut)
def post_customer(
        customer_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    # 1. Mijozni ID va foydalanuvchining kompaniyasi bo'yicha bazadan qidiramiz
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id
    ).first()

    # 2. Agar bunday mijoz topilmasa, 404 xatolik qaytaramiz
    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Mijoz topilmadi yoki sizning kompaniyangizga tegishli emas."
        )

    # 3. Topilgan mijoz obyektini qaytaramiz.
    # CustomerOut modelidagi @model_validator(mode="before") buni avtomat ravishda normalize qiladi.
    return customer


def _same_balances(a: dict, b: dict) -> bool:
    """Ikki valyuta->summa lug'atini 0.005 aniqlikda taqqoslaydi (nol qoldiqlar hisobga olinmaydi)."""
    def _clean(d):
        return {str(k).strip().upper(): Decimal(str(v or 0)) for k, v in (d or {}).items()
                if abs(Decimal(str(v or 0))) > Decimal("0.005")}
    ca, cb = _clean(a), _clean(b)
    if set(ca) != set(cb):
        return False
    return all(abs(ca[k] - cb[k]) <= Decimal("0.005") for k in ca)


def _same_num(a, b, tol: str = "0.0001") -> bool:
    return abs(Decimal(str(a or 0)) - Decimal(str(b or 0))) <= Decimal(tol)


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, data: CustomerIn, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    # T0.26: mijoz qatori qulflanadi — parallel sotuv/to'lov bilan lost update bo'lmasin
    cust = lock_customer(db, customer_id, current_user.company_id)

    # Faqat yuborilgan maydonlar yangilanadi (phone, card_number, limit va h.k. yuborilmasa o'zgarmaydi)
    update_data = data.model_dump(exclude_unset=True)

    # --- Qarz / ball: PUT orqali hech qachon yozilmaydi ---
    # Joriy qiymatga teng bo'lsa e'tiborsiz (forma hammasini qayta yuboradi), farq qilsa 400.
    cur_balances = _normalize_customer_balances(
        cust.debt_balances, cust.debt_balance or Decimal("0"), cust.debt_currency or "UZS",
    )
    for _f in DEBT_PROTECTED_FIELDS:
        if _f not in update_data:
            continue
        val = update_data.pop(_f)
        if val is None:
            continue
        if _f == "debt_balances":
            changed = not _same_balances(val, cur_balances)
        elif _f == "debt_balance":
            changed = not _same_num(val, cust.debt_balance, "0.01")
        elif _f == "debt_currency":
            changed = str(val).strip().upper() != (cust.debt_currency or "UZS").strip().upper()
        else:  # loyalty_points
            changed = int(val) != int(cust.loyalty_points or 0)
        if changed:
            if _f == "loyalty_points":
                detail = (f"Ballarni PUT orqali o'zgartirib bo'lmaydi — "
                          f"/customers/{customer_id}/adjust-points dan foydalaning")
            else:
                detail = (f"Qarzni PUT orqali o'zgartirib bo'lmaydi — "
                          f"/customers/{customer_id}/adjust-debt dan foydalaning")
            raise HTTPException(status_code=400, detail=detail)

    # --- Shartlar (limit, keshbek, narx turi, chegirma): faqat vakolatli rollar ---
    can_terms = _has_role(current_user, CUSTOMER_TERMS_ROLES)
    terms_old, terms_new = {}, {}
    for _f in TERMS_FIELDS:
        if _f not in update_data:
            continue
        val = update_data[_f]
        if val is None and _f != "discount_percent":
            update_data.pop(_f)      # NOT NULL/CHECK ustunlarga NULL yozilmaydi
            continue
        cur = getattr(cust, _f)
        if _f == "price_type":
            same = (val or "sale") == (cur or "sale")
        else:
            same = _same_num(val, cur)
        if same:
            update_data.pop(_f)      # o'zgarmagan — e'tiborsiz
            continue
        if not can_terms:
            raise HTTPException(status_code=403, detail=f"Bu maydonni o'zgartirish uchun ruxsat yo'q: {_f}")
        terms_old[_f] = str(cur) if cur is not None else None
        terms_new[_f] = str(val) if val is not None else None

    for _f in ("extra_phones", "work_days"):
        if _f in update_data and update_data[_f] is None:
            update_data[_f] = []
    # T1.15: filial faqat yuborilganda o'zgaradi (eski POS forma yubormasa saqlanadi);
    # aniq null — ajratadi. O'zgarish faqat admin/director/manager va faol filialga.
    branch_log = None
    if "branch_id" in update_data:
        new_bid = update_data["branch_id"]
        if new_bid == cust.branch_id:
            update_data.pop("branch_id")
        else:
            if not _has_role(current_user, CUSTOMER_BRANCH_ROLES):
                raise HTTPException(status_code=403, detail="Mijoz filialini o'zgartirish uchun ruxsat yo'q")
            if new_bid is not None:
                get_active_branch(db, new_bid, current_user.company_id)
            branch_log = ({"branch_id": cust.branch_id}, {"branch_id": new_bid})
    if "agent_id" in update_data:
        _check_agent(db, current_user.company_id, update_data["agent_id"])
    _check_territory_free(
        db, current_user.company_id,
        update_data.get("customer_type", cust.customer_type),
        update_data.get("territory", cust.territory),
        exclude_id=cust.id,
        region=update_data.get("region", cust.region),
    )

    for key, val in update_data.items():
        setattr(cust, key, val)
    if terms_new:
        log_action(db, "CUSTOMER_TERMS", "customer", cust.id, user_id=current_user.id,
                   old_values=terms_old, new_values=terms_new)
    if branch_log:
        log_action(db, "CUSTOMER_BRANCH", "customer", cust.id, user_id=current_user.id,
                   old_values=branch_log[0], new_values=branch_log[1])
    db.commit()
    db.refresh(cust)
    return cust


@router.post("/{customer_id}/adjust-debt", response_model=CustomerOut)
def adjust_customer_debt(
        customer_id: int,
        data: DebtAdjust,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*CUSTOMER_DEBT_ROLES)),
):
    """Qarzni qo'lda tuzatish: faqat farq (delta) qo'shiladi, sabab bilan jurnalga yoziladi.
    Butun balansni ustidan yozmaydi, shuning uchun parallel sotuv/to'lovlar yo'qolmaydi."""
    from app.models.currency import Currency as CurrencyModel

    reason = (data.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Tuzatish sababini kiriting")
    changes = [c for c in data.changes if c.delta]
    if not changes:
        raise HTTPException(status_code=400, detail="O'zgarish kiritilmagan")

    cust = lock_customer(db, customer_id, current_user.company_id)

    old_balances = _normalize_customer_balances(
        cust.debt_balances, cust.debt_balance or Decimal("0"), cust.debt_currency or "UZS",
    )
    new_dec = {k: Decimal(str(v)) for k, v in old_balances.items()}
    for c in changes:
        code = (c.currency or "UZS").strip().upper() or "UZS"
        if code != "UZS" and not db.query(CurrencyModel.id).filter(
            CurrencyModel.code == code,
            (CurrencyModel.company_id == current_user.company_id) | (CurrencyModel.company_id.is_(None)),
        ).first():
            raise HTTPException(status_code=400, detail=f"Noma'lum valyuta: {code}")
        new_dec[code] = new_dec.get(code, Decimal("0")) + c.delta
    for code, val in new_dec.items():
        if val < Decimal("-0.005"):
            raise HTTPException(status_code=400, detail=f"Qarz manfiy bo'lib qoladi ({code}): tuzatish summasi qarzdan katta")
    new_balances = {k: (float(v) if v > Decimal("0.005") else 0.0) for k, v in new_dec.items()}

    # T2.6: balans va jurnal (kind='edit', kim/filial/sabab) yagona servis orqali
    ledger.set_balances(db, cust, new_balances, user=current_user, reason=reason, kind="edit")
    _append_debt_edit(cust, old_balances, new_balances, user=current_user, reason=reason)
    log_action(db, "ADJUST_DEBT", "customer", cust.id, user_id=current_user.id,
               old_values={"debt_balances": old_balances},
               new_values={"debt_balances": new_balances, "reason": reason,
                           "changes": [{"currency": (c.currency or "UZS").strip().upper(), "delta": str(c.delta)}
                                       for c in changes]})
    db.commit()
    db.refresh(cust)
    return cust


@router.get("/{customer_id}/stats")
def get_customer_stats(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    from app.models.sale import Sale, SaleStatus

    all_sales = db.query(Sale).filter(
        Sale.customer_id == customer_id,
        Sale.company_id == current_user.company_id
    ).all()
    completed = [s for s in all_sales if s.status != SaleStatus.refunded and s.status != SaleStatus.cancelled]
    returned = [s for s in all_sales if s.status == SaleStatus.refunded]

    # debt_balances ni normalize qilish (eski debt_balance ni ham hisobga olish)
    balances = dict(cust.debt_balances or {})
    if not balances and float(cust.debt_balance or 0) > 0:
        currency = (cust.debt_currency or "UZS").strip().upper() or "UZS"
        balances[currency] = float(cust.debt_balance)

    return {
        "id": cust.id,
        "name": cust.name,
        "phone": cust.phone,
        "branch_id": cust.branch_id,
        "debt_balance": float(cust.debt_balance),
        "debt_limit": float(cust.debt_limit),
        "loyalty_points": cust.loyalty_points or 0,
        "tier": cust.tier,
        "card_number": cust.card_number,
        "cashback_percent": float(cust.cashback_percent or 0),
        "bonus_balance": float(cust.bonus_balance or 0),
        "total_spent": float(cust.total_spent or 0),
        "debt_currency": "UZS",
        "debt_balances": balances,
        "total_sales_count": len(completed),
        "total_sales_amount": sum(float(s.total_amount) for s in completed),
        "total_paid_amount": sum(float(s.paid_amount) for s in completed),
        "total_returns_count": len(returned),
        "total_returns_amount": sum(float(s.total_amount) for s in returned),
    }


@router.get("/{customer_id}/history")
def get_customer_history(customer_id: int, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    from app.models.sale import Sale  # type: ignore
    from app.models.moliya import Transaction  # type: ignore
    from app.models.user import User as UserModel  # type: ignore

    # 1) Barcha sotuvlar (T1.15: kassir va ombor bitta so'rovda — N+1 yo'q)
    from sqlalchemy.orm import joinedload  # type: ignore
    sales = db.query(Sale).options(
        joinedload(Sale.cashier), joinedload(Sale.warehouse),
    ).filter(
        Sale.customer_id == customer_id,
        Sale.company_id == current_user.company_id
    ).order_by(Sale.created_at.desc()).all()

    # 2) Qarz to'lovlari (customer_payment transaktsiyalari)
    # T1.19: bekor qilingan (void) tranzaksiyalar tarixda ko'rsatilmaydi
    payments = db.query(Transaction).options(
        joinedload(Transaction.user), joinedload(Transaction.branch),
    ).filter(
        Transaction.reference_type == "customer_payment",
        Transaction.reference_id == customer_id,
        Transaction.company_id == current_user.company_id,
        Transaction.voided_at.is_(None),
    ).order_by(Transaction.created_at.desc()).all()

    # 3) Qarz jurnali (T2.6): boshlang'ich qarz, tahrir, hisobdan chiqarish, AI, yetkazish haqi, qayta hisoblash.
    # Sotuv/qaytarish/to'lov jurnal qatorlari yuqoridagi sotuvlar va to'lovlar bilan takrorlanmasin deb olinmaydi.
    from app.models.customer_debt_log import CustomerDebtLog as DebtLog  # type: ignore
    debt_log_rows = db.query(DebtLog).filter(
        DebtLog.customer_id == customer_id,
        DebtLog.company_id == current_user.company_id,
        DebtLog.kind.in_(HISTORY_DEBT_LOG_KINDS),
    ).order_by(DebtLog.created_at.desc(), DebtLog.id.desc()).all()

    history = []

    # T1.15: filial nomlari bitta so'rovda (savdo omborlarining filiallari)
    from app.models.branch import Branch  # type: ignore
    # T1.9: sotuv filiali — `Sale.branch_id` snapshot'i (bo'lmasa — eski qator: ombor filiali)
    _wh_branch_ids = {
        (s.branch_id or (s.warehouse.branch_id if s.warehouse else None)) for s in sales
        if s.branch_id or (s.warehouse and s.warehouse.branch_id)
    }
    branch_names = {}
    if _wh_branch_ids:
        branch_names = {
            b.id: b.name for b in db.query(Branch.id, Branch.name).filter(
                Branch.id.in_(_wh_branch_ids), Branch.company_id == current_user.company_id,
            ).all()
        }

    from app.models.sale import SaleStatus
    for s in sales:
        exr = float(s.exchange_rate or 1.0)
        total = float(s.total_amount or 0) / exr
        paid = float(s.paid_amount or 0) / exr
        
        if s.status == SaleStatus.refunded:
            op_type = "refund"
            debt_added = -max(0.0, total - paid)
            desc = s.note or f"Qaytarish (#{getattr(s, 'number', '')})"
        else:
            op_type = "sale"
            debt_added = max(0.0, total - paid)
            desc = f"Sotuv #{getattr(s, 'number', '')}"
        
        curr_code = "UZS"
        if hasattr(s, "currency") and s.currency:
            curr_code = s.currency.code
        elif hasattr(s, "currency_id") and s.currency_id:
            from app.models.currency import Currency
            curr_obj = db.query(Currency).filter(Currency.id == s.currency_id).first()
            if curr_obj:
                curr_code = curr_obj.code

        history.append({
            "id": s.id,
            "op_type": op_type,                       
            "date": s.created_at.isoformat() if s.created_at else "",
            "amount": total,
            "paid": paid,
            "debt": debt_added,
            "currency": curr_code,
            "payment_type": getattr(s, "payment_type", ""),
            "cashier": s.cashier.name if s.cashier else "",
            "warehouse_id": s.warehouse_id,
            "warehouse_name": s.warehouse.name if s.warehouse else "",
            "branch_id": s.branch_id or (s.warehouse.branch_id if s.warehouse else None),
            "branch_name": branch_names.get(s.branch_id or (s.warehouse.branch_id if s.warehouse else None), ""),
            "sale_number": getattr(s, "number", ""),
            "description": desc,
            "type": op_type,
        })

    for p in payments:
        history.append({
            "id": p.id,
            "op_type": "payment",                    # qarz to'lovi
            "date": p.created_at.isoformat() if p.created_at else "",
            "amount": float(p.amount or 0),
            "paid": float(p.amount or 0),
            "debt": 0,
            "currency": p.currency_code or "UZS",
            "payment_type": p.payment_type or "cash",
            "cashier": p.user.name if p.user else "",
            "branch_id": p.branch_id,
            "branch_name": p.branch.name if p.branch and p.branch.company_id == current_user.company_id else "",
            "description": p.description or "Qarz to'lovi",
            # eski maydon
            "type": "payment",
        })

    # Jurnal qatorlari (kim, qaysi filial, sabab)
    _log_branch_ids = {r.branch_id for r in debt_log_rows if r.branch_id}
    _log_branch_names = {
        b.id: b.name for b in db.query(Branch.id, Branch.name).filter(
            Branch.id.in_(_log_branch_ids), Branch.company_id == current_user.company_id,
        ).all()
    } if _log_branch_ids else {}
    _log_user_ids = {r.user_id for r in debt_log_rows if r.user_id}
    _log_user_names = {
        u.id: u.name for u in db.query(UserModel.id, UserModel.name).filter(UserModel.id.in_(_log_user_ids)).all()
    } if _log_user_ids else {}
    for r in debt_log_rows:
        label = DEBT_LOG_LABELS.get(r.kind, "Qarz o'zgarishi")
        history.append({
            "id": r.id,
            "op_type": "debt_edit",
            "date": r.created_at.isoformat() if r.created_at else "",
            "amount": abs(float(r.delta or 0)),
            "paid": 0,
            "debt": float(r.delta or 0),
            "currency": r.currency or "UZS",
            "payment_type": "",
            "cashier": _log_user_names.get(r.user_id, ""),
            "branch_id": r.branch_id,
            "branch_name": _log_branch_names.get(r.branch_id, ""),
            "description": f"{label}: {r.reason}" if r.reason else label,
            "type": "debt_edit",
            "kind": r.kind,
            "reason": r.reason,
            "edited_by": ({"id": r.user_id, "name": _log_user_names.get(r.user_id, "")} if r.user_id else None),
        })

    # Jurnal yuritilishidan oldingi tahrirlar (`customers.debt_edited`): jurnalda aynan shu o'zgarish bo'lsa
    # (user va valyuta bo'yicha farq mos) takrorlanmaydi
    _pool = [r for r in debt_log_rows if r.kind in ("edit", "opening")]
    # T2.7: kurslar bir marta, joriy korxona bo'yicha yuklanadi (korxonasiz so'rov faqat global kursni ko'rardi)
    from app.services.currency_service import rate_map as _rate_map
    _edit_rates = _rate_map(db, current_user.company_id)
    for edit in (cust.debt_edited or []):
        from_bal = edit.get("edited_from") or {}
        to_bal = edit.get("edited_to") or {}
        editor = edit.get("edited_by") or {}
        _diffs = {}
        for _c in set(from_bal) | set(to_bal):
            _d_ = Decimal(str(to_bal.get(_c) or 0)) - Decimal(str(from_bal.get(_c) or 0))
            if abs(_d_) > Decimal("0.005"):
                _diffs[str(_c).strip().upper()] = _d_
        _matched = []
        for _c, _d_ in _diffs.items():
            _hit = next((r for r in _pool if r not in _matched and (r.currency or "UZS").upper() == _c
                         and abs(Decimal(str(r.delta or 0)) - _d_) < Decimal("0.01")
                         and (editor.get("id") is None or r.user_id in (None, editor.get("id")))), None)
            if _hit is None:
                break
            _matched.append(_hit)
        if _diffs and len(_matched) == len(_diffs):
            continue
        from_total = float(_calc_debt_in_uzs(from_bal, db, _edit_rates, company_id=current_user.company_id))
        to_total = float(_calc_debt_in_uzs(to_bal, db, _edit_rates, company_id=current_user.company_id))
        debt_change = to_total - from_total
        reason = edit.get("reason")
        history.append({
            "op_type": "debt_edit",
            "date": edit.get("edited_at") or "",
            "amount": abs(debt_change),
            "paid": 0,
            "debt": debt_change,
            "currency": "UZS",
            "payment_type": "",
            "cashier": editor.get("name") or "",
            "description": f"Qarz tahriri: {reason}" if reason else "Qarz tahriri",
            "type": "debt_edit",
            "edited_from": from_bal,
            "edited_to": to_bal,
            "edited_by": editor or None,
            "branch_id": edit.get("branch_id"),
            "reason": reason,
        })

    return sorted(history, key=lambda x: x.get("date") or "", reverse=True)


@router.get("/{customer_id}/pay-debt")
def pay_debt_get(customer_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    """Mijoz qarz to'lovi uchun kerakli ma'lumotlarni qaytaradi."""
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Ensure debt_balances is initialized
    if not cust.debt_balances:
        cust.debt_balances = {}
        if float(cust.debt_balance or 0) > 0:
            legacy_currency = (cust.debt_currency or "UZS").strip().upper() or "UZS"
            cust.debt_balances = {legacy_currency: float(cust.debt_balance)}

    # Get available wallets for the company (T1.10: foydalanuvchiga ko'rinadigan, shaxsiy bo'lmagan kassalar)
    from app.services.wallet_resolver import wallet_visible_to
    wallets = [
        w for w in db.query(Wallet).filter(
            Wallet.company_id == current_user.company_id,
            Wallet.is_active == True,
            Wallet.is_open == True
        ).order_by(Wallet.id).all()
        if wallet_visible_to(db, current_user, w)
    ]

    # Get available currencies (T2.7: faqat shu korxonaning faol valyutalari — begona korxona kurslari ko'rinmaydi)
    currencies = db.query(Currency).filter(
        Currency.company_id == current_user.company_id,
        Currency.is_active.isnot(False),
    ).order_by(Currency.id).all()

    return {
        "customer": {
            "id": cust.id,
            "name": cust.name,
            "phone": cust.phone,
            "debt_balance": float(cust.debt_balance or 0),
            "debt_balances": cust.debt_balances,
            "debt_limit": float(cust.debt_limit or 0),
        },
        "wallets": [
            {
                "id": w.id,
                "name": w.name,
                "type": w.type,
                "balance": float(w.balance),
            }
            for w in wallets
        ],
        "currencies": [
            {
                "code": c.code,
                "name": c.name,
                "rate": float(c.rate),
            }
            for c in currencies
        ],
    }


@router.post("/{customer_id}/pay-debt")
def pay_debt(customer_id: int, data: DebtUpdate, db: Session = Depends(get_db),
             current_user: User = Depends(require_roles(*CUSTOMER_PAY_ROLES))):
    """Mijoz qarzini to'lash — ingichka wrapper: butun mantiq `customer_ledger.pay_debt` da (T2.6).
    `finance/customer-debts/{id}/pay`, AI va agent ilovasi ham xuddi shu servisni chaqiradi."""
    # Qulf tartibi: mijoz -> hamyon (ombor qoldig'iga tegmaydi)
    cust = lock_customer(db, customer_id, current_user.company_id)
    if data.payments and len(data.payments) > 0:
        payments = data.payments
    else:
        # Eski klientlar (bitta to'lov)
        payments = [PaymentInput(
            amount=data.amount, currency=data.currency or "UZS",
            payment_type=data.payment_type or "cash", rate=None,
        )]
    res = ledger.pay_debt(
        db, cust, user=current_user, payments=payments, wallet_id=data.wallet_id, reason=data.reason,
    )
    db.commit()
    return {
        "message": "Qarzdorlik to'landi",
        "remaining_debt": res["remaining_debt"],
        "debt_balances": res["debt_balances"],
        "transaction_ids": res["transaction_ids"],
        "allocation": res["allocation"],
    }


@router.get("/{customer_id}/payments")
def get_customer_payments(
        customer_id: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Mijoz kartasidagi "Kirim to'lovlar": `reference_type='customer_payment'` va `reference_id=customer_id`
    bo'yicha (ism bo'yicha emas). Karta ruxsatiga mos — kassir ham ko'ra oladi (T2.6)."""
    from sqlalchemy.orm import joinedload  # type: ignore
    from app.models.moliya import Transaction  # type: ignore
    from app.utils.report_utils import date_bounds  # type: ignore

    if not db.query(Customer.id).filter(
        Customer.id == customer_id, Customer.company_id == current_user.company_id,
    ).first():
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    q = db.query(Transaction).filter(
        Transaction.reference_type == "customer_payment",
        Transaction.reference_id == customer_id,
        Transaction.company_id == current_user.company_id,
        Transaction.voided_at.is_(None),
    )
    if date_from or date_to:
        start, end = date_bounds(date_from, date_to)
        q = q.filter(Transaction.created_at >= start, Transaction.created_at < end)
    total = q.order_by(None).count()
    txs = (
        q.options(joinedload(Transaction.wallet), joinedload(Transaction.branch), joinedload(Transaction.user))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc()).offset(skip).limit(limit).all()
    )
    items = []
    for tx in txs:
        branch = tx.branch if (tx.branch and tx.branch.company_id == current_user.company_id) else None
        items.append({
            "id": tx.id,
            "amount": float(tx.amount or 0),
            "currency": tx.currency_code or "UZS",
            "payment_type": tx.payment_type or "cash",
            "wallet_id": tx.wallet_id,
            "wallet_name": tx.wallet.name if tx.wallet and tx.wallet.company_id == current_user.company_id else None,
            "branch_id": tx.branch_id,
            "branch_name": branch.name if branch else None,
            "user_name": tx.user.name if tx.user else None,
            "description": tx.description,
            "allocation": (tx.meta or {}).get("allocation") if isinstance(tx.meta, dict) else None,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        })
    return {"items": items, "total": total}


@router.get("/{customer_id}/debt-log")
def get_customer_debt_log(
        customer_id: int,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Mijoz qarzi harakatlari jurnali (T2.6): kim, qaysi filialda, nima uchun."""
    from app.models.branch import Branch  # type: ignore
    from app.models.customer_debt_log import CustomerDebtLog as DebtLog  # type: ignore

    if not db.query(Customer.id).filter(
        Customer.id == customer_id, Customer.company_id == current_user.company_id,
    ).first():
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    q = db.query(DebtLog).filter(DebtLog.customer_id == customer_id, DebtLog.company_id == current_user.company_id)
    total = q.count()
    rows = q.order_by(DebtLog.created_at.desc(), DebtLog.id.desc()).offset(skip).limit(limit).all()
    branch_ids = {b for r in rows for b in (r.branch_id, r.cash_branch_id) if b}
    branch_names = {
        b.id: b.name for b in db.query(Branch.id, Branch.name).filter(
            Branch.id.in_(branch_ids), Branch.company_id == current_user.company_id,
        ).all()
    } if branch_ids else {}
    user_ids = {r.user_id for r in rows if r.user_id}
    user_names = {
        u.id: u.name for u in db.query(User.id, User.name).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    return {
        "total": total,
        "items": [{
            "id": r.id, "kind": r.kind, "currency": r.currency,
            "delta": float(r.delta or 0), "delta_uzs": float(r.delta_uzs or 0),
            "rate": float(r.rate) if r.rate is not None else None,
            "branch_id": r.branch_id, "branch_name": branch_names.get(r.branch_id),
            "cash_branch_id": r.cash_branch_id, "cash_branch_name": branch_names.get(r.cash_branch_id),
            "user_id": r.user_id, "user_name": user_names.get(r.user_id),
            "sale_id": r.sale_id, "transaction_id": r.transaction_id, "reason": r.reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
    }


class DebtWriteOff(BaseModel):
    amount: Decimal
    currency: str = "UZS"
    reason: str


@router.post("/{customer_id}/debt-writeoff")
def write_off_customer_debt(
        customer_id: int,
        data: DebtWriteOff,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """Qarzni hisobdan chiqarish (kassa harakatisiz): faqat admin/director, sabab majburiy (kamida 5 belgi).
    Pulsiz qarz kamaytirish faqat shu amal orqali (T2.6)."""
    cust = lock_customer(db, customer_id, current_user.company_id)
    rows = ledger.write_off(
        db, cust, user=current_user, amount=data.amount, currency=data.currency, reason=data.reason,
    )
    db.commit()
    return {
        "message": "Qarz hisobdan chiqarildi",
        "debt_balance": float(cust.debt_balance or 0),
        "debt_balances": dict(cust.debt_balances or {}),
        "log_ids": [r.id for r in rows],
    }


@router.post("/debt-log/reconcile")
def reconcile_debt_log(
        dry_run: bool = Query(True, description="true — faqat farqlarni qaytaradi; false — 'recalc' qatorlari bilan tuzatadi"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*CUSTOMER_DEBT_ROLES)),
):
    """Invariant: har mijoz va valyuta uchun `SUM(delta)` = `debt_balances[valyuta]`. Farqlar ro'yxati qaytadi."""
    diffs = ledger.reconcile(db, current_user.company_id, dry_run=dry_run, user=current_user)
    if not dry_run and diffs:
        log_action(db, "DEBT_LOG_RECONCILE", "customer", None, user_id=current_user.id,
                   new_values={"fixed": len(diffs)}, company_id=current_user.company_id)
        db.commit()
    return {"dry_run": dry_run, "count": len(diffs), "items": diffs}


@router.get("/{customer_id}/cashback")
def get_customer_cashback(
        customer_id: int,
        warehouse_id: Optional[int] = Query(None, description="Sotuv ombori (filial qoidasini aniqlash uchun)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """POS uchun: mijozning keshbek va bonus balans ma'lumotlari (yengil endpoint)."""
    cust = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    # T2.12: sozlama (korxona + filial): daraja chegaralari, ball qiymati, sarflash imkoniyati
    rules = get_loyalty_rules(db, current_user.company_id, warehouse_id=warehouse_id,
                              branch_id=None if warehouse_id else current_user.branch_id)
    bonus = float(cust.bonus_balance or 0)
    points = int(cust.loyalty_points or 0)
    return {
        "loyalty_enabled": rules.enabled,
        "point_value": float(rules.point_value),
        "max_redeem_percent": float(rules.max_redeem_percent),
        "max_redeem_uzs": (bonus + points * float(rules.point_value)) if rules.enabled else 0,
        "customer_id": cust.id,
        "name": cust.name,
        "bonus_balance": float(cust.bonus_balance or 0),
        "cashback_percent": float(cust.cashback_percent or 0),
        "loyalty_points": cust.loyalty_points or 0,
        "tier": tier_for(cust.loyalty_points or 0, rules),
        "debt_balance": float(cust.debt_balance or 0),
        "debt_balances": cust.debt_balances or {},
        "debt_limit": float(cust.debt_limit or 0),
    }


@router.post("/{customer_id}/adjust-points")
def adjust_loyalty_points(
        customer_id: int,
        data: PointsAdjust,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*CUSTOMER_DEBT_ROLES)),
):
    """Loyallik ballarini qo'shish yoki ayirish (sabab majburiy, jurnalga yoziladi)"""
    cust = lock_customer(db, customer_id, current_user.company_id)
    old_points = int(cust.loyalty_points or 0)
    new_points = old_points + data.delta
    if new_points < 0:
        raise HTTPException(status_code=400, detail="Ballar manfiy bo'lolmaydi")
    cust.loyalty_points = new_points
    log_action(db, "ADJUST_POINTS", "customer", cust.id, user_id=current_user.id,
               old_values={"loyalty_points": old_points},
               new_values={"loyalty_points": new_points, "delta": data.delta, "reason": data.reason})
    db.commit()
    return {
        "customer_id": customer_id,
        "delta": data.delta,
        "loyalty_points": cust.loyalty_points,
        "tier": tier_for(cust.loyalty_points or 0, get_loyalty_rules(db, current_user.company_id)),
    }


# Faol buyurtma holatlari — shu holatdagi buyurtmasi bor mijozni o'chirib bo'lmaydi
ACTIVE_ORDER_STATUSES = ("pending", "confirmed", "preparing", "assigned", "on_way")


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_roles(*CUSTOMER_DEBT_ROLES))):
    """Mijozni o'chirish. Ochiq qarz yoki faol buyurtma/kutilayotgan sotuv bo'lsa — 400.
    Sotuv/buyurtma tarixi bo'lmasa jismonan o'chadi, tarixi bor bo'lsa arxivlanadi
    (Sale.customer_id hech qachon NULL qilinmaydi)."""
    from app.models.sale import Sale, SaleStatus
    from app.models.order import Order, OrderStatus
    from app.models.agent_visit import AgentVisit
    from app.routers.customer_profile import delete_customer_files

    cust = lock_customer(db, customer_id, current_user.company_id, allow_inactive=True)
    if cust.is_active is False:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    # 1) Ochiq qarz
    balances = _normalize_customer_balances(cust.debt_balances, cust.debt_balance or Decimal("0"), cust.debt_currency or "UZS")
    open_debts = {k: v for k, v in balances.items() if v > 0.01}
    if open_debts or Decimal(str(cust.debt_balance or 0)) > Decimal("0.01"):
        shown = ", ".join(f"{v:,.0f} {k}".replace(",", " ") for k, v in open_debts.items()) \
            or f"{float(cust.debt_balance):,.0f}".replace(",", " ")
        raise HTTPException(status_code=400, detail=f"Mijozning ochiq qarzi bor ({shown}) — avval qarzni yoping")

    # 2) Faol buyurtma yoki kutilayotgan sotuv
    if db.query(Order.id).filter(
        Order.customer_id == cust.id,
        Order.status.in_([OrderStatus(s) for s in ACTIVE_ORDER_STATUSES]),
    ).first():
        raise HTTPException(status_code=400, detail="Mijozning faol buyurtmasi bor — avval buyurtmani yakunlang yoki bekor qiling")
    if db.query(Sale.id).filter(Sale.customer_id == cust.id, Sale.status == SaleStatus.pending).first():
        raise HTTPException(status_code=400, detail="Mijozning kutilayotgan sotuvi bor — avval uni yakunlang yoki bekor qiling")

    has_history = bool(
        db.query(Sale.id).filter(Sale.customer_id == cust.id).first()
        or db.query(Order.id).filter(Order.customer_id == cust.id).first()
        # agent tashrif tarixi (agent_visits ondelete=CASCADE) jim yo'qolmasin
        or db.query(AgentVisit.id).filter(AgentVisit.customer_id == cust.id).first()
    )
    snapshot = {"name": cust.name, "phone": cust.phone, "card_number": cust.card_number,
                "tg_chat_id": cust.tg_chat_id, "agent_id": cust.agent_id}

    if not has_history:
        # 3) Tarix yo'q — jismonan o'chirish (maxsus narxlar, hujjat fayllari bilan)
        db.query(CustomerPrice).filter(CustomerPrice.customer_id == cust.id).delete(synchronize_session=False)
        delete_customer_files(db, cust)
        db.delete(cust)
        mode = "deleted"
    else:
        # 4) Tarix bor — arxivlash; unique maydonlar bo'shatiladi (xuddi shu telefon bilan yangi mijoz ochish uchun)
        cust.deleted_meta = {k: snapshot[k] for k in ("phone", "card_number", "tg_chat_id", "agent_id")}
        cust.is_active = False
        cust.deleted_at = datetime.now(timezone.utc)
        cust.phone = None
        cust.card_number = None
        cust.tg_chat_id = None
        cust.agent_id = None
        mode = "archived"
    log_action(db, "DELETE_CUSTOMER", "customer", customer_id, user_id=current_user.id,
               old_values=snapshot, new_values={"mode": mode})
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.warning("Customer %s delete failed: %s", customer_id, exc)
        raise HTTPException(status_code=409, detail="Mijozni o'chirib bo'lmadi: unga bog'liq yozuvlar bor")


# ── Customer Prices ────────────────────────────────────────────────────────────

class CustomerPriceIn(BaseModel):
    product_id: int
    price: Decimal = Field(..., gt=0)


@router.get("/{customer_id}/prices")
def list_customer_prices(
        customer_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    cust = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    from app.models.product import Product  # type: ignore
    rows = db.query(CustomerPrice, Product).join(
        Product, Product.id == CustomerPrice.product_id,
    ).filter(
        CustomerPrice.customer_id == customer_id,
        CustomerPrice.company_id == current_user.company_id,
        Product.company_id == current_user.company_id,
    ).order_by(CustomerPrice.id).all()
    return [
        {
            "id": cp.id,
            "product_id": cp.product_id,
            "product_name": pr.name,
            "sku": pr.sku,
            "price": float(cp.price or 0),
            "sale_price": float(pr.sale_price or 0),
        }
        for cp, pr in rows
    ]


@router.post("/{customer_id}/prices", status_code=201)
def set_customer_price(
        customer_id: int,
        data: CustomerPriceIn,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*CUSTOMER_TERMS_ROLES)),
):
    cust = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    # T3.19: mahsulot shu korxonaniki va o'chirilmagan bo'lishi shart
    from app.models.product import Product  # type: ignore
    _prod = db.query(Product.id).filter(
        Product.id == data.product_id,
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,  # noqa: E712
    ).first()
    if not _prod:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    existing = db.query(CustomerPrice).filter(
        CustomerPrice.customer_id == customer_id,
        CustomerPrice.product_id == data.product_id,
        CustomerPrice.company_id == current_user.company_id,
    ).first()
    if existing:
        log_action(db, "CUSTOMER_PRICE", "customer", customer_id, user_id=current_user.id,
                   old_values={"product_id": data.product_id, "price": str(existing.price)},
                   new_values={"product_id": data.product_id, "price": str(data.price)})
        existing.price = data.price
        db.commit()
        db.refresh(existing)
        return {"id": existing.id, "product_id": existing.product_id, "price": float(existing.price or 0)}
    cp = CustomerPrice(
        company_id=current_user.company_id,
        customer_id=customer_id,
        product_id=data.product_id,
        price=data.price,
    )
    db.add(cp)
    log_action(db, "CUSTOMER_PRICE", "customer", customer_id, user_id=current_user.id,
               new_values={"product_id": data.product_id, "price": str(data.price)})
    db.commit()
    db.refresh(cp)
    return {"id": cp.id, "product_id": cp.product_id, "price": float(cp.price or 0)}


@router.delete("/{customer_id}/prices/{product_id}", status_code=204)
def delete_customer_price(
        customer_id: int,
        product_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*CUSTOMER_TERMS_ROLES)),
):
    cp = db.query(CustomerPrice).filter(
        CustomerPrice.customer_id == customer_id,
        CustomerPrice.product_id == product_id,
        CustomerPrice.company_id == current_user.company_id,
    ).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Narx topilmadi")
    log_action(db, "CUSTOMER_PRICE", "customer", customer_id, user_id=current_user.id,
               old_values={"product_id": product_id, "price": str(cp.price)}, new_values={"deleted": True})
    db.delete(cp)
    db.commit()


@router.get("/{customer_id}/barcode.svg")
def get_customer_barcode_svg(
        customer_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Mijozning shtrix kodini SVG qilib qaytaradi."""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    if not customer.card_number:
        raise HTTPException(status_code=400, detail="Mijozning karta raqami yo'q")

    import barcode
    import io
    from barcode.writer import ImageWriter

    Code128 = barcode.get_barcode_class("code128")
    buf = io.BytesIO()
    Code128(customer.card_number, writer=ImageWriter()).write(buf, options={
        "module_height": 12.0,
        "module_width": 0.38,
        "quiet_zone": 6.5,
        "font_size": 10,
        "text_distance": 4.0,
    })
    buf.seek(0)

    from fastapi.responses import Response
    return Response(content=buf.getvalue(), media_type="image/png")


@router.put("/{customer_id}/assign-branch")
def assign_branch_to_customer(
        customer_id: int,
        branch_id: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*CUSTOMER_BRANCH_ROLES)),
):
    """Mijozga filial biriktirish (T1.15). `branch_id` berilmasa/`null` bo'lsa filialni ajratadi."""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    old_branch_id = customer.branch_id
    if branch_id is None:
        customer.branch_id = None
        message = "Mijoz filialdan ajratildi"
    else:
        branch = get_active_branch(db, branch_id, current_user.company_id)
        customer.branch_id = branch.id
        message = f"Mijoz {branch.name} filialiga biriktirildi"

    if old_branch_id != customer.branch_id:
        log_action(db, "CUSTOMER_BRANCH", "customer", customer.id, user_id=current_user.id,
                   old_values={"branch_id": old_branch_id}, new_values={"branch_id": customer.branch_id})
    db.commit()
    db.refresh(customer)

    return {"message": message, "branch_id": customer.branch_id}


@router.post("/{customer_id}/send-barcode-to-telegram")
async def send_barcode_to_telegram(
        customer_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company or not company.tg_bot_token:
        raise HTTPException(status_code=400, detail="Telegram boti sozlanmagan")

    if not customer.tg_chat_id:
        raise HTTPException(status_code=400, detail="Mijoz Telegram'da ulangan emas")

    if not customer.card_number:
        raise HTTPException(status_code=400, detail="Mijozning karta raqami yo'q")

    from app.routers.telegram import send_loyalty_card

    cashback = float(customer.cashback_percent or 0)
    await send_loyalty_card(
        str(company.tg_bot_token),
        str(customer.tg_chat_id),
        str(customer.name),
        str(customer.card_number),
        cashback
    )

    return {"message": "Shtrix kod Telegram orqali yuborildi", "customer": customer.name}
