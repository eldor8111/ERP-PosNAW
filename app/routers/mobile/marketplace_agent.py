"""Marketplace savdo agenti mobil API'si (/api/mobile/marketplace/*).

Agent mavjud distribyutor korxonasiga biriktiriladi (yangi korxona ochilmaydi):
  1. /register — org_code bo'yicha, status=pending, rol=marketplace_agent
  2. /auth/login — pending agent ham kira oladi (kategoriya tanlashi uchun)
  3. /categories, /my-categories — mir-maza.uz kategoriyalari
  4. /products — faqat FAOL agent (pending/blocked — 403)

Har so'rovda korxonada marketplace_agents_enabled tekshiriladi.
"""
import hmac
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.audit import log_action
from app.core.limiter import limiter
from app.core.security import decode_token, hash_password, verify_password
from app.database import get_db
from app.core.dependencies import bearer_scheme
from app.models.company import Company
from app.models.marketplace import (
    MarketplaceAgentCategory, MarketplaceAgentTransaction, MarketplaceProduct,
    MarketplaceProductStatus, MarketplaceTransactionType,
)
from app.models.mobile_device import MobileDevice
from app.models.branch import Branch
from app.models.warehouse import Warehouse
from app.models.user import User, UserRole, UserStatus
from app.routers.mobile.base import _issue_tokens
from app.schemas.marketplace import (
    AgentCategoriesIn, AgentLoginIn, AgentRefreshIn, AgentRegisterIn, AgentSendCodeIn, MirmazaWebhookIn,
    ProductIn, ProductUpdateIn,
)
from app.services import marketplace_service as mp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mobile/marketplace", tags=["mobile-marketplace"])

# T0.18: bir telefon raqamiga bir soatda ko'pi bilan shuncha SMS kodi
_SMS_CODE_PER_PHONE_PER_HOUR = 5
# T0.18: webhook'dagi item.total ning mahsulot narxi*miqdor dan ruxsat etilgan og'ishi
_WEBHOOK_TOTAL_TOLERANCE_RATIO = Decimal("0.05")   # 5 %
_WEBHOOK_TOTAL_TOLERANCE_ABS = Decimal("1000")      # yoki 1000 so'm (qaysi katta bo'lsa)

# Moderatsiyani qayta talab qiladigan maydonlar (narx, qoldiq, nom, rasm, kategoriya)
_MODERATED_FIELDS = ("name", "price", "qty", "images", "description", "category_id")


# ── Yordamchilar ───────────────────────────────────────────────────────────

def _feature_company(db: Session, company_id: Optional[int]) -> Company:
    c = db.query(Company).filter(Company.id == company_id).first() if company_id else None
    if not c or not c.is_active or not c.marketplace_agents_enabled:
        raise HTTPException(status_code=403, detail="Marketplace agentlari moduli bu korxona uchun yoqilmagan")
    return c


def get_agent(
    credentials=Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """pending va active agentni qabul qiladi (blocked/inactive — yo'q)."""
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Token yaroqsiz yoki muddati o'tgan")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if not user or user.role != UserRole.marketplace_agent:
        raise HTTPException(status_code=403, detail="Faqat marketplace agentlari uchun")
    if user.status in (UserStatus.blocked, UserStatus.inactive):
        raise HTTPException(status_code=403, detail="Hisobingiz bloklangan")
    dev = payload.get("dev")
    device = db.query(MobileDevice).filter(MobileDevice.id == dev, MobileDevice.user_id == user.id).first() if dev else None
    if not device or device.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Qurilma sessiyasi bekor qilingan")
    _feature_company(db, user.company_id)
    return user


def get_active_agent(user: User = Depends(get_agent)) -> User:
    if user.status != UserStatus.active:
        raise HTTPException(status_code=403, detail="Hisobingiz hali faollashtirilmagan. Korxona admini tasdiqlashini kuting.")
    return user


def _upsert_device(db: Session, user: User, data) -> MobileDevice:
    device = db.query(MobileDevice).filter(
        MobileDevice.user_id == user.id, MobileDevice.device_id == data.device_id).first()
    if not device:
        device = MobileDevice(user_id=user.id, device_id=data.device_id, company_id=user.company_id)
        db.add(device)
    device.company_id = user.company_id
    device.platform, device.model, device.app_version = data.platform, data.model, data.app_version
    device.last_seen_at = datetime.now(timezone.utc)
    device.revoked_at = None
    db.flush()
    return device


def _agent_out(db: Session, user: User) -> dict:
    cats = db.query(MarketplaceAgentCategory.category_id).filter(MarketplaceAgentCategory.user_id == user.id).all()
    names = mp.category_name_map()
    ids = [c[0] for c in cats]
    company = db.query(Company).filter(Company.id == user.company_id).first()
    return {
        "id": user.id, "name": user.name, "phone": user.phone,
        "status": user.status.value, "company_id": user.company_id,
        "org_code": company.org_code if company else "",
        "company_name": company.name if company else "",
        "categories": [{"id": i, "name": names.get(i)} for i in ids],
        "needs_category_selection": len(ids) == 0,
        "subscription_ends_at": user.subscription_ends_at.isoformat() if user.subscription_ends_at else None,
        "is_trial": bool(user.is_trial),
        "paid_amount": float(user.paid_amount or 0),
    }


def _product_out(p: MarketplaceProduct, names: dict) -> dict:
    status_str = p.status.value if hasattr(p.status, "value") else str(p.status or "")
    cat_name = names.get(p.category_id) if names else None
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "price": float(p.price or 0), "qty": float(p.qty or 0),
        "category_id": p.category_id, "category_name": cat_name,
        "barcode": p.barcode, "sku": p.sku, "images": p.images or [],
        "status": status_str, "reject_reason": p.reject_reason,
        # T3.17: tasdiqlanganda kirim qilingan ombor (agent ilovasi ko'rsatadi)
        "warehouse_id": p.warehouse_id, "purchase_order_id": p.purchase_order_id,
        "warehouse_name": p.warehouse.name if p.warehouse_id and p.warehouse else None,
        "preferred_warehouse_id": p.preferred_warehouse_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _agent_category_ids(db: Session, user: User) -> set:
    return {r[0] for r in db.query(MarketplaceAgentCategory.category_id).filter(
        MarketplaceAgentCategory.user_id == user.id).all()}


def _check_category(db: Session, user: User, category_id: int) -> None:
    if category_id not in _agent_category_ids(db, user):
        raise HTTPException(status_code=400, detail="Bu kategoriyada sotish uchun ruxsatingiz yo'q. Avval kategoriyani tanlang.")


def check_warehouse(db: Session, company_id: Optional[int], warehouse_id: Optional[int]) -> None:
    """T3.17: agent ko'rsatgan topshirish ombori shu korxonaning faol ombori bo'lishi shart."""
    if warehouse_id is None:
        return
    ok = db.query(Warehouse.id).filter(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id,
        Warehouse.is_active == True,  # noqa: E712
    ).first()
    if not ok:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")


# ── Ro'yxatdan o'tish va kirish ────────────────────────────────────────────

@router.post("/register/send-code")
@limiter.limit("3/minute")
async def send_register_code(request: Request, data: AgentSendCodeIn, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.org_code == data.org_code.strip()).first()
    if not company:
        raise HTTPException(status_code=404, detail="Kiritilgan tashkilot kodi topilmadi")
    if not company.is_active:
        raise HTTPException(status_code=400, detail="Ushbu tashkilot nofaol holatda")
    if not company.marketplace_agents_enabled:
        raise HTTPException(status_code=400, detail="Ushbu tashkilotda savdo agentlari tizimi yoqilmagan")
    
    phone = mp.normalize_phone(data.phone)
    if db.query(User).filter(User.phone.in_([phone, f"+{phone}"])).first():
        raise HTTPException(status_code=409, detail="Bu telefon raqami allaqachon ro'yxatdan o'tgan")
    
    from app.models.user import SmsVerification
    from datetime import timedelta

    # T0.18: bir telefon uchun soatlik urinishlar limiti (SmsVerification jadvalidan)
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = db.query(SmsVerification).filter(
        SmsVerification.phone == phone,
        SmsVerification.created_at >= hour_ago,
    ).count()
    if recent >= _SMS_CODE_PER_PHONE_PER_HOUR:
        raise HTTPException(status_code=429, detail="Bu raqamga juda ko'p kod so'raldi. Bir soatdan keyin urinib ko'ring")

    # T0.18: kriptografik tasodifiy 5 xonali kod
    code = str(secrets.randbelow(90000) + 10000)

    # Eskiz SMS orqali yuborish
    sms_sent = False
    try:
        from app.services.eskiz_service import eskiz_service
        msg = f"E-Code.uz saytida ro'yxatdan o'tish uchun tasdiqlash kodi: {code}. Kodni hech kimga bermang."
        res = await eskiz_service.send_sms(phone, msg)
        sms_sent = bool(res.get("success", False))
        if not sms_sent:
            logger.warning("Agent ro'yxati: SMS yuborilmadi (phone=%s): %s", phone, res.get("error"))
    except Exception as e:
        logger.warning("Agent ro'yxati: SMS xatosi (phone=%s): %s", phone, e)

    # T0.18: SMS ketmagan bo'lsa kod saqlanmaydi va javobda ham qaytarilmaydi
    if not sms_sent:
        raise HTTPException(status_code=503, detail="SMS yuborilmadi, keyinroq urinib ko'ring")

    sms = SmsVerification(
        phone=phone,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db.add(sms)
    db.commit()

    return {
        "ok": True,
        "detail": "Tasdiqlash kodi yuborildi",
        "sms_sent": True,
    }


@router.post("/register", status_code=201)
@limiter.limit("5/minute")
def register_agent(request: Request, data: AgentRegisterIn, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.org_code == data.org_code.strip()).first()
    if not company:
        raise HTTPException(status_code=404, detail="Kiritilgan tashkilot kodi topilmadi")
    if not company.is_active:
        raise HTTPException(status_code=400, detail="Ushbu tashkilot nofaol holatda")
    if not company.marketplace_agents_enabled:
        raise HTTPException(status_code=400, detail="Ushbu tashkilotda savdo agentlari tizimi yoqilmagan")

    phone = mp.normalize_phone(data.phone)
    if db.query(User).filter(User.phone.in_([phone, f"+{phone}"])).first():
        raise HTTPException(status_code=409, detail="Bu telefon raqami allaqachon ro'yxatdan o'tgan")
        
    from app.models.user import SmsVerification
    sms = db.query(SmsVerification).filter(
        SmsVerification.phone == phone,
        SmsVerification.code == data.sms_code,
        SmsVerification.is_used == False,
        SmsVerification.expires_at > datetime.now(timezone.utc)
    ).order_by(SmsVerification.id.desc()).first()
    
    if not sms:
        raise HTTPException(status_code=400, detail="Tasdiqlash kodi noto'g'ri yoki eskirgan")
    
    sms.is_used = True

    # User yaratish
    user = User(
        name=data.name.strip(), phone=phone, hashed_password=hash_password(data.password),
        role=UserRole.marketplace_agent, status=UserStatus.pending, company_id=company.id,
    )
    db.add(user)
    db.flush()
    log_action(db=db, action="MARKETPLACE_AGENT_REGISTER", entity_type="user", entity_id=user.id, user_id=user.id,
               ip_address=request.client.host if request.client else None, new_values={"company_id": company.id})
    device = _upsert_device(db, user, data)
    out = {**_issue_tokens(user, device), "user": _agent_out(db, user)}
    db.commit()
    return out


@router.post("/auth/login")
@limiter.limit("10/minute")
def agent_login(request: Request, data: AgentLoginIn, db: Session = Depends(get_db)):
    phone = mp.normalize_phone(data.phone)
    phones = [phone, f"+{phone}"]
    user = db.query(User).filter(User.phone.in_(phones), User.role == UserRole.marketplace_agent).first()
    if not user:
        # T3.17: dala agenti (role=agent) rolini jimgina o'zgartirmaymiz — aniq 403
        field = db.query(User.id, User.hashed_password).filter(
            User.phone.in_(phones), User.role == UserRole.agent).first()
        if field and verify_password(data.password, field.hashed_password):
            raise HTTPException(
                status_code=403,
                detail="Bu ilova marketplace agentlari uchun. Dala agenti ilovasidan foydalaning")
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Telefon yoki parol noto'g'ri")
    if user.status in (UserStatus.blocked, UserStatus.inactive):
        raise HTTPException(status_code=403, detail="Hisobingiz bloklangan")
    _feature_company(db, user.company_id)
    device = _upsert_device(db, user, data)
    out = {**_issue_tokens(user, device), "user": _agent_out(db, user)}
    db.commit()
    return out


@router.post("/auth/refresh")
@limiter.limit("30/minute")
def agent_refresh(request: Request, data: AgentRefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh" or payload.get("dev") is None:
        raise HTTPException(status_code=401, detail="Sessiya tugagan, qaytadan kiring")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    device = db.query(MobileDevice).filter(
        MobileDevice.id == int(payload["dev"]), MobileDevice.user_id == int(payload["sub"])).first()
    if (not user or not device or device.revoked_at is not None or user.role != UserRole.marketplace_agent
            or user.status in (UserStatus.blocked, UserStatus.inactive)):
        raise HTTPException(status_code=401, detail="Sessiya tugagan, qaytadan kiring")
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return _issue_tokens(user, device)

@router.get("/auth/payme-checkout")
def get_payme_checkout_url(
    months: int = Query(1, ge=1, le=12),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_agent)
):
    from app.config import settings
    import base64
    if not settings.PAYME_MERCHANT_ID:
        raise HTTPException(status_code=500, detail="Payme merchant id topilmadi")
        
    if months == 6:
        amount_som = 1000000  # 6 oy: 1 000 000 UZS (chegirma bilan)
    elif months == 3:
        amount_som = 550000   # 3 oy: 550 000 UZS (chegirma bilan)
    else:
        amount_som = 200000   # 1 oy: 200 000 UZS

    amount_tiyin = int(amount_som * 100)
    clean_phone = (user.phone or "").replace("+", "").replace(" ", "").replace("-", "")
    # Payme Merchant kabinetida hisob parametri 'org_code' deb sozlangan.
    # Shuning uchun agent telefon raqami ac.org_code orqali uzatiladi.
    raw = f"m={settings.PAYME_MERCHANT_ID};ac.org_code={clean_phone};a={amount_tiyin}"
    encoded = base64.b64encode(raw.encode()).decode()
    base_url = "https://checkout.test.paycom.uz" if settings.PAYME_IS_TEST else "https://checkout.paycom.uz"
    
    return {"checkout_url": f"{base_url}/{encoded}", "amount": amount_som, "months": months}


@router.get("/me")
def agent_me(db: Session = Depends(get_db), user: User = Depends(get_agent)):
    return _agent_out(db, user)


@router.post("/upload")
async def upload_marketplace_image(
    file: UploadFile = File(...),
    remove_bg: bool = Query(False),
    user: User = Depends(get_agent),
):
    if file.content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg"):
        raise HTTPException(status_code=400, detail="Faqat rasm formatlari (JPG, PNG, WEBP) qabul qilinadi")
    
    content = await file.read(10 * 1024 * 1024)  # 10MB limit
    import anyio
    from app.config import settings
    from app.routers.uploads import _store
    from app.utils import image_pipeline as ip

    bg_removed = False
    # Agar fonni tozalash so'ralgan bo'lsa
    if remove_bg:
        try:
            from app.services.bg_removal_worker import remove_background
            content = await anyio.to_thread.run_sync(remove_background, content)
            bg_removed = True
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Marketplace image bg removal fallback: %s", e)
            # rembg xatosi yoki o'rnatilmagan bo'lsa, xavfsiz oq fon bilan saqlash
            try:
                def _fallback_white(raw_bytes: bytes) -> bytes:
                    img = ip.flatten_on_white(ip.load_image(raw_bytes))
                    return ip.to_jpeg(img, quality=90)
                content = await anyio.to_thread.run_sync(_fallback_white, content)
            except Exception:
                pass
    
    filename = await anyio.to_thread.run_sync(_store, content)
    rel_url = ip.URL_PREFIX + filename
    base = settings.SERVER_URL.rstrip("/") if settings.SERVER_URL else "https://savdo.e-code.uz"
    full_url = f"{base}{rel_url}"
    return {"url": full_url, "relative_url": rel_url, "bg_removed": bg_removed}


# ── Kategoriyalar ──────────────────────────────────────────────────────────

@router.get("/categories")
def list_categories(user: User = Depends(get_agent)):
    return {
        "items": mp.fetch_categories(),
        "tree": mp.fetch_categories_tree(),
    }


@router.put("/my-categories")
def set_my_categories(data: AgentCategoriesIn, db: Session = Depends(get_db), user: User = Depends(get_agent)):
    """Nofaol agent ham kategoriya tanlay oladi (ТЗ 5-band). Mahsulotlari bor
    kategoriyani olib tashlab bo'lmaydi."""
    valid = mp.category_ids()
    if not valid:
        raise HTTPException(status_code=503, detail="Kategoriyalar manbasi hozircha mavjud emas, keyinroq urinib ko'ring")
    wanted = set(data.category_ids)
    unknown = wanted - valid
    if unknown:
        raise HTTPException(status_code=400, detail=f"Noma'lum kategoriyalar: {sorted(unknown)}")
    current = _agent_category_ids(db, user)
    removed = current - wanted
    if removed:
        used = db.query(MarketplaceProduct.id).filter(
            MarketplaceProduct.agent_id == user.id, MarketplaceProduct.category_id.in_(removed)).first()
        if used:
            raise HTTPException(status_code=409, detail="Mahsuloti bor kategoriyani olib tashlab bo'lmaydi")
        db.query(MarketplaceAgentCategory).filter(
            MarketplaceAgentCategory.user_id == user.id,
            MarketplaceAgentCategory.category_id.in_(removed)).delete(synchronize_session=False)
    for cid in wanted - current:
        db.add(MarketplaceAgentCategory(user_id=user.id, category_id=cid, company_id=user.company_id))
    log_action(db=db, action="MARKETPLACE_AGENT_CATEGORIES", entity_type="user", entity_id=user.id, user_id=user.id,
               old_values={"ids": sorted(current)}, new_values={"ids": sorted(wanted)})
    db.commit()
    return _agent_out(db, user)


# ── Mahsulotlar (faqat faol agent) ─────────────────────────────────────────

@router.get("/products")
def my_products(
    status: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=100),
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(get_active_agent),
):
    query = db.query(MarketplaceProduct).filter(MarketplaceProduct.agent_id == user.id)
    if status:
        try:
            query = query.filter(MarketplaceProduct.status == MarketplaceProductStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Noto'g'ri status")
    if q:
        query = query.filter(MarketplaceProduct.name.ilike(f"%{q.strip()}%"))
    total = query.count()
    rows = query.order_by(MarketplaceProduct.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    names = mp.category_name_map()
    return {"total": total, "page": page, "items": [_product_out(p, names) for p in rows]}


@router.get("/warehouses")
def list_warehouses(db: Session = Depends(get_db), user: User = Depends(get_active_agent)):
    """T3.17: topshirish ombori tanlovi — faqat korxonada 2 va undan ko'p faol filial bo'lsa to'ldiriladi."""
    branches = db.query(func.count(Branch.id)).filter(
        Branch.company_id == user.company_id, Branch.is_active == True,  # noqa: E712
    ).scalar() or 0
    if branches < 2:
        return []
    rows = db.query(Warehouse, Branch.name).outerjoin(Branch, Branch.id == Warehouse.branch_id).filter(
        Warehouse.company_id == user.company_id, Warehouse.is_active == True,  # noqa: E712
    ).order_by(Warehouse.name, Warehouse.id).all()
    return [{"id": w.id, "name": w.name, "branch_name": bn} for w, bn in rows]


@router.post("/products", status_code=201)
def create_product(data: ProductIn, db: Session = Depends(get_db), user: User = Depends(get_active_agent)):
    _check_category(db, user, data.category_id)
    check_warehouse(db, user.company_id, data.preferred_warehouse_id)
    p = MarketplaceProduct(
        company_id=user.company_id, agent_id=user.id, name=data.name.strip(),
        preferred_warehouse_id=data.preferred_warehouse_id,
        description=data.description, price=data.price, qty=data.qty, category_id=data.category_id,
        barcode=data.barcode, sku=data.sku, images=mp.clamp_images(data.images),
        status=MarketplaceProductStatus.review if data.submit else MarketplaceProductStatus.draft,
    )
    db.add(p)
    db.flush()
    log_action(db=db, action="MARKETPLACE_PRODUCT_CREATE", entity_type="marketplace_product", entity_id=p.id,
               user_id=user.id, new_values={"name": p.name, "status": p.status.value})
    db.commit()
    return _product_out(p, mp.category_name_map())


def _own_product(db: Session, user: User, product_id: int) -> MarketplaceProduct:
    p = db.query(MarketplaceProduct).filter(
        MarketplaceProduct.id == product_id, MarketplaceProduct.agent_id == user.id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return p


@router.put("/products/{product_id}")
def update_product(product_id: int, data: ProductUpdateIn, db: Session = Depends(get_db),
                   user: User = Depends(get_active_agent)):
    p = _own_product(db, user, product_id)
    changes = data.model_dump(exclude_unset=True, exclude={"submit"})
    if "category_id" in changes and changes["category_id"] != p.category_id:
        _check_category(db, user, changes["category_id"])
    if "images" in changes:
        changes["images"] = mp.clamp_images(changes["images"])
    if "preferred_warehouse_id" in changes:
        check_warehouse(db, user.company_id, changes["preferred_warehouse_id"])
    old = {k: (float(getattr(p, k)) if isinstance(getattr(p, k), Decimal) else getattr(p, k)) for k in changes}
    needs_moderation = any(
        k in _MODERATED_FIELDS and changes[k] != getattr(p, k) for k in changes)
    for k, v in changes.items():
        setattr(p, k, v)
    # Tasdiqlangan mahsulotning muhim tahriri qayta moderatsiyaga tushadi;
    # qoldiq/shtrix-kod o'zgarishi moderatsiyani talab qilmaydi.
    if p.status == MarketplaceProductStatus.approved and needs_moderation:
        p.status = MarketplaceProductStatus.review
    elif p.status in (MarketplaceProductStatus.draft, MarketplaceProductStatus.rejected) and data.submit:
        p.status = MarketplaceProductStatus.review
        p.reject_reason = None
    log_action(db=db, action="MARKETPLACE_PRODUCT_UPDATE", entity_type="marketplace_product", entity_id=p.id,
               user_id=user.id, old_values=old, new_values={"status": p.status.value, **{
                   k: (float(v) if isinstance(v, Decimal) else v) for k, v in changes.items()}})
    db.commit()
    return _product_out(p, mp.category_name_map())


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_active_agent)):
    """Qoralama/rad etilgan mahsulot to'g'ridan-to'g'ri o'chadi. Tasdiqlangan
    mahsulotni agent o'chira olmaydi — admin ko'rib chiqishi uchun
    tekshiruvga qaytariladi (ТЗ: o'chirishga so'rov)."""
    p = _own_product(db, user, product_id)
    if p.status in (MarketplaceProductStatus.draft, MarketplaceProductStatus.rejected):
        log_action(db=db, action="MARKETPLACE_PRODUCT_DELETE", entity_type="marketplace_product",
                   entity_id=p.id, user_id=user.id, old_values={"name": p.name})
        db.delete(p)
        db.commit()
        return {"ok": True, "deleted": True}
    p.status = MarketplaceProductStatus.review
    p.reject_reason = "Agent o'chirishni so'radi"
    log_action(db=db, action="MARKETPLACE_PRODUCT_DELETE_REQUEST", entity_type="marketplace_product",
               entity_id=p.id, user_id=user.id)
    db.commit()
    return {"ok": True, "deleted": False, "detail": "O'chirish so'rovi adminga yuborildi"}


# ── Balans ─────────────────────────────────────────────────────────────────

def agent_balance(db: Session, agent_id: int) -> dict:
    rows = db.query(MarketplaceAgentTransaction.transaction_type, func.coalesce(func.sum(MarketplaceAgentTransaction.amount), 0)) \
        .filter(MarketplaceAgentTransaction.agent_id == agent_id).group_by(MarketplaceAgentTransaction.transaction_type).all()
    s = {r[0]: Decimal(r[1]) for r in rows}
    T = MarketplaceTransactionType
    income, commission = s.get(T.income, Decimal(0)), s.get(T.commission, Decimal(0))
    refund, payout = s.get(T.refund, Decimal(0)), s.get(T.payout, Decimal(0))

    # Mir-maza skladiga topshirilgan mahsulotlar statistikasi
    prods = db.query(MarketplaceProduct).filter(
        MarketplaceProduct.agent_id == agent_id,
        MarketplaceProduct.status == MarketplaceProductStatus.approved,
    ).all()
    goods_count = len(prods)
    goods_qty = sum(float(p.qty or 0) for p in prods)
    goods_total_value = sum(float(p.price or 0) * float(p.qty or 0) for p in prods)
    warehouse_debt = max(0.0, goods_total_value - float(payout))

    return {
        "sales": float(income), "commission": float(commission), "refunds": float(refund),
        "paid_out": float(payout), "balance": float(income - commission - refund - payout),
        "goods_count": goods_count,
        "goods_qty": goods_qty,
        "goods_total_value": goods_total_value,
        "warehouse_debt": warehouse_debt,
    }


@router.get("/balance")
def my_balance(db: Session = Depends(get_db), user: User = Depends(get_agent)):
    return agent_balance(db, user.id)


@router.get("/transactions")
def my_transactions(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                    db: Session = Depends(get_db), user: User = Depends(get_active_agent)):
    q = db.query(MarketplaceAgentTransaction).filter(MarketplaceAgentTransaction.agent_id == user.id)
    total = q.count()
    rows = q.order_by(MarketplaceAgentTransaction.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [{
        "id": t.id, "type": t.transaction_type.value, "amount": float(t.amount), "order_id": t.order_id,
        "note": t.note, "created_at": t.created_at.isoformat() if t.created_at else None} for t in rows]}


# ── Bildirishnomalar ───────────────────────────────────────────────────────

@router.get("/notifications")
def my_notifications(
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db), user: User = Depends(get_agent),
):
    from app.models.marketplace import MarketplaceAgentNotification
    q = db.query(MarketplaceAgentNotification).filter(MarketplaceAgentNotification.agent_id == user.id)
    unread_count = q.filter(MarketplaceAgentNotification.is_read == False).count()
    total = q.count()
    rows = q.order_by(MarketplaceAgentNotification.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "unread_count": unread_count,
        "items": [{
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "type": n.notif_type,
            "data": n.data,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        } for n in rows],
    }


@router.post("/notifications/{notif_id}/read")
def mark_notification_read(
    notif_id: int, db: Session = Depends(get_db), user: User = Depends(get_agent),
):
    from app.models.marketplace import MarketplaceAgentNotification
    n = db.query(MarketplaceAgentNotification).filter(
        MarketplaceAgentNotification.id == notif_id,
        MarketplaceAgentNotification.agent_id == user.id,
    ).first()
    if n:
        n.is_read = True
        db.commit()
    return {"ok": True}


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db), user: User = Depends(get_agent),
):
    from app.models.marketplace import MarketplaceAgentNotification
    db.query(MarketplaceAgentNotification).filter(
        MarketplaceAgentNotification.agent_id == user.id,
        MarketplaceAgentNotification.is_read == False,
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"ok": True}


# ── Mir-maza Webhook: Buyurtma / Sotuv bildirishnomasi ─────────────────────

def _verify_webhook_key(request: Request) -> None:
    """T0.18: X-Integration-Key sarlavhasini MARKETPLACE_API_TOKEN bilan doimiy vaqtda solishtirish.
    Token sozlanmagan bo'lsa 503, mos kelmasa (yoki yo'q bo'lsa) 401."""
    expected = (settings.MARKETPLACE_API_TOKEN or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Marketplace integratsiyasi sozlanmagan")
    got = (request.headers.get("X-Integration-Key") or "").strip()
    if not got or not hmac.compare_digest(got.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Integratsiya kaliti noto'g'ri")


@router.post("/webhook/order")
def mirmaza_order_webhook(
    request: Request, data: MirmazaWebhookIn, db: Session = Depends(get_db),
):
    """Mir-maza da buyurtma yaratilganda yoki sotilganda to'g'ridan-to'g'ri chaqiriladigan webhook.

    T0.18: X-Integration-Key majburiy; har item alohida savepoint'da; (order_id + mahsulot)
    bo'yicha income allaqachon yozilgan bo'lsa o'tkazib yuboriladi (idempotent); item.total
    mahsulot narxi*miqdor dan ruxsat etilgan og'ishdan ko'p farq qilsa rad etiladi.
    """
    _verify_webhook_key(request)
    market_order_id = data.marketOrderId

    processed = skipped = rejected = 0
    for item in data.items:
        ext_id = item.externalId or ""
        if not ext_id.startswith("ECODE-PROD-"):
            continue
        try:
            with db.begin_nested():
                mp_id = int(ext_id.split("-")[2])
                mp_item = db.query(MarketplaceProduct).filter(MarketplaceProduct.id == mp_id).first()
                if not mp_item:
                    rejected += 1
                    logger.warning("Webhook: mahsulot topilmadi (%s, order=%s)", ext_id, market_order_id)
                    continue

                existing = db.query(MarketplaceAgentTransaction).filter(
                    MarketplaceAgentTransaction.order_id == market_order_id,
                    MarketplaceAgentTransaction.marketplace_product_id == mp_item.id,
                    MarketplaceAgentTransaction.transaction_type == MarketplaceTransactionType.income,
                ).first()
                if existing:
                    skipped += 1
                    continue

                qty_ordered = Decimal(str(item.quantity))
                item_total = Decimal(str(item.total))
                expected_total = Decimal(str(mp_item.price or 0)) * qty_ordered
                allowed = max(expected_total * _WEBHOOK_TOTAL_TOLERANCE_RATIO, _WEBHOOK_TOTAL_TOLERANCE_ABS)
                if abs(item_total - expected_total) > allowed:
                    rejected += 1
                    logger.warning("Webhook: summa mos emas (%s, order=%s, total=%s, kutilgan=%s)",
                                   ext_id, market_order_id, item_total, expected_total)
                    continue

                mp_item.qty = max(Decimal("0"), Decimal(str(mp_item.qty or 0)) - qty_ordered)

                tx = MarketplaceAgentTransaction(
                    agent_id=mp_item.agent_id,
                    company_id=mp_item.company_id,
                    order_id=market_order_id,
                    marketplace_product_id=mp_item.id,
                    transaction_type=MarketplaceTransactionType.income,
                    amount=item_total,
                    note=f"Mir-maza buyurtmasi #{market_order_id} ({mp_item.name})",
                )
                db.add(tx)
                db.flush()

                mp.notify_agent(
                    db=db,
                    agent_id=mp_item.agent_id,
                    company_id=mp_item.company_id,
                    title="Mahsulotingiz sotildi! 🎉",
                    body=f"Mir-maza da '{mp_item.name}' mahsulotingizdan {qty_ordered:.0f} dona sotildi. Summa: {item_total:,.0f} so'm.",
                    notif_type="order_sold",
                    data={"product_id": mp_item.id, "order_id": market_order_id, "amount": float(item_total)},
                )
                processed += 1
        except Exception as e:
            # Savepoint faqat shu item'ni bekor qiladi, qolgan itemlar saqlanadi
            rejected += 1
            logger.warning("Webhookda xatolik (%s, order=%s): %s", ext_id, market_order_id, e)
    db.commit()
    return {"status": "ok", "processed": processed, "skipped": skipped, "rejected": rejected}
