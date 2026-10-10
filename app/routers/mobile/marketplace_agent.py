"""Marketplace savdo agenti mobil API'si (/api/mobile/marketplace/*).

Agent mavjud distribyutor korxonasiga biriktiriladi (yangi korxona ochilmaydi):
  1. /register — org_code bo'yicha, status=pending, rol=marketplace_agent
  2. /auth/login — pending agent ham kira oladi (kategoriya tanlashi uchun)
  3. /categories, /my-categories — mir-maza.uz kategoriyalari
  4. /products — faqat FAOL agent (pending/blocked — 403)

Har so'rovda korxonada marketplace_agents_enabled tekshiriladi.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

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
from app.models.user import User, UserRole, UserStatus
from app.routers.mobile.base import _issue_tokens
from app.schemas.marketplace import (
    AgentCategoriesIn, AgentLoginIn, AgentRefreshIn, AgentRegisterIn, ProductIn, ProductUpdateIn,
)
from app.services import marketplace_service as mp

router = APIRouter(prefix="/mobile/marketplace", tags=["mobile-marketplace"])

# Moderatsiyani qayta talab qiladigan maydonlar (ТЗ 7-band)
_MODERATED_FIELDS = ("name", "price", "images", "description", "category_id")


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
    return {
        "id": user.id, "name": user.name, "phone": user.phone,
        "status": user.status.value, "company_id": user.company_id,
        "categories": [{"id": i, "name": names.get(i)} for i in ids],
        "needs_category_selection": len(ids) == 0,
    }


def _product_out(p: MarketplaceProduct, names: dict) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "price": float(p.price or 0), "qty": float(p.qty or 0),
        "category_id": p.category_id, "category_name": names.get(p.category_id),
        "barcode": p.barcode, "sku": p.sku, "images": p.images or [],
        "status": p.status.value, "reject_reason": p.reject_reason,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _agent_category_ids(db: Session, user: User) -> set:
    return {r[0] for r in db.query(MarketplaceAgentCategory.category_id).filter(
        MarketplaceAgentCategory.user_id == user.id).all()}


def _check_category(db: Session, user: User, category_id: int) -> None:
    if category_id not in _agent_category_ids(db, user):
        raise HTTPException(status_code=400, detail="Bu kategoriyada sotish uchun ruxsatingiz yo'q. Avval kategoriyani tanlang.")


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
    
    import random
    code = str(random.randint(10000, 99999))
    from app.models.user import SmsVerification
    from datetime import timedelta
    
    # Eskiz SMS orqali yuborish
    from app.services.eskiz_service import eskiz_service
    msg = f"Universal ERP tasdiqlash kodi: {code}"
    res = await eskiz_service.send_sms(phone, msg)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail="SMS yuborishda xatolik yuz berdi")
        
    sms = SmsVerification(
        phone=phone,
        code=code,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    db.add(sms)
    db.commit()
    return {"ok": True, "detail": "Tasdiqlash kodi yuborildi"}


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
    user = db.query(User).filter(User.phone.in_([phone, f"+{phone}"]), User.role == UserRole.marketplace_agent).first()
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
def get_payme_checkout_url(request: Request, db: Session = Depends(get_db), user: User = Depends(get_agent)):
    # get_agent allows UserStatus.pending
    if user.status == UserStatus.active:
        raise HTTPException(status_code=400, detail="Sizning hisobingiz allaqachon faollashtirilgan")
        
    from app.config import settings
    import base64
    if not settings.PAYME_MERCHANT_ID:
        raise HTTPException(status_code=500, detail="Payme merchant id topilmadi")
        
    amount_tiyin = 200000 * 100 # 200 000 UZS
    raw = f"m={settings.PAYME_MERCHANT_ID};ac.agent_phone={user.phone};a={amount_tiyin}"
    encoded = base64.b64encode(raw.encode()).decode()
    base_url = "https://checkout.test.paycom.uz" if settings.PAYME_IS_TEST else "https://checkout.paycom.uz"
    
    return {"checkout_url": f"{base_url}/{encoded}"}


@router.get("/me")
def agent_me(db: Session = Depends(get_db), user: User = Depends(get_agent)):
    return _agent_out(db, user)


# ── Kategoriyalar ──────────────────────────────────────────────────────────

@router.get("/categories")
def list_categories(user: User = Depends(get_agent)):
    return {"items": mp.fetch_categories()}


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


@router.post("/products", status_code=201)
def create_product(data: ProductIn, db: Session = Depends(get_db), user: User = Depends(get_active_agent)):
    _check_category(db, user, data.category_id)
    p = MarketplaceProduct(
        company_id=user.company_id, agent_id=user.id, name=data.name.strip(),
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
    return {
        "sales": float(income), "commission": float(commission), "refunds": float(refund),
        "paid_out": float(payout), "balance": float(income - commission - refund - payout),
    }


@router.get("/balance")
def my_balance(db: Session = Depends(get_db), user: User = Depends(get_active_agent)):
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
