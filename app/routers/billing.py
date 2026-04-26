"""
Billing API — Tariflar, Balans, Obuna boshqaruvi.
Super Admin barcha korxonalarni boshqaradi.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from pydantic import BaseModel  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user, get_current_user_allow_expired  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.billing import Tariff, BalanceLog  # type: ignore
from app.models.platform_settings import PlatformSettings  # type: ignore

router = APIRouter(prefix="/billing", tags=["Billing"])

# Default sozlamalar (DB bo'sh bo'lsa ishlatiladi)
DEFAULT_SETTINGS = {
    "card_number": "0000 0000 0000 0000",
    "card_owner":  "Karta egasi",
    "tg_username": "username",
    "phone":       "+998 00 000 00 00",
    "phone_raw":   "+998000000000",
}


def _get_settings_dict(db: Session) -> dict:
    result = dict(DEFAULT_SETTINGS)
    try:
        rows = db.query(PlatformSettings).all()
        for r in rows:
            result[r.key] = r.value or result.get(r.key, "")
    except Exception:
        db.rollback()
    return result




# ─── Yordamchi ────────────────────────────────────────────────────────────────

def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Faqat Super Admin uchun")
    return user


def _tariff_out(t: Tariff) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "price_per_month": float(t.price_per_month or 0),
        "duration_days": t.duration_days,
        "max_users": t.max_users,
        "max_branches": t.max_branches,
        "is_active": t.is_active,
        "sort_order": t.sort_order,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _company_billing_out(c: Company) -> dict:
    now = datetime.now(timezone.utc)
    sub_ends = c.subscription_ends_at
    # timezone-aware qilish
    if sub_ends and sub_ends.tzinfo is None:
        sub_ends = sub_ends.replace(tzinfo=timezone.utc)

    is_active_sub = sub_ends is not None and sub_ends > now
    days_left = max(0, (sub_ends - now).days) if is_active_sub else 0

    return {
        "id": c.id,
        "name": c.name,
        "org_code": c.org_code,
        "is_active": c.is_active,
        "balance": float(c.balance or 0),
        "tariff_id": c.tariff_id,
        "tariff_name": c.tariff.name if c.tariff else None,
        "subscription_ends_at": sub_ends.isoformat() if sub_ends else None,
        "is_trial": bool(c.is_trial),
        "subscription_active": is_active_sub,
        "days_left": days_left,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ─── Platform Sozlamalari (public) ───────────────────────────────────────────

@router.get("/settings")
def get_payment_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user_allow_expired),
):
    """Karta raqami, Telegram, Telefon — barcha login qilganlar uchun"""
    return _get_settings_dict(db)


# ─── Tariflar ─────────────────────────────────────────────────────────────────

@router.get("/tariffs")
def list_tariffs(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user_allow_expired),
):
    """Barcha faol tariflar (hamma foydalanuvchilar ko'ra oladi)"""
    tariffs = db.query(Tariff).filter(Tariff.is_active == True).order_by(Tariff.sort_order).all()
    return [_tariff_out(t) for t in tariffs]


class TariffCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price_per_month: float = 0
    duration_days: int = 30
    max_users: int = 5
    max_branches: int = 1
    sort_order: int = 0


@router.post("/tariffs")
def create_tariff(
    data: TariffCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    t = Tariff(
        name=data.name,
        description=data.description,
        price_per_month=data.price_per_month,
        duration_days=data.duration_days,
        max_users=data.max_users,
        max_branches=data.max_branches,
        sort_order=data.sort_order,
        created_at=datetime.now(timezone.utc),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _tariff_out(t)


class TariffUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_per_month: Optional[float] = None
    duration_days: Optional[int] = None
    max_users: Optional[int] = None
    max_branches: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


@router.put("/tariffs/{tariff_id}")
def update_tariff(
    tariff_id: int,
    data: TariffUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    t = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarif topilmadi")
    for field, val in data.model_dump(exclude_none=True).items():
        setattr(t, field, val)
    db.commit()
    db.refresh(t)
    return _tariff_out(t)


@router.delete("/tariffs/{tariff_id}")
def delete_tariff(
    tariff_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    t = db.query(Tariff).filter(Tariff.id == tariff_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarif topilmadi")
    t.is_active = False
    db.commit()
    return {"ok": True}


# ─── O'z korxona billing ma'lumoti (barcha foydalanuvchilar) ─────────────────

@router.get("/my-company")
def get_my_company_billing(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_allow_expired),
):
    """Foydalanuvchi o'z korxonasining billing holatini ko'radi"""
    if not user.company_id:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    c = db.query(Company).filter(Company.id == user.company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    return _company_billing_out(c)


# ─── Korxonalar billing ma'lumotlari ─────────────────────────────────────────

@router.get("/companies")
def list_companies_billing(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Barcha korxonalar billing holati"""
    companies = db.query(Company).order_by(Company.id).all()
    return [_company_billing_out(c) for c in companies]


@router.get("/companies/{company_id}")
def get_company_billing(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    return _company_billing_out(c)


# ─── 7 Kunlik Sinov (Trial) ───────────────────────────────────────────────────

@router.post("/companies/{company_id}/activate-trial")
def activate_trial(
    company_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """7 kunlik sinov muddatini yoqish (bepul) — Super Admin uchun"""
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    now = datetime.now(timezone.utc)
    current_end = c.subscription_ends_at
    if current_end and current_end.tzinfo is None:
        current_end = current_end.replace(tzinfo=timezone.utc)

    base = current_end if (current_end and current_end > now) else now
    c.subscription_ends_at = base + timedelta(days=7)
    c.is_trial = True

    log = BalanceLog(
        company_id=c.id,
        amount=0,
        log_type="trial",
        note="7 kunlik sinov muddati berildi",
        created_by_id=admin.id,
        created_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(c)
    return {
        **_company_billing_out(c),
        "message": f"7 kunlik sinov {c.subscription_ends_at.strftime('%d.%m.%Y')} gacha berildi",
    }


@router.post("/activate-my-trial")
def activate_my_trial(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """O'z korxonasi uchun 7 kunlik bepul sinov faollashtirish — har bir korxona bir marta"""
    if not user.company_id:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    c = db.query(Company).filter(Company.id == user.company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    if c.is_trial:
        raise HTTPException(status_code=400, detail="Sinov muddati allaqachon ishlatilgan")

    # Sinov tarifini topamiz
    trial_tariff = db.query(Tariff).filter(Tariff.is_active == True, Tariff.price_per_month <= 0).first()

    now = datetime.now(timezone.utc)
    c.subscription_ends_at = now + timedelta(days=7)
    c.is_trial = True
    if trial_tariff:
        c.tariff_id = trial_tariff.id

    log = BalanceLog(
        company_id=c.id,
        amount=0,
        log_type="trial",
        note="7 kunlik bepul sinov faollashtirildi",
        created_by_id=user.id,
        created_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(c)
    return {
        **_company_billing_out(c),
        "message": f"7 kunlik sinov {c.subscription_ends_at.strftime('%d.%m.%Y')} gacha faollashtirildi!",
    }


# ─── Balansni to'ldirish ──────────────────────────────────────────────────────

class TopUpRequest(BaseModel):
    amount: float
    note: Optional[str] = None


@router.post("/companies/{company_id}/top-up")
def top_up_balance(
    company_id: int,
    data: TopUpRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """Korxona balansini to'ldirish (Super Admin qo'lda)"""
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Miqdor musbat bo'lishi kerak")

    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    now = datetime.now(timezone.utc)
    c.balance = float(c.balance or 0) + data.amount

    log = BalanceLog(
        company_id=c.id,
        amount=data.amount,
        log_type="top_up",
        note=data.note or f"Balans to'ldirildi: +{data.amount:,.0f} so'm",
        created_by_id=admin.id,
        created_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(c)
    return {
        **_company_billing_out(c),
        "message": f"Balans +{data.amount:,.0f} so'm qo'shildi",
    }


# ─── Obuna faollashtirish (balansdan hisobdan chiqarish) ─────────────────────

class SubscribeRequest(BaseModel):
    tariff_id: int
    months: int = 1   # necha oylik obuna


@router.post("/companies/{company_id}/subscribe")
def activate_subscription(
    company_id: int,
    data: SubscribeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """Balansdan hisobdan chiqarib obunani faollashtirish"""
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    tariff = db.query(Tariff).filter(Tariff.id == data.tariff_id, Tariff.is_active == True).first()
    if not tariff:
        raise HTTPException(status_code=404, detail="Tarif topilmadi")

    total_price = float(tariff.price_per_month) * data.months
    current_balance = float(c.balance or 0)

    if current_balance < total_price:
        raise HTTPException(
            status_code=400,
            detail=f"Balans yetarli emas. Kerak: {total_price:,.0f} s, Balans: {current_balance:,.0f} s"
        )

    # Balansdan chiqarish
    c.balance = current_balance - total_price
    c.tariff_id = tariff.id
    c.is_trial = False

    now = datetime.now(timezone.utc)
    current_end = c.subscription_ends_at
    if current_end and current_end.tzinfo is None:
        current_end = current_end.replace(tzinfo=timezone.utc)

    base = current_end if (current_end and current_end > now) else now
    extra_days = tariff.duration_days * data.months
    c.subscription_ends_at = base + timedelta(days=extra_days)

    log = BalanceLog(
        company_id=c.id,
        amount=-total_price,
        log_type="subscription",
        note=f"Tarif: {tariff.name} × {data.months} oy",
        created_by_id=admin.id,
        created_at=now,
    )
    db.add(log)
    db.commit()
    db.refresh(c)
    return {
        **_company_billing_out(c),
        "message": f"Obuna {c.subscription_ends_at.strftime('%d.%m.%Y')} gacha uzaytirildi",
        "charged": total_price,
    }


# ─── Balans tarixi ────────────────────────────────────────────────────────────

@router.get("/companies/{company_id}/logs")
def get_balance_logs(
    company_id: int,
    limit: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    logs = (
        db.query(BalanceLog)
        .filter(BalanceLog.company_id == company_id)
        .order_by(BalanceLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": lg.id,
            "amount": float(lg.amount),
            "log_type": lg.log_type,
            "note": lg.note,
            "created_by": lg.created_by.name if lg.created_by else None,
            "created_at": lg.created_at.isoformat() if lg.created_at else None,
        }
        for lg in logs
    ]
