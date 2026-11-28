"""Ofitsiant planshetlari (R6.1).

Menejer planshetni bir marta ulaydi (`POST /restaurant/terminals` — maxfiy token bir marta ko'rsatiladi, bazada
faqat SHA-256 xeshi). Planshet `/waiter?t=<token>` havolasi bilan ochiladi va tokenni saqlaydi. Keyin xodimlar shu
planshetda ismini tanlab, 4-6 raqamli PIN bilan almashib kiradi.

PIN bilan berilgan sessiya: oddiy access token, `term` claim bilan (planshet bekor qilinsa darhol yaroqsiz —
app/core/dependencies.py), 12 soat, refresh tokensiz. Xato PIN: 5 urinishdan keyin 10 daqiqa blok (audit bilan).
Ruxsatlar xodimning o'z roli bo'yicha; kirish faqat planshet filialiga ruxsati bor, cheklar yoki oshxona bilan
ishlaydigan, PIN o'rnatgan faol xodimlarga.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.branch_context import BranchContext, build_branch_context, get_branch_context
from app.core.dependencies import require_roles
from app.core.features import require_restaurant
from app.core.limiter import limiter
from app.database import get_db
from app.models.branch import Branch
from app.models.company import Company
from app.models.restaurant import RestaurantTerminal
from app.models.user import MOBILE_ONLY_ROLES, User, UserRole, UserStatus
from app.services import restaurant_orders as svc

SESSION_HOURS = 12
MANAGE_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager)

router = APIRouter(prefix="/restaurant/terminals", tags=["Ofitsiant planshetlari"],
                   dependencies=[Depends(require_restaurant)])
public = APIRouter(prefix="/restaurant/terminal", tags=["Ofitsiant planshetlari"])


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now():
    return datetime.now(timezone.utc)


def _iso(d):
    if d is None:
        return None
    return (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d).isoformat()


def _out(db: Session, t: RestaurantTerminal) -> dict:
    b = db.get(Branch, t.branch_id)
    return {"id": t.id, "name": t.name, "branch_id": t.branch_id, "branch_name": b.name if b else None,
            "created_at": _iso(t.created_at), "last_used_at": _iso(t.last_used_at), "active": t.revoked_at is None}


# ───────────────────────── boshqaruv (menejer) ─────────────────────────

class TerminalIn(BaseModel):
    branch_id: Optional[int] = None
    name: str


@router.get("")
def list_terminals(db: Session = Depends(get_db), user: User = Depends(require_roles(*MANAGE_ROLES)),
                   ctx: BranchContext = Depends(get_branch_context)):
    q = db.query(RestaurantTerminal).filter(RestaurantTerminal.company_id == user.company_id,
                                            RestaurantTerminal.revoked_at.is_(None))
    if ctx.allowed_branch_ids is not None:
        q = q.filter(RestaurantTerminal.branch_id.in_(ctx.allowed_branch_ids or {0}))
    return [_out(db, t) for t in q.order_by(RestaurantTerminal.id)]


@router.post("", status_code=201)
def create_terminal(payload: TerminalIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(*MANAGE_ROLES)), ctx: BranchContext = Depends(get_branch_context)):
    bid = svc.branch_for(db, user, ctx, payload.branch_id)
    name = (payload.name or "").strip()[:100]
    if not name:
        raise HTTPException(status_code=400, detail="Planshet nomini kiriting")
    if db.query(RestaurantTerminal).filter(RestaurantTerminal.company_id == user.company_id,
                                           RestaurantTerminal.revoked_at.is_(None)).count() >= 50:
        raise HTTPException(status_code=400, detail="Faol planshetlar soni 50 tadan oshmasin")
    from app.services.restaurant_tariff import check_waiter_devices
    check_waiter_devices(db, user.company_id)                                  # R9.1: tarif limiti
    token = secrets.token_urlsafe(32)
    t = RestaurantTerminal(company_id=user.company_id, branch_id=bid, name=name, token_hash=_hash(token),
                           created_by=user.id, created_at=_now())
    db.add(t)
    db.flush()
    log_action(db=db, action="REST_TERMINAL_CREATE", entity_type="restaurant_terminal", entity_id=t.id,
               user_id=user.id, new_values={"name": name, "branch_id": bid})
    db.commit()
    return {**_out(db, t), "token": token}


@router.delete("/{terminal_id}")
def revoke_terminal(terminal_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(*MANAGE_ROLES)),
                    ctx: BranchContext = Depends(get_branch_context)):
    t = db.query(RestaurantTerminal).filter(RestaurantTerminal.id == terminal_id,
                                            RestaurantTerminal.company_id == user.company_id).first()
    if t is None or (ctx.allowed_branch_ids is not None and t.branch_id not in ctx.allowed_branch_ids):
        raise HTTPException(status_code=404, detail="Planshet topilmadi")
    if t.revoked_at is None:
        t.revoked_at = _now()
        log_action(db=db, action="REST_TERMINAL_REVOKE", entity_type="restaurant_terminal", entity_id=t.id,
                   user_id=user.id, old_values={"name": t.name})
        db.commit()
    return {"ok": True}


# ───────────────────────── planshet tomoni ─────────────────────────

def _terminal(db: Session, token: Optional[str]) -> RestaurantTerminal:
    if not token or len(token) > 200:
        raise HTTPException(status_code=401, detail="Planshet ulanmagan")
    t = db.query(RestaurantTerminal).filter(RestaurantTerminal.token_hash == _hash(token),
                                            RestaurantTerminal.revoked_at.is_(None)).first()
    if t is None:
        raise HTTPException(status_code=401, detail="Planshet ulanmagan yoki bekor qilingan")
    c = db.get(Company, t.company_id)
    from app.services.restaurant import is_restaurant
    if c is None or c.is_active is False or not is_restaurant(db, t.company_id):
        raise HTTPException(status_code=403, detail="Korxona faol emas")
    return t


def _membership(db: Session, user: User, company_id: int):
    """(rol, huquqlar) shu korxonada; a'zolik yo'q bo'lsa None."""
    from app.models.user_company import UserCompany
    uc = db.query(UserCompany).filter(UserCompany.user_id == user.id, UserCompany.company_id == company_id).first()
    if uc is not None:
        return (uc.role, uc.permissions) if uc.is_active else None
    if user.company_id == company_id:
        return user.role, user.permissions
    return None


def _eligible(db: Session, t: RestaurantTerminal, user: User, settings: dict):
    """Xodim shu planshetda ishlay oladimi: (rol, huquqlar) yoki None."""
    if user.status != UserStatus.active or not user.pin_hash or user.role in MOBILE_ONLY_ROLES:
        return None
    m = _membership(db, user, t.company_id)
    if m is None:
        return None
    role, perms = m
    try:
        role = role if isinstance(role, UserRole) else UserRole(role)
    except (ValueError, TypeError):
        return None
    if role == UserRole.super_admin or role in MOBILE_ONLY_ROLES:
        return None
    proxy = SimpleNamespace(id=user.id, company_id=t.company_id, branch_id=user.branch_id, role=role,
                            permissions=perms if perms is not None else user.permissions,
                            custom_role=user.custom_role)
    p = svc.rest_perms(proxy, settings)
    if not (p.get("orders") or p.get("kitchen")):
        return None
    try:
        build_branch_context(db, proxy, t.branch_id)
    except HTTPException:
        return None
    return role, perms


def _candidates(db: Session, company_id: int):
    from app.models.user_company import UserCompany
    ids = {uid for (uid,) in db.query(UserCompany.user_id).filter(UserCompany.company_id == company_id,
                                                                 UserCompany.is_active == True)}  # noqa: E712
    q = db.query(User).filter(User.status == UserStatus.active, User.pin_hash.isnot(None))
    return [u for u in q.filter((User.company_id == company_id) | (User.id.in_(ids or {0}))).order_by(User.name)]


@public.get("/staff")
@limiter.limit("60/minute")
def terminal_staff(request: Request, x_terminal_token: Optional[str] = Header(None), db: Session = Depends(get_db)):
    t = _terminal(db, x_terminal_token)
    settings = svc.settings_for(db, t.company_id)
    staff = [{"id": u.id, "name": u.name} for u in _candidates(db, t.company_id) if _eligible(db, t, u, settings)]
    c = db.get(Company, t.company_id)
    b = db.get(Branch, t.branch_id)
    return {"terminal": t.name, "company": c.name if c else None, "branch_id": t.branch_id,
            "branch": b.name if b else None, "staff": staff}


def _db_pin_fails(db: Session, user_id: int) -> int:
    """Oxirgi blok oralig'idagi xato PIN urinishlari audit jurnalidan: xotiradagi hisob har bir worker'da alohida,
    bu esa hamma worker'lar uchun umumiy. Muvaffaqiyatli kirishdan keyingi urinishlargina sanaladi."""
    from app.models.audit_log import AuditLog
    edge = (_now() - timedelta(minutes=svc.PIN_LOCK_MINUTES)).replace(tzinfo=None)
    last_ok = (db.query(AuditLog.created_at).filter(AuditLog.action == "REST_TERMINAL_LOGIN",
                                                    AuditLog.entity_id == user_id, AuditLog.created_at >= edge)
               .order_by(AuditLog.created_at.desc()).first())
    since = max(edge, last_ok[0].replace(tzinfo=None)) if last_ok and last_ok[0] else edge
    return db.query(AuditLog.id).filter(AuditLog.action == "REST_PIN_FAIL", AuditLog.entity_id == user_id,
                                        AuditLog.created_at > since).count()


class PinLoginIn(BaseModel):
    user_id: int
    pin: str


@public.post("/login")
@limiter.limit("30/minute")
def terminal_login(request: Request, payload: PinLoginIn, x_terminal_token: Optional[str] = Header(None),
                   db: Session = Depends(get_db)):
    from app.core.security import create_access_token, verify_password
    from app.routers.auth import _user_out_in_company
    t = _terminal(db, x_terminal_token)
    settings = svc.settings_for(db, t.company_id)
    user = db.query(User).filter(User.id == payload.user_id).first()
    m = _eligible(db, t, user, settings) if user is not None else None
    if m is None:
        raise HTTPException(status_code=403, detail="Bu xodim shu planshetda ishlay olmaydi")
    if svc._pin_fails(user.id) >= svc.PIN_MAX_FAILS or _db_pin_fails(db, user.id) >= svc.PIN_MAX_FAILS:
        raise HTTPException(status_code=429, detail=f"PIN {svc.PIN_LOCK_MINUTES} daqiqaga bloklangan")
    if not verify_password((payload.pin or "").strip(), user.pin_hash):
        svc._pin_fail(user.id)
        svc._log_pin_fail(user, user.id)
        raise HTTPException(status_code=401, detail="PIN noto'g'ri")
    with svc._PIN_LOCK:
        svc._PIN_FAILS.pop(user.id, None)
    role, perms = m
    t.last_used_at = _now()
    token = create_access_token({"sub": str(user.id), "role": role.value, "company_id": t.company_id, "term": t.id},
                                expires_delta=timedelta(hours=SESSION_HOURS))
    user_out = _user_out_in_company(db, user, t.company_id, role, perms)
    log_action(db=db, action="REST_TERMINAL_LOGIN", entity_type="user", entity_id=user.id, user_id=user.id,
               ip_address=request.client.host if request.client else None, new_values={"terminal_id": t.id})
    db.commit()
    return {"access_token": token, "user": user_out.model_dump(mode="json"), "branch_id": t.branch_id,
            "expires_in": SESSION_HOURS * 3600}
