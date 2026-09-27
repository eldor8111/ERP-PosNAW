"""
Mobil ilova (E-code Mobile): kirish, qurilma sessiyasi va profil.

Tokenlarda "dev" (mobile_devices.id) bo'ladi. get_current_user har so'rovda
qurilma bekor qilinmaganini tekshiradi, kuryer/agent tokeni esa faqat
/api/mobile/* yo'llarida ishlaydi (app/core/dependencies.py).
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.features import company_has_feature
from app.core.limiter import limiter
from app.core.security import create_access_token, decode_token, verify_password
from app.database import get_db
from app.models.company import Company
from app.models.mobile_device import MobileDevice
from app.models.user import MOBILE_ONLY_ROLES, User, UserRole, UserStatus
from app.services.mobile_service import ensure_courier_profile, ensure_personal_wallet

router = APIRouter(prefix="/mobile", tags=["mobile"])

MOBILE_REFRESH_DAYS = 30
MIN_APP_VERSION = "1.0.0"
LATEST_APP_VERSION = "1.0.0"


class MobileLoginIn(BaseModel):
    phone: str = Field(..., min_length=5, max_length=20)
    password: str = Field(..., min_length=1, max_length=128)
    device_id: str = Field(..., min_length=8, max_length=100)
    platform: Optional[str] = Field(None, max_length=20)
    model: Optional[str] = Field(None, max_length=100)
    app_version: Optional[str] = Field(None, max_length=20)


class MobileRefreshIn(BaseModel):
    refresh_token: str


def _issue_tokens(user: User, device: MobileDevice) -> dict:
    claims = {"sub": str(user.id), "role": user.role.value, "company_id": user.company_id, "dev": device.id}
    refresh = create_access_token(
        {"sub": str(user.id), "dev": device.id, "type": "refresh"},
        expires_delta=timedelta(days=MOBILE_REFRESH_DAYS),
    )
    return {"access_token": create_access_token(claims), "refresh_token": refresh, "token_type": "bearer"}


def _profile(db: Session, user: User) -> dict:
    company = db.query(Company).filter(Company.id == user.company_id).first()
    wallet = ensure_personal_wallet(db, user)
    courier = ensure_courier_profile(db, user)
    return {
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "role": user.role.value,
        "company_id": user.company_id,
        "company_name": company.name if company else None,
        "courier_id": courier.id if courier else None,
        "wallet": {"id": wallet.id, "name": wallet.name, "balance": float(wallet.balance or 0)},
        "shift": _shift_out(_open_shift(db, user)),
        "features": {
            "distribution": company_has_feature(db, user.company_id, "distribution"),
            "manufacturing": company_has_feature(db, user.company_id, "manufacturing"),
        },
    }


@router.post("/auth/login")
@limiter.limit("10/minute")
def mobile_login(request: Request, data: MobileLoginIn, db: Session = Depends(get_db)):
    from app.routers.auth import get_active_user_by_phone
    user, _ = get_active_user_by_phone(db, data.phone)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Telefon yoki parol noto'g'ri")
    if user.role not in MOBILE_ONLY_ROLES:
        raise HTTPException(status_code=403, detail="Bu ilova kuryer va savdo agentlari uchun. Rahbarlar veb-paneldan foydalanadi.")
    if not user.company_id:
        raise HTTPException(status_code=403, detail="Xodim kompaniyaga biriktirilmagan")

    now = datetime.now(timezone.utc)
    device = db.query(MobileDevice).filter(
        MobileDevice.user_id == user.id, MobileDevice.device_id == data.device_id,
    ).first()
    if not device:
        device = MobileDevice(user_id=user.id, device_id=data.device_id, company_id=user.company_id)
        db.add(device)
    device.company_id = user.company_id
    device.platform = data.platform
    device.model = data.model
    device.app_version = data.app_version
    device.last_seen_at = now
    device.revoked_at = None  # qayta parol bilan kirish — qurilmani qayta faollashtiradi
    db.flush()

    from app.core.audit import log_action
    log_action(db=db, action="MOBILE_LOGIN", entity_type="user", entity_id=user.id, user_id=user.id,
               ip_address=request.client.host if request.client else None,
               new_values={"device": data.device_id[:20], "platform": data.platform})
    out = {**_issue_tokens(user, device), "user": _profile(db, user)}
    db.commit()
    return out


@router.post("/auth/refresh")
@limiter.limit("30/minute")
def mobile_refresh(request: Request, data: MobileRefreshIn, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh" or payload.get("dev") is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessiya tugagan, qaytadan kiring")
    user = db.query(User).filter(User.id == int(payload["sub"]), User.status == UserStatus.active).first()
    device = db.query(MobileDevice).filter(
        MobileDevice.id == int(payload["dev"]), MobileDevice.user_id == int(payload["sub"]),
    ).first()
    if not user or not device or device.revoked_at is not None or user.role not in MOBILE_ONLY_ROLES:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessiya tugagan, qaytadan kiring")
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return _issue_tokens(user, device)


def _current_device(db: Session, request: Request, user: User) -> MobileDevice:
    auth = request.headers.get("authorization", "")
    payload = decode_token(auth.split(" ", 1)[1]) if " " in auth else None
    dev = payload.get("dev") if payload else None
    device = db.query(MobileDevice).filter(MobileDevice.id == dev, MobileDevice.user_id == user.id).first() if dev else None
    if not device:
        raise HTTPException(status_code=401, detail="Qurilma aniqlanmadi")
    return device


@router.post("/auth/logout")
def mobile_logout(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    device = _current_device(db, request, current_user)
    device.revoked_at = datetime.now(timezone.utc)
    device.fcm_token = None
    db.commit()
    return {"ok": True}


@router.get("/me")
def mobile_me(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    out = _profile(db, current_user)
    db.commit()  # birinchi kirishda yaratilgan kassa/kuryer profili saqlansin
    return out


class PushTokenIn(BaseModel):
    fcm_token: Optional[str] = Field(None, max_length=300)


@router.put("/device/push-token")
def set_push_token(data: PushTokenIn, request: Request, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    device = _current_device(db, request, current_user)
    device.fcm_token = data.fcm_token
    device.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ── Ish smenasi ─────────────────────────────────────────────────────────────

class GeoIn(BaseModel):
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)


def _open_shift(db: Session, user: User):
    from app.models.field_shift import FieldShift
    return db.query(FieldShift).filter(FieldShift.user_id == user.id, FieldShift.ended_at.is_(None)).first()


def _shift_out(s) -> Optional[dict]:
    if not s:
        return None
    return {"id": s.id, "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None}


@router.get("/shift")
def get_shift(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return {"shift": _shift_out(_open_shift(db, current_user))}


@router.post("/shift/start")
def start_shift(data: GeoIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.field_shift import FieldShift
    s = _open_shift(db, current_user)
    if not s:  # idempotent — ochiq smena bo'lsa o'shani qaytaramiz
        s = FieldShift(user_id=current_user.id, company_id=current_user.company_id,
                       start_lat=data.lat, start_lng=data.lng)
        db.add(s)
        db.commit()
        db.refresh(s)
    return {"shift": _shift_out(s)}


@router.post("/shift/end")
def end_shift(data: GeoIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    s = _open_shift(db, current_user)
    if s:
        s.ended_at = datetime.now(timezone.utc)
        s.end_lat, s.end_lng = data.lat, data.lng
        db.commit()
    return {"shift": None}


# ── GPS nuqtalari (fon kuzatuvi) ────────────────────────────────────────────

class LocPoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    accuracy: Optional[float] = Field(None, ge=0)
    speed: Optional[float] = None
    t: datetime


class LocBatchIn(BaseModel):
    points: List[LocPoint] = Field(..., max_length=500)
    battery: Optional[int] = Field(None, ge=0, le=100)


@router.post("/locations")
def push_locations(data: LocBatchIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Faqat ochiq smena davomida qabul qilinadi — smenadan tashqari nuqtalar
    saqlanmaydi (xodim shaxsiy vaqtida kuzatilmaydi)."""
    from app.models.employee_location import EmployeeLocation
    shift = _open_shift(db, current_user)
    if not shift:
        return {"saved": 0, "shift": False}
    # Baza sessiyasi Asia/Tashkent — undan kelgan naive vaqt mahalliy vaqtdir (UTC emas)
    from app.utils.report_utils import LOCAL_TZ
    as_aware = lambda dt: dt if dt is None or dt.tzinfo else dt.replace(tzinfo=LOCAL_TZ)
    started = as_aware(shift.started_at)
    now = datetime.now(timezone.utc)
    last = as_aware(db.query(func.max(EmployeeLocation.recorded_at)).filter(EmployeeLocation.user_id == current_user.id).scalar())
    saved = 0
    for p in sorted(data.points, key=lambda x: x.t):
        t = p.t if p.t.tzinfo else p.t.replace(tzinfo=timezone.utc)
        if t < started - timedelta(minutes=1) or t > now + timedelta(minutes=5):
            continue
        if last is not None and t <= last:
            continue  # qayta yuborilgan paket — takror yozilmaydi
        db.add(EmployeeLocation(
            user_id=current_user.id, company_id=current_user.company_id,
            lat=round(p.lat, 7), lng=round(p.lng, 7),
            accuracy=int(p.accuracy) if p.accuracy is not None else None,
            speed=p.speed, battery=data.battery, recorded_at=t,
        ))
        last = t
        saved += 1
    db.commit()
    return {"saved": saved, "shift": True}


@router.get("/version")
def app_version():
    """Majburiy yangilash tekshiruvi (autentifikatsiyasiz)."""
    return {"min_version": MIN_APP_VERSION, "latest_version": LATEST_APP_VERSION}
