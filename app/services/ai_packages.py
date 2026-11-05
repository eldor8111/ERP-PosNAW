"""E-code AI yordamchi paketlari: kirish huquqi, kvotalar va ishlatilish hisoboti.

Paketlar boshqa pullik paketlar bilan bir xil saqlanadi (feature_packages + company_packages).
AI darajalari — kodi "ai_assistant" bilan boshlanadigan paketlar ("ai_assistant", "ai_assistant_pro" ...).
Korxonada bir vaqtda faqat bitta AI darajasi faol bo'ladi.

So'rov = foydalanuvchining bitta chat xabari (vosita chaqiruvlari alohida sanalmaydi).
Kun va oy chegarasi — Toshkent vaqti.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ai_assistant import AiMessage
from app.models.billing import CompanyPackage, FeaturePackage
from app.utils.report_utils import LOCAL_TZ, local_day_start, local_today

AI_PREFIX = "ai_assistant"


def is_ai_code(code: Optional[str]) -> bool:
    return bool(code) and str(code).startswith(AI_PREFIX)


def _utc_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def day_bounds(d: Optional[date] = None):
    """Toshkent kuni -> (boshi, oxiri) UTC (naive) — ai_messages.created_at bilan solishtirish uchun."""
    d = d or local_today()
    return _utc_naive(local_day_start(d)), _utc_naive(local_day_start(d + timedelta(days=1)))


def month_bounds(d: Optional[date] = None):
    d = d or local_today()
    first = d.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return _utc_naive(local_day_start(first)), _utc_naive(local_day_start(nxt))


@dataclass
class Access:
    active: bool = False
    code: Optional[str] = None
    name: Optional[str] = None
    ends_at: Optional[datetime] = None
    monthly_limit: int = 0          # 0 = cheklanmagan
    daily_user_limit: int = 0
    allow_actions: bool = True
    allow_vision: bool = True
    is_trial: bool = False


def access_for(db: Session, company_id: Optional[int]) -> Access:
    """Korxonaning hozir faol AI paketi (muddati tugamagan). Bir nechta bo'lsa — eng kech tugaydigani."""
    if not company_id:
        return Access()
    now = datetime.now(timezone.utc)
    best = None
    for cp in db.query(CompanyPackage).filter(
        CompanyPackage.company_id == company_id,
        CompanyPackage.package_code.like(f"{AI_PREFIX}%"),
        CompanyPackage.is_active == True,  # noqa: E712
    ).all():
        ends = _aware(cp.ends_at)
        if ends is None or ends <= now:
            continue
        if best is None or ends > _aware(best.ends_at):
            best = cp
    if best is None:
        return Access()
    pkg = db.query(FeaturePackage).filter(FeaturePackage.code == best.package_code).first()
    return Access(
        active=True,
        code=best.package_code,
        name=pkg.name if pkg else best.package_code,
        ends_at=_aware(best.ends_at),
        monthly_limit=int((pkg.ai_monthly_limit if pkg else 0) or 0),
        daily_user_limit=int((pkg.ai_daily_user_limit if pkg else 0) or 0),
        allow_actions=(pkg.ai_allow_actions is not False) if pkg else True,
        allow_vision=(pkg.ai_allow_vision is not False) if pkg else True,
        is_trial=bool(best.is_trial),
    )


def _count_prompts(db: Session, company_id: int, start: datetime, end: datetime, user_id: Optional[int] = None) -> int:
    q = db.query(func.count(AiMessage.id)).filter(
        AiMessage.company_id == company_id,
        AiMessage.role == "user",
        AiMessage.kind == "prompt",
        AiMessage.created_at >= start,
        AiMessage.created_at < end,
    )
    if user_id is not None:
        q = q.filter(AiMessage.user_id == user_id)
    return int(q.scalar() or 0)


def usage(db: Session, company_id: int, user_id: Optional[int] = None) -> dict:
    m0, m1 = month_bounds()
    d0, d1 = day_bounds()
    out = {
        "month_used": _count_prompts(db, company_id, m0, m1),
        "day_used_company": _count_prompts(db, company_id, d0, d1),
    }
    if user_id is not None:
        out["day_used_user"] = _count_prompts(db, company_id, d0, d1, user_id)
    return out


def check_quota(db: Session, user) -> Access:
    """Chat so'rovidan oldin: paket faol emas -> 402, limit tugagan -> 429."""
    acc = access_for(db, user.company_id)
    if not acc.active:
        raise HTTPException(status_code=402, detail="AI yordamchi paketi faol emas. Paketni Tariflar bo'limidan sotib oling.")
    u = usage(db, user.company_id, user.id)
    if acc.monthly_limit and u["month_used"] >= acc.monthly_limit:
        raise HTTPException(status_code=429, detail=f"Bu oy uchun AI so'rovlar limiti tugadi ({acc.monthly_limit} ta).")
    if acc.daily_user_limit and u["day_used_user"] >= acc.daily_user_limit:
        raise HTTPException(status_code=429, detail=f"Bugungi shaxsiy limitingiz tugadi ({acc.daily_user_limit} ta). Ertaga davom eting.")
    company_cap = int(getattr(settings, "AI_DAILY_LIMIT_COMPANY", 0) or 0)
    if company_cap and u["day_used_company"] >= company_cap:
        raise HTTPException(status_code=429, detail="Korxonaning bugungi AI so'rovlar chegarasi tugadi. Ertaga davom eting.")
    return acc


def status(db: Session, user) -> dict:
    acc = access_for(db, user.company_id)
    u = usage(db, user.company_id, user.id) if user.company_id else {"month_used": 0, "day_used_user": 0}
    return {
        "active": acc.active,
        "package_code": acc.code,
        "package_name": acc.name,
        "ends_at": acc.ends_at.isoformat() if acc.ends_at else None,
        "is_trial": acc.is_trial,
        "monthly_limit": acc.monthly_limit,
        "month_used": u.get("month_used", 0),
        "daily_user_limit": acc.daily_user_limit,
        "day_used": u.get("day_used_user", 0),
        "allow_actions": acc.allow_actions,
        "allow_vision": acc.allow_vision,
        "configured": bool(settings.ANTHROPIC_API_KEY),
    }


def check_switch(db: Session, company_id: int, package_code: str) -> None:
    """Boshqa AI darajasi faol bo'lsa yangi darajani sotib olish/uzaytirish rad etiladi (bir vaqtda bitta daraja)."""
    if not is_ai_code(package_code):
        return
    acc = access_for(db, company_id)
    if acc.active and acc.code != package_code:
        raise HTTPException(
            status_code=409,
            detail=f"Sizda faol '{acc.name}' AI paketi bor ({acc.ends_at.astimezone(LOCAL_TZ):%d.%m.%Y} gacha). "
                   "Boshqa darajaga o'tish uchun u tugashini kuting yoki super adminga murojaat qiling.",
        )


def deactivate_other_tiers(db: Session, company_id: int, keep_code: str) -> None:
    """Super admin boshqa darajani bergan payt: korxonaning qolgan AI darajalari o'chiriladi."""
    for cp in db.query(CompanyPackage).filter(
        CompanyPackage.company_id == company_id,
        CompanyPackage.package_code.like(f"{AI_PREFIX}%"),
        CompanyPackage.package_code != keep_code,
        CompanyPackage.is_active == True,  # noqa: E712
    ).all():
        cp.is_active = False


def usage_report(db: Session, month: Optional[date] = None) -> dict:
    """Super admin: tanlangan oy bo'yicha korxonalar kesimida so'rovlar, tokenlar va xarajat (USD)."""
    from app.models.company import Company
    m0, m1 = month_bounds(month)
    rows = db.query(
        AiMessage.company_id,
        func.count(AiMessage.id).filter(AiMessage.kind == "prompt").label("prompts"),
        func.coalesce(func.sum(AiMessage.input_tokens), 0),
        func.coalesce(func.sum(AiMessage.output_tokens), 0),
        func.coalesce(func.sum(AiMessage.cache_read_tokens), 0),
        func.coalesce(func.sum(AiMessage.cache_write_tokens), 0),
        func.coalesce(func.sum(AiMessage.cost_usd), 0),
    ).filter(AiMessage.created_at >= m0, AiMessage.created_at < m1).group_by(AiMessage.company_id).all()
    names = {c.id: c.name for c in db.query(Company.id, Company.name).filter(
        Company.id.in_([r[0] for r in rows] or [0])).all()}
    items = []
    total_cost = Decimal("0")
    for cid, prompts, it, ot, cr, cw, cost in rows:
        acc = access_for(db, cid)
        cost = Decimal(str(cost or 0))
        total_cost += cost
        items.append({
            "company_id": cid, "company_name": names.get(cid, f"#{cid}"),
            "package": acc.name if acc.active else None,
            "monthly_limit": acc.monthly_limit if acc.active else None,
            "prompts": int(prompts or 0),
            "input_tokens": int(it), "output_tokens": int(ot),
            "cache_read_tokens": int(cr), "cache_write_tokens": int(cw),
            "cost_usd": float(round(cost, 4)),
        })
    items.sort(key=lambda r: r["cost_usd"], reverse=True)
    month_d = (month or local_today()).replace(day=1)
    return {"month": month_d.isoformat(), "items": items, "total_cost_usd": float(round(total_cost, 4)),
            "total_prompts": sum(r["prompts"] for r in items)}
