"""
Companies (Korxonalar) CRUD API
super_admin va admin/director uchun
"""
from datetime import datetime
from typing import List, Literal, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore
from pydantic import BaseModel, field_validator

from app.config import settings  # type: ignore
from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.user import User, UserRole  # type: ignore

router = APIRouter(prefix="/companies", tags=["Companies"])

MANAGE_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director)


def _telegram_setup_bot(token: str, webhook_url: str) -> str:
    """Token tekshiradi, bot username oladi, webhook o'rnatadi. Bot username qaytaradi."""
    try:
        with httpx.Client(timeout=10) as client:
            r = client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = r.json()
            if not data.get("ok"):
                raise HTTPException(status_code=400, detail="Bot tokeni noto'g'ri yoki bot mavjud emas!")
            bot_username = data["result"].get("username", "")
            client.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
            )
            return bot_username
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Telegram API bilan bog'lanishda xatolik: {e}")


def _telegram_delete_webhook(token: str) -> None:
    """Webhookni o'chiradi (bot uzilganda)."""
    try:
        with httpx.Client(timeout=10) as client:
            client.post(f"https://api.telegram.org/bot{token}/deleteWebhook")
    except Exception:
        pass


class CompanyCreate(BaseModel):
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    tg_bot_token: Optional[str] = None
    tg_bot_username: Optional[str] = None
    daily_report_time: Optional[str] = None
    low_stock_alert: Optional[bool] = None
    expiration_alert: Optional[bool] = None
    debt_deadline_alert: Optional[bool] = None
    daily_report_enabled: Optional[bool] = None
    daily_report_recipients: Optional[Literal["owners_and_admins", "owners", "all_managers"]] = None   # T3.16
    shop_allow_out_of_stock_orders: Optional[bool] = None
    pos_allow_negative_stock: Optional[bool] = None
    delivery_fee: Optional[float] = None
    courier_bot_token: Optional[str] = None
    orders_auto_create_sale: Optional[bool] = None
    pos_require_shift: Optional[bool] = None   # T1.11: ochiq smenasiz sotuv backendda rad etiladi
    promotions_auto_apply: Optional[bool] = None   # C4.1 (T4.3): null kelsa e'tiborsiz
    fiscal_default_vat: Optional[int] = None   # C4.1 (T4.2): QQS turi belgilanmagan mahsulot uchun foiz (null = 12)
    credit_limit_scope: Optional[Literal["distributor", "all"]] = None   # T2.12: kredit limit kimga qo'llanadi
    manufacturing_enabled: Optional[bool] = None
    distribution_enabled: Optional[bool] = None
    marketplace_agents_enabled: Optional[bool] = None
    # T0.36: Mir-maza buyurtmalari uchun asosiy filial (shu korxonaning faol filiali bo'lishi shart)
    marketplace_default_branch_id: Optional[int] = None
    # T3.13: Telegram Mini App / bot buyurtmalari uchun standart filial (shu korxonaning faol filiali)
    shop_default_branch_id: Optional[int] = None
    # Xarid chekini Telegram botda yuborish formati: 'text', 'image', 'pdf'
    receipt_format: Optional[Literal["text", "pdf", "image"]] = None
    tg_protect_content: Optional[bool] = None
    stock_deduct_stage: Optional[str] = None
    agent_order_geo_radius_check: Optional[bool] = None
    default_delivery_radius_m: Optional[int] = None


# Chek shabloni (XSS himoyasi): faqat ma'lum kalitlar va cheklangan qiymatlar
RECEIPT_TEMPLATE_KEYS = ("r58", "r80", "nak")
RECEIPT_TEXT_FIELDS = (
    "company", "address", "phone", "inn", "header", "footer", "footer_note",
    "director", "accountant", "storekeeper", "bank", "account", "mfo",
    "logo_position", "copies",
)
RECEIPT_TEXT_MAX = 500
RECEIPT_LOGO_MAX = 1_500_000  # data URL uchun (~1 MB rasm)
RECEIPT_LOGO_PREFIXES = (
    "data:image/png;base64,", "data:image/jpeg;base64,", "data:image/jpg;base64,",
    "data:image/gif;base64,", "data:image/webp;base64,", "data:image/svg+xml;base64,",
    "https://",
)


def _validate_receipt_cfg(name: str, cfg) -> dict:
    if not isinstance(cfg, dict):
        raise ValueError(f"'{name}' obyekt bo'lishi kerak")
    out = {}
    for key, val in cfg.items():
        if key == "_company_id":
            continue
        if key.startswith("show_"):
            if not isinstance(val, (bool, int)) and val is not None:
                raise ValueError(f"'{name}.{key}' mantiqiy qiymat bo'lishi kerak")
            out[key] = val
        elif key in RECEIPT_TEXT_FIELDS:
            if val is None:
                val = ""
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                val = str(val)
            if not isinstance(val, str):
                raise ValueError(f"'{name}.{key}' matn bo'lishi kerak")
            if len(val) > RECEIPT_TEXT_MAX:
                raise ValueError(f"'{name}.{key}' juda uzun (ko'pi bilan {RECEIPT_TEXT_MAX} belgi)")
            out[key] = val
        elif key == "logo":
            if val is None:
                val = ""
            if not isinstance(val, str):
                raise ValueError(f"'{name}.logo' matn bo'lishi kerak")
            if val:
                if len(val) > RECEIPT_LOGO_MAX:
                    raise ValueError(f"'{name}.logo' juda katta")
                if not val.lower().startswith(RECEIPT_LOGO_PREFIXES):
                    raise ValueError(f"'{name}.logo' faqat data:image/... yoki https:// bo'lishi mumkin")
                if any(ch in val for ch in ('"', "'", "<", ">", " ", chr(10), chr(13))):
                    raise ValueError(f"'{name}.logo' noto'g'ri belgilarni o'z ichiga oladi")
            out[key] = val
        elif key == "logo_size":
            try:
                num = float(val) if val not in (None, "") else 0
            except (TypeError, ValueError):
                raise ValueError(f"'{name}.logo_size' son bo'lishi kerak")
            if isinstance(val, bool) or not (0 <= num <= 1000):
                raise ValueError(f"'{name}.logo_size' 0..1000 oralig'ida bo'lishi kerak")
            out[key] = val
        else:
            raise ValueError(f"'{name}.{key}' noma'lum kalit")
    return out


class ReceiptTemplatesUpdate(BaseModel):
    receipt_templates: dict

    @field_validator("receipt_templates")
    @classmethod
    def _check_templates(cls, v: dict) -> dict:
        out = {}
        for name, cfg in v.items():
            if name not in RECEIPT_TEMPLATE_KEYS:
                raise ValueError(f"'{name}' noma'lum shablon (faqat r58, r80, nak)")
            out[name] = _validate_receipt_cfg(name, cfg)
        return out

class CompanyOut(BaseModel):
    id: int
    name: str
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    is_active: bool
    created_at: datetime
    branches_count: int = 0
    tg_bot_token: Optional[str] = None
    tg_bot_username: Optional[str] = None
    receipt_templates: Optional[dict] = None
    daily_report_time: str = "17:30"
    low_stock_alert: bool = True
    expiration_alert: bool = True
    debt_deadline_alert: bool = True
    daily_report_enabled: bool = True
    daily_report_recipients: str = "owners_and_admins"
    shop_allow_out_of_stock_orders: bool = True
    pos_allow_negative_stock: bool = True
    delivery_fee: float = 0
    courier_bot_username: Optional[str] = None
    orders_auto_create_sale: bool = False
    pos_require_shift: bool = False
    promotions_auto_apply: bool = False
    fiscal_default_vat: Optional[int] = None
    credit_limit_scope: str = "distributor"
    manufacturing_enabled: bool = False
    distribution_enabled: bool = False
    marketplace_agents_enabled: bool = False
    marketplace_default_branch_id: Optional[int] = None
    shop_default_branch_id: Optional[int] = None
    stock_deduct_stage: str = "order_confirmed"
    agent_order_geo_radius_check: bool = True
    default_delivery_radius_m: int = 250
    receipt_format: str = "text"
    tg_protect_content: bool = False

    class Config:
        from_attributes = True


@router.get("", response_model=List[CompanyOut])
def list_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.super_admin:
        companies = db.query(Company).order_by(Company.id).all()
    else:
        companies = db.query(Company).filter(Company.id == current_user.company_id).order_by(Company.id).all()

    # tg_bot_token orqali kompaniyaning Telegram botini to'liq boshqarish mumkin
    # (xabar yuborish, webhook o'zgartirish) — faqat yuqori huquqli rollarga ko'rsatamiz
    is_privileged = current_user.role in (UserRole.admin, UserRole.director, UserRole.super_admin)

    result = []
    for c in companies:
        bc = db.query(func.count(Branch.id)).filter(Branch.company_id == c.id, Branch.is_active == True).scalar() or 0  # noqa: E712
        result.append(CompanyOut(
            id=c.id, name=c.name, address=c.address, phone=c.phone,
            email=c.email, is_active=c.is_active, created_at=c.created_at,
            branches_count=bc, tg_bot_token=c.tg_bot_token if is_privileged else None, tg_bot_username=c.tg_bot_username,
            receipt_templates=c.receipt_templates, daily_report_time=c.daily_report_time or "17:30",
            low_stock_alert=c.low_stock_alert if c.low_stock_alert is not None else True,
            expiration_alert=c.expiration_alert if c.expiration_alert is not None else True,
            debt_deadline_alert=c.debt_deadline_alert if c.debt_deadline_alert is not None else True,
            daily_report_enabled=c.daily_report_enabled if c.daily_report_enabled is not None else True,
            daily_report_recipients=c.daily_report_recipients or "owners_and_admins",
            shop_allow_out_of_stock_orders=c.shop_allow_out_of_stock_orders if c.shop_allow_out_of_stock_orders is not None else True,
        pos_allow_negative_stock=c.pos_allow_negative_stock if c.pos_allow_negative_stock is not None else True,
        delivery_fee=float(c.delivery_fee or 0) if hasattr(c, 'delivery_fee') else 0,
        courier_bot_username=getattr(c, 'courier_bot_username', None),
        orders_auto_create_sale=bool(getattr(c, 'orders_auto_create_sale', False) or False),
        pos_require_shift=bool(getattr(c, 'pos_require_shift', False) or False),
        promotions_auto_apply=bool(getattr(c, 'promotions_auto_apply', False) or False),
        fiscal_default_vat=getattr(c, 'fiscal_default_vat', None),
        credit_limit_scope=getattr(c, 'credit_limit_scope', None) or "distributor",
        manufacturing_enabled=bool(getattr(c, 'manufacturing_enabled', False)),
        distribution_enabled=bool(getattr(c, 'distribution_enabled', False)),
        marketplace_agents_enabled=bool(getattr(c, 'marketplace_agents_enabled', False)),
        marketplace_default_branch_id=getattr(c, 'marketplace_default_branch_id', None),
        shop_default_branch_id=getattr(c, 'shop_default_branch_id', None),
        stock_deduct_stage=getattr(c, 'stock_deduct_stage', 'order_confirmed') or 'order_confirmed',
        agent_order_geo_radius_check=c.agent_order_geo_radius_check if c.agent_order_geo_radius_check is not None else True,
        default_delivery_radius_m=c.default_delivery_radius_m if c.default_delivery_radius_m is not None else 250,
        receipt_format=getattr(c, 'receipt_format', 'text') or 'text',
        tg_protect_content=bool(getattr(c, 'tg_protect_content', False)),
        ))  # type: ignore[call-arg]
    return result

@router.get("/me/features")
def get_my_company_features(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Kompaniyada yoqilgan ixtiyoriy modullar (sidebar va sahifalar uchun)."""
    from app.core.features import company_has_feature
    cid = current_user.company_id
    if not cid:
        return {
            "manufacturing": False, "distribution": False, "marketplace_agents": False,
            "require_shift": False, "credit_limit_scope": "distributor",
        }
    c = db.query(Company).filter(Company.id == cid).first()
    return {
        "manufacturing": company_has_feature(db, cid, "manufacturing"),
        "distribution": company_has_feature(db, cid, "distribution"),
        "marketplace_agents": company_has_feature(db, cid, "marketplace_agents"),
        "require_shift": bool(c and c.pos_require_shift),
        "credit_limit_scope": (getattr(c, "credit_limit_scope", None) or "distributor") if c else "distributor",
    }


@router.get("/me/receipt_templates")
def get_my_receipt_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.company_id:
        return {"receipt_templates": {}}
    try:
        c = db.query(Company).filter(Company.id == current_user.company_id).first()
        if not c:
            return {"receipt_templates": {}}
        return {"receipt_templates": c.receipt_templates or {}}
    except Exception:
        return {"receipt_templates": {}}

@router.put("/me/receipt_templates")
def update_my_receipt_templates(
    data: ReceiptTemplatesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    if not current_user.company_id:
        raise HTTPException(status_code=400, detail="Kompaniyangiz topilmadi")
    c = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Kompaniya topilmadi")
    c.receipt_templates = data.receipt_templates
    db.commit()
    return {"ok": True, "receipt_templates": c.receipt_templates}

@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director)),
):
    c = Company(**data.model_dump())
    db.add(c)
    db.flush()
    # T0.7: filialsiz korxona bo'lmasin — asosiy filial avtomatik (auth.py register kabi)
    branch = Branch(name=f"{c.name} (Asosiy)", company_id=c.id, is_active=True, is_main=True)  # T1.4: asosiy filial
    db.add(branch)
    db.flush()
    # T1.4: asosiy filial uchun asosiy ombor (is_default) va kassa (yopiq) — auth.py register kabi
    from app.services.branch_provisioning import provision_branch
    provision_branch(db, branch, create_warehouse=True, create_wallet=True)
    db.commit()
    db.refresh(c)
    return CompanyOut(
        id=c.id, name=c.name, address=c.address, phone=c.phone, 
        email=c.email, is_active=c.is_active, created_at=c.created_at, 
        branches_count=1, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username, 
        receipt_templates=c.receipt_templates, daily_report_time=c.daily_report_time or "17:30",
        low_stock_alert=c.low_stock_alert if c.low_stock_alert is not None else True,
        expiration_alert=c.expiration_alert if c.expiration_alert is not None else True,
        debt_deadline_alert=c.debt_deadline_alert if c.debt_deadline_alert is not None else True,
        daily_report_enabled=c.daily_report_enabled if c.daily_report_enabled is not None else True,
        daily_report_recipients=c.daily_report_recipients or "owners_and_admins",
        shop_allow_out_of_stock_orders=c.shop_allow_out_of_stock_orders if c.shop_allow_out_of_stock_orders is not None else True,
        pos_allow_negative_stock=c.pos_allow_negative_stock if c.pos_allow_negative_stock is not None else True,
        delivery_fee=float(c.delivery_fee or 0) if hasattr(c, 'delivery_fee') else 0,
        courier_bot_username=getattr(c, 'courier_bot_username', None),
        orders_auto_create_sale=bool(getattr(c, 'orders_auto_create_sale', False) or False),
        pos_require_shift=bool(getattr(c, 'pos_require_shift', False) or False),
        promotions_auto_apply=bool(getattr(c, 'promotions_auto_apply', False) or False),
        fiscal_default_vat=getattr(c, 'fiscal_default_vat', None),
        credit_limit_scope=getattr(c, 'credit_limit_scope', None) or "distributor",
        manufacturing_enabled=bool(getattr(c, 'manufacturing_enabled', False)),
        distribution_enabled=bool(getattr(c, 'distribution_enabled', False)),
        marketplace_default_branch_id=getattr(c, 'marketplace_default_branch_id', None),
        shop_default_branch_id=getattr(c, 'shop_default_branch_id', None),
        stock_deduct_stage=getattr(c, 'stock_deduct_stage', 'order_confirmed') or 'order_confirmed',
        agent_order_geo_radius_check=c.agent_order_geo_radius_check if c.agent_order_geo_radius_check is not None else True,
        default_delivery_radius_m=c.default_delivery_radius_m if c.default_delivery_radius_m is not None else 250,
        receipt_format=getattr(c, 'receipt_format', 'text') or 'text',
        tg_protect_content=bool(getattr(c, 'tg_protect_content', False)),
    )  # type: ignore[call-arg]


@router.put("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    data: CompanyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director)),
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    # Faqat super_admin boshqa kompaniyani tahrirlay oladi — aks holda begona
    # kompaniyaning bot tokenini o'g'irlash yoki uni o'chirib qo'yish mumkin edi.
    if current_user.role != UserRole.super_admin and c.id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("pos_require_shift") is None:
        update_data.pop("pos_require_shift", None)   # NOT NULL ustun: null yuborilsa e'tiborsiz
    if update_data.get("promotions_auto_apply") is None:
        update_data.pop("promotions_auto_apply", None)   # NOT NULL ustun (C4.1, T4.3)
    if update_data.get("fiscal_default_vat") is not None and not (0 <= update_data["fiscal_default_vat"] <= 100):
        raise HTTPException(status_code=400, detail="QQS foizi 0 dan 100 gacha bo'lishi kerak")
    if update_data.get("credit_limit_scope") is None:
        update_data.pop("credit_limit_scope", None)  # NOT NULL ustun (T2.12)

    # Marketplace agentlari modulini faqat super_admin yoqib/o'chira oladi (tarix audit logga yoziladi)
    if "marketplace_agents_enabled" in update_data:
        if current_user.role != UserRole.super_admin:
            raise HTTPException(status_code=403, detail="Bu modulni faqat super admin boshqaradi")
        new_flag = bool(update_data["marketplace_agents_enabled"])
        if new_flag != bool(c.marketplace_agents_enabled):
            from app.core.audit import log_action
            log_action(db=db, action="MARKETPLACE_AGENTS_TOGGLE", entity_type="company", entity_id=c.id,
                       user_id=current_user.id, old_values={"enabled": bool(c.marketplace_agents_enabled)},
                       new_values={"enabled": new_flag}, ip_address=request.client.host if request.client else None)

    # T0.36: marketplace asosiy filiali — faqat shu korxonaning faol filiali (None = tozalash)
    if "marketplace_default_branch_id" in update_data:
        v = update_data["marketplace_default_branch_id"]
        if v is not None:
            ok = db.query(Branch.id).filter(
                Branch.id == v, Branch.company_id == c.id, Branch.is_active == True,  # noqa: E712
            ).first()
            if not ok:
                raise HTTPException(status_code=400, detail="Filial topilmadi yoki faol emas")

    # T3.13: Mini App standart filiali — faqat shu korxonaning faol filiali (None = tozalash)
    if "shop_default_branch_id" in update_data:
        v = update_data["shop_default_branch_id"]
        if v is not None:
            ok = db.query(Branch.id).filter(
                Branch.id == v, Branch.company_id == c.id, Branch.is_active == True,  # noqa: E712
            ).first()
            if not ok:
                raise HTTPException(status_code=400, detail="Filial topilmadi yoki faol emas")

    # Ishlab chiqarish va distribyutsiya modullarini yoqish huquqini tekshirish
    if current_user.role != UserRole.super_admin:
        from app.models.billing import CompanyPackage
        from datetime import datetime, timezone
        now_dt = datetime.now(timezone.utc)

        for feat_key, feat_name, col_name in [
            ("manufacturing", "Ishlab chiqarish", "manufacturing_enabled"),
            ("distribution", "Distribyutsiya", "distribution_enabled"),
            ("delivery_automation", "Yetkazib berish avtomatikasi", "orders_auto_create_sale"),
        ]:
            # T3.9: tarif yoki paket faqat modul YANGI yoqilayotganda talab qilinadi (o'chirish va
            # allaqachon yoqilgan bayroqni qayta saqlash — forma qayta saqlanishi — to'sqinlik qilmaydi)
            if col_name in update_data and update_data[col_name] and not getattr(c, col_name, False):
                has_in_tariff = bool(c.tariff and getattr(c.tariff, f"has_{feat_key}", False))
                has_active_pkg = False
                pkgs = db.query(CompanyPackage).filter(
                    CompanyPackage.company_id == c.id,
                    CompanyPackage.package_code == feat_key,
                ).all()
                for p in pkgs:
                    ends = p.ends_at
                    if ends and ends.tzinfo is None:
                        ends = ends.replace(tzinfo=timezone.utc)
                    if p.is_active and ends and ends > now_dt:
                        has_active_pkg = True
                        break

                if not has_in_tariff and not has_active_pkg:
                    raise HTTPException(
                        status_code=403,
                        detail=f"'{feat_name}' modulini faollashtirish uchun Tariflar sahifasidan mos tarif yoki paketni xarid qiling",
                    )

    if "tg_bot_token" in update_data:
        new_token = update_data["tg_bot_token"]
        if new_token:
            base_url = settings.SERVER_URL.rstrip("/") if settings.SERVER_URL else str(request.base_url).rstrip("/")
            webhook_url = f"{base_url}/api/telegram/webhook/{new_token}"
            bot_username = _telegram_setup_bot(new_token, webhook_url)
            update_data["tg_bot_username"] = bot_username
        else:
            if c.tg_bot_token:
                _telegram_delete_webhook(c.tg_bot_token)
            update_data["tg_bot_username"] = None

    if "courier_bot_token" in update_data:
        new_ctoken = update_data["courier_bot_token"]
        if new_ctoken:
            base_url = settings.SERVER_URL.rstrip("/") if settings.SERVER_URL else str(request.base_url).rstrip("/")
            webhook_url = f"{base_url}/api/courier-bot/webhook/{new_ctoken}"
            cbot_username = _telegram_setup_bot(new_ctoken, webhook_url)
            update_data["courier_bot_username"] = cbot_username
        else:
            if getattr(c, "courier_bot_token", None):
                _telegram_delete_webhook(c.courier_bot_token)
            update_data["courier_bot_username"] = None

    for k, v in update_data.items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    bc = db.query(func.count(Branch.id)).filter(Branch.company_id == c.id, Branch.is_active == True).scalar() or 0  # noqa: E712
    return CompanyOut(
        id=c.id, name=c.name, address=c.address, phone=c.phone,
        email=c.email, is_active=c.is_active, created_at=c.created_at,
        branches_count=bc, tg_bot_token=c.tg_bot_token, tg_bot_username=c.tg_bot_username, 
        receipt_templates=c.receipt_templates, daily_report_time=c.daily_report_time or "17:30",
        low_stock_alert=c.low_stock_alert if c.low_stock_alert is not None else True,
        expiration_alert=c.expiration_alert if c.expiration_alert is not None else True,
        debt_deadline_alert=c.debt_deadline_alert if c.debt_deadline_alert is not None else True,
        daily_report_enabled=c.daily_report_enabled if c.daily_report_enabled is not None else True,
        daily_report_recipients=c.daily_report_recipients or "owners_and_admins",
        shop_allow_out_of_stock_orders=c.shop_allow_out_of_stock_orders if c.shop_allow_out_of_stock_orders is not None else True,
        pos_allow_negative_stock=c.pos_allow_negative_stock if c.pos_allow_negative_stock is not None else True,
        delivery_fee=float(c.delivery_fee or 0) if hasattr(c, 'delivery_fee') else 0,
        courier_bot_username=getattr(c, 'courier_bot_username', None),
        orders_auto_create_sale=bool(getattr(c, 'orders_auto_create_sale', False) or False),
        pos_require_shift=bool(getattr(c, 'pos_require_shift', False) or False),
        promotions_auto_apply=bool(getattr(c, 'promotions_auto_apply', False) or False),
        fiscal_default_vat=getattr(c, 'fiscal_default_vat', None),
        credit_limit_scope=getattr(c, 'credit_limit_scope', None) or "distributor",
        manufacturing_enabled=bool(getattr(c, 'manufacturing_enabled', False)),
        distribution_enabled=bool(getattr(c, 'distribution_enabled', False)),
        marketplace_agents_enabled=bool(getattr(c, 'marketplace_agents_enabled', False)),
        marketplace_default_branch_id=getattr(c, 'marketplace_default_branch_id', None),
        shop_default_branch_id=getattr(c, 'shop_default_branch_id', None),
        stock_deduct_stage=getattr(c, 'stock_deduct_stage', 'order_confirmed') or 'order_confirmed',
        agent_order_geo_radius_check=c.agent_order_geo_radius_check if c.agent_order_geo_radius_check is not None else True,
        default_delivery_radius_m=c.default_delivery_radius_m if c.default_delivery_radius_m is not None else 250,
        receipt_format=getattr(c, 'receipt_format', 'text') or 'text',
        tg_protect_content=bool(getattr(c, 'tg_protect_content', False)),
    )  # type: ignore[call-arg]


