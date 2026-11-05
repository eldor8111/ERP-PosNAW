"""E-code AI yordamchi API (/api/ai/assistant/*).

Chat javobi SSE oqimi: har bir hodisa `data: {json}` qatori (start, status, tool, delta, action, done, error);
ulanish uzilmasligi uchun `: ping` izohlari. Paket faol bo'lmasa 402, limit tugasa 429.
"""
import json
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.billing import FeaturePackage
from app.models.user import User, UserRole
from app.services import ai_assistant as svc
from app.services import ai_packages
from app.services.ai_assistant_tools import CHAT_ROLES

router = APIRouter(prefix="/ai/assistant", tags=["E-code AI"])


def _raise(e: svc.AssistantError):
    raise HTTPException(status_code=e.status, detail=e.message)


def chat_user(user: User = Depends(get_current_user)) -> User:
    if user.role not in CHAT_ROLES or not user.company_id:
        raise HTTPException(status_code=403, detail="AI yordamchi sizning lavozimingiz uchun ochilmagan")
    return user


def super_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Faqat super admin uchun")
    return user


@router.get("/status")
def assistant_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Paket holati va ishlatilish (menyu va ishlatilish qatori uchun). Har qanday xodim so'rashi mumkin."""
    st = ai_packages.status(db, user) if user.company_id else {"active": False}
    st["can_chat"] = bool(st.get("active")) and user.role in CHAT_ROLES
    st["can_buy"] = user.role in (UserRole.admin, UserRole.director)
    return st


@router.get("/conversations")
def conversations(db: Session = Depends(get_db), user: User = Depends(chat_user)):
    return svc.list_conversations(db, user)


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    try:
        conv = svc.get_conversation(db, user, conversation_id)
    except svc.AssistantError as e:
        _raise(e)
    return {"id": conv.id, "title": conv.title or "Yangi suhbat", "turns": conv.turns or 0,
            "messages": svc.conversation_view(db, conv)}


class RenameIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, data: RenameIn, db: Session = Depends(get_db),
                        user: User = Depends(chat_user)):
    try:
        conv = svc.get_conversation(db, user, conversation_id)
    except svc.AssistantError as e:
        _raise(e)
    conv.title = data.title.strip()[:200]
    db.commit()
    return {"ok": True, "title": conv.title}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    try:
        conv = svc.get_conversation(db, user, conversation_id)
    except svc.AssistantError as e:
        _raise(e)
    conv.is_deleted = True
    db.commit()
    return {"ok": True}


@router.post("/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(chat_user)):
    acc = ai_packages.check_quota(db, user)
    if not acc.allow_vision:
        raise HTTPException(status_code=403, detail="Paketingizda rasm yuborish yo'q")
    raw = await file.read(svc.IMAGE_MAX_BYTES + 1)
    try:
        return svc.upload_image(db, user, raw, file.filename or "rasm.jpg")
    except svc.AssistantError as e:
        _raise(e)
    except Exception:
        raise HTTPException(status_code=502, detail="Rasmni AI xizmatiga yuklab bo'lmadi. Qayta urinib ko'ring.")


class ChatIn(BaseModel):
    conversation_id: Optional[int] = None
    message: str = Field("", max_length=svc.MAX_MESSAGE_CHARS)
    file_ids: List[str] = []


def _sse(gen):
    for ev in gen:
        if ev.get("type") == "ping":
            yield ": ping\n\n"
        else:
            yield "data: " + json.dumps(ev, ensure_ascii=False, default=str) + "\n\n"


def prepare_turn(db: Session, user: User, conversation_id: Optional[int], message: str, file_ids: list):
    """Oqim boshlanishidan oldingi tekshiruvlar (HTTP xato kodi to'g'ri qaytsin). (conv, text, files)."""
    acc = ai_packages.check_quota(db, user)
    text = (message or "").strip()
    if not text and not file_ids:
        raise HTTPException(status_code=400, detail="Xabar bo'sh")
    if file_ids and not acc.allow_vision:
        raise HTTPException(status_code=403, detail="Paketingizda rasm yuborish yo'q")
    if not svc.is_configured():
        raise HTTPException(status_code=503, detail="AI yordamchi hali ulanmagan. Administrator bilan bog'laning.")
    try:
        files = svc.own_files(db, user, file_ids)
        if conversation_id:
            conv = svc.get_conversation(db, user, conversation_id)
        else:
            conv = svc.create_conversation(db, user, acc.allow_actions)
        svc.acquire(db, conv)
    except svc.AssistantError as e:
        _raise(e)
    if not text:
        text = "Rasmdagi hujjatni o'qib ber."
    return conv, text, files


@router.post("/chat")
def chat(data: ChatIn, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    conv, text, files = prepare_turn(db, user, data.conversation_id, data.message, data.file_ids)
    return StreamingResponse(
        _sse(svc.run_turn(conv.id, user.id, text, files)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/actions/{confirmation_id}/confirm")
def confirm(confirmation_id: str, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    try:
        return svc.confirm_action(db, user, confirmation_id)
    except svc.AssistantError as e:
        _raise(e)


@router.post("/actions/{confirmation_id}/cancel")
def cancel(confirmation_id: str, db: Session = Depends(get_db), user: User = Depends(chat_user)):
    try:
        return svc.cancel_action(db, user, confirmation_id)
    except svc.AssistantError as e:
        _raise(e)


# ─── Super admin: AI tariflari va ishlatilish hisoboti ──────────────────────

class AiPackageIn(BaseModel):
    code: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    price_per_month: float = Field(0, ge=0)
    is_active: bool = False
    sort_order: int = 90
    ai_monthly_limit: int = Field(0, ge=0)
    ai_daily_user_limit: int = Field(0, ge=0)
    ai_allow_actions: bool = True
    ai_allow_vision: bool = True


def _pkg_out(p: FeaturePackage) -> dict:
    return {"code": p.code, "name": p.name, "description": p.description,
            "price_per_month": float(p.price_per_month or 0), "is_active": bool(p.is_active),
            "sort_order": p.sort_order, "ai_monthly_limit": p.ai_monthly_limit or 0,
            "ai_daily_user_limit": p.ai_daily_user_limit or 0,
            "ai_allow_actions": p.ai_allow_actions is not False, "ai_allow_vision": p.ai_allow_vision is not False}


@router.get("/admin/packages")
def admin_packages(db: Session = Depends(get_db), _: User = Depends(super_admin)):
    rows = db.query(FeaturePackage).filter(FeaturePackage.code.like(f"{ai_packages.AI_PREFIX}%")).order_by(
        FeaturePackage.sort_order, FeaturePackage.id).all()
    return [_pkg_out(p) for p in rows]


def _apply(p: FeaturePackage, data: AiPackageIn):
    p.name = data.name.strip()
    p.description = (data.description or "").strip() or None
    p.price_per_month = data.price_per_month
    p.bhm_percent = None
    p.is_active = data.is_active
    p.sort_order = data.sort_order
    p.ai_monthly_limit = data.ai_monthly_limit
    p.ai_daily_user_limit = data.ai_daily_user_limit
    p.ai_allow_actions = data.ai_allow_actions
    p.ai_allow_vision = data.ai_allow_vision


@router.post("/admin/packages")
def admin_create_package(data: AiPackageIn, db: Session = Depends(get_db), _: User = Depends(super_admin)):
    """Yangi AI darajasi (masalan "ai_assistant_pro"). Kod "ai_assistant" bilan boshlanadi."""
    suffix = "".join(ch for ch in (data.code or "").lower() if ch.isalnum() or ch == "_")
    if suffix.startswith(ai_packages.AI_PREFIX):
        suffix = suffix[len(ai_packages.AI_PREFIX):].lstrip("_")
    code = ai_packages.AI_PREFIX + (f"_{suffix}" if suffix else "")
    if db.query(FeaturePackage.id).filter(FeaturePackage.code == code).first():
        raise HTTPException(status_code=409, detail=f"'{code}' kodli paket allaqachon bor")
    p = FeaturePackage(code=code)
    _apply(p, data)
    db.add(p)
    db.commit()
    return _pkg_out(p)


@router.put("/admin/packages/{code}")
def admin_update_package(code: str, data: AiPackageIn, db: Session = Depends(get_db), _: User = Depends(super_admin)):
    if not ai_packages.is_ai_code(code):
        raise HTTPException(status_code=400, detail="Bu AI paketi emas")
    p = db.query(FeaturePackage).filter(FeaturePackage.code == code).first()
    if not p:
        raise HTTPException(status_code=404, detail="Paket topilmadi")
    _apply(p, data)
    db.commit()
    return _pkg_out(p)


@router.get("/admin/usage")
def admin_usage(month: Optional[str] = Query(None, description="YYYY-MM"), db: Session = Depends(get_db),
                _: User = Depends(super_admin)):
    d = None
    if month:
        try:
            y, m = month.split("-")[:2]
            d = date(int(y), int(m), 1)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Oy formati: YYYY-MM")
    return ai_packages.usage_report(db, d)
