import os
import asyncio
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status  # type: ignore
from pydantic import BaseModel  # type: ignore
from sqlalchemy.orm import Session  # type: ignore

from app.core.audit import log_action  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.core.security import (  # type: ignore
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db  # type: ignore
from app.models.agent import Agent  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.currency import Currency  # type: ignore
from app.models.user import User, UserRole, UserStatus  # type: ignore
from app.schemas.user import LoginRequest, RefreshRequest, TokenResponse, UserOut  # type: ignore
from app.core.limiter import limiter  # type: ignore

router = APIRouter(prefix="/auth", tags=["Auth"])

# ─── OTP in-memory store ────────────────────────────────────────────────────
# {phone: {"otp": "123456", "expires": datetime, "purpose": str}}
_otp_store: dict = {}
# {verified_token: {"phone": str, "expires": datetime}}
_verified_tokens: dict = {}
# Bot orqali ulangan: {normalized_phone: chat_id}
_phone_to_chat_id: dict = {}
# Polling offset
_polling_offset: list = [0]  # list ishlatiladi mutable bo'lishi uchun


from app.config import settings

def _get_otp_bot_token() -> str:
    return settings.OTP_BOT_TOKEN


async def _send_telegram_otp(chat_id: str, otp: str, user_name: str = "") -> bool:
    """OTP kodni Telegram orqali yuboradi. True qaytaradi agar muvaffaqiyatli."""
    bot_token = _get_otp_bot_token()
    if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    greeting = f"Salom, <b>{user_name}</b>!\n\n" if user_name else ""
    text = (
        f"🔐 <b>ERP-POS tasdiqlash kodi</b>\n\n"
        f"{greeting}"
        f"Sizning bir martalik kod:\n\n"
        f"<code>{otp}</code>\n\n"
        f"⏱ Kod <b>5 daqiqa</b> davomida amal qiladi.\n"
        f"🚫 Kodni hech kimga bermang!"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            })
            return resp.status_code == 200
    except Exception as e:
        print(f"OTP Telegram xato: {e}")
        return False


def _generate_otp() -> str:
    return str(random.randint(100000, 999999))


def _get_bot_username(token: str) -> str:
    """Bot username ni sinxron ravishda oladi."""
    try:
        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=3.0)
        if resp.status_code == 200:
            return resp.json().get("result", {}).get("username", "your_bot")
    except Exception:
        pass
    return "your_bot"


async def _process_bot_update(update: dict, bot_token: str):
    """Telegram bot update ni qayta ishlaydi — /start va contact."""
    message = update.get("message", {})
    if not message:
        return

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()

    # Kontakt yuborilganda — phone→chat_id bog'laymiz
    if "contact" in message:
        contact = message["contact"]
        phone_raw = contact.get("phone_number", "")
        # Faqat oxirgi 9 raqam (O'zbekiston formati)
        phone_digits = "".join(filter(str.isdigit, phone_raw))
        # Har xil formatda saqlash
        possible_phones = [
            phone_digits,
            phone_digits[-9:] if len(phone_digits) >= 9 else phone_digits,
            "998" + phone_digits[-9:] if len(phone_digits) >= 9 else "",
        ]
        for p in possible_phones:
            if p:
                _phone_to_chat_id[p] = chat_id
        print(f"[OTP Bot] Ulandi: {phone_digits} → chat_id {chat_id}")

        # DB ga ham saqlash — server restart bo'lsa ham saqlansin
        try:
            from app.database import SessionLocal
            db = SessionLocal()
            try:
                for p in possible_phones:
                    if not p:
                        continue
                    db_user = db.query(User).filter(User.phone == p, User.status == UserStatus.active).first()
                    if db_user:
                        db_user.tg_chat_id = chat_id
                        db.commit()
                        print(f"[OTP Bot] DB ga saqlandi: {p} → chat_id {chat_id}")
                        break
            finally:
                db.close()
        except Exception as e:
            print(f"[OTP Bot] DB saqlashda xato: {e}")
        # Tasdiqlash xabari
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "chat_id": chat_id,
                    "text": (
                        "✅ <b>Muvaffaqiyat!</b>\n\n"
                        "Sizning raqamingiz tizimga ulandi. "
                        "Endi ro'yxatdan o'tish yoki parolni tiklashda "
                        "OTP kodi shu botga yuboriladi! 🔐"
                    ),
                    "parse_mode": "HTML",
                    "reply_markup": {"remove_keyboard": True}
                })
        except Exception as e:
            print(f"[OTP Bot] Xato: {e}")
        return

    # /start komandasiga javob
    if text.startswith("/start"):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        keyboard = {
            "keyboard": [[{"text": "📞 Telefon raqamimni ulash", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={
                    "chat_id": chat_id,
                    "text": (
                        "👋 <b>ERP-POS OTP Bot</b>\n\n"
                        "Salom! Bu bot ro'yxatdan o'tish va "
                        "parolni tiklash uchun tasdiqlash kodlarini yuboradi.\n\n"
                        "📱 Boshlash uchun <b>quyidagi tugmani bosing</b> "
                        "va telefon raqamingizni ulang:"
                    ),
                    "parse_mode": "HTML",
                    "reply_markup": keyboard
                })
        except Exception as e:
            print(f"[OTP Bot] /start xato: {e}")


async def run_otp_bot_polling():
    """OTP Bot uchun long-polling (local development uchun)."""
    try:
        bot_token = _get_otp_bot_token()
        if not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
            print("[OTP Bot] OTP_BOT_TOKEN sozlanmagan, polling o'chirilgan.")
            return

        print(f"[OTP Bot] Polling boshlandi... (Token: {bot_token[:10]}...)")
    except Exception as e:
        print(f"[OTP Bot] START xato: {e}")
        return
    offset = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getUpdates",
                    params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]}
                )
            if resp.status_code == 200:
                data = resp.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await _process_bot_update(update, bot_token)
        except asyncio.CancelledError:
            print("[OTP Bot] Polling to'xtatildi.")
            break
        except Exception as e:
            print(f"[OTP Bot] Polling xato: {e}")
            await asyncio.sleep(5)


def _find_chat_id_by_phone(phone_normalized: str) -> str | None:
    """_phone_to_chat_id dan chat_id qidiradi (turli formatlar bo'yicha)."""
    # To'liq match
    if phone_normalized in _phone_to_chat_id:
        return _phone_to_chat_id[phone_normalized]
    # Oxirgi 9 raqam bilan match
    short = phone_normalized[-9:] if len(phone_normalized) >= 9 else phone_normalized
    for stored_phone, chat_id in _phone_to_chat_id.items():
        stored_short = stored_phone[-9:] if len(stored_phone) >= 9 else stored_phone
        if stored_short == short:
            return chat_id
    return None


def _generate_org_code(db: Session) -> str:
    while True:
        code = str(random.randint(10000000, 99999999))
        exists = db.query(Company).filter(Company.org_code == code).first()
        if not exists:
            return code
    raise RuntimeError("unreachable")  # type: ignore[unreachable]


# ─── Agent code check ────────────────────────────────────────────────────────

class AgentCodeCheck(BaseModel):
    code: str


@router.post("/check-agent-code")
def check_agent_code(data: AgentCodeCheck, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(
        Agent.code == data.code.strip().upper(),
        Agent.is_active == True
    ).first()
    if agent:
        return {"valid": True, "agent_name": agent.name}
    return {"valid": False, "agent_name": None}


# ─── OTP Endpointlari ────────────────────────────────────────────────────────

class SendOtpRequest(BaseModel):
    phone: str
    purpose: str = "register"  # "register" yoki "reset"


class VerifyOtpRequest(BaseModel):
    phone: str
    otp: str
    otp_session: Optional[str] = None  # JWT da saqlangan OTP sessiyasi


@router.post("/send-otp")
@limiter.limit("3/minute")
async def send_otp(request: Request, data: SendOtpRequest, db: Session = Depends(get_db)):
    """
    Telegram orqali OTP yuboradi.
    - purpose='reset': foydalanuvchi tizimda bo'lishi va bot bilan ulangan bo'lishi kerak
    - purpose='register': yangi foydalanuvchi — bot orqali phone→chat_id topiladi
    """
    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    bot_token = _get_otp_bot_token()
    is_dev_mode = not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE"

    user = db.query(User).filter(User.phone == normalized, User.status == UserStatus.active).first()

    # ─── purpose='reset' ──────────────────────────────────────────
    if data.purpose == "reset":
        if not user:
            raise HTTPException(status_code=404, detail="Bu telefon raqam tizimda topilmadi")

        otp = _generate_otp()

        if is_dev_mode:
            print(f"[DEV] Reset OTP for {normalized} ({user.name}): {otp}")
        else:
            chat_id = _find_chat_id_by_phone(normalized)
            if not chat_id and user.tg_chat_id:
                chat_id = user.tg_chat_id
            if not chat_id:
                bot_username = _get_bot_username(bot_token)
                return {
                    "sent": False,
                    "has_telegram": False,
                    "bot_link": f"https://t.me/{bot_username}",
                    "message": "Telegram bot ulanmagan. Quyidagi botni oching va telefon raqamingizni ulang.",
                }
            sent = await _send_telegram_otp(chat_id, otp, user.name)
            if not sent:
                raise HTTPException(status_code=500, detail="Telegram xabar yuborishda xato")

        from app.core.security import create_access_token
        otp_session = create_access_token(
            {"phone": normalized, "otp": otp, "purpose": "reset", "type": "otp_session"},
            expires_delta=timedelta(minutes=5)
        )
        return {"sent": True, "dev_mode": is_dev_mode, "has_telegram": True, "otp_session": otp_session}

    # ─── purpose='register' ──────────────────────────────────────
    elif data.purpose == "register":
        if user:
            raise HTTPException(status_code=400, detail="Bu telefon raqam allaqachon ro'yxatdan o'tgan")

        otp = _generate_otp()

        if is_dev_mode:
            print(f"[DEV] Register OTP for {normalized}: {otp}")
        else:
            chat_id = _find_chat_id_by_phone(normalized)
            if not chat_id:
                bot_username = _get_bot_username(bot_token)
                return {
                    "sent": False,
                    "has_telegram": False,
                    "bot_link": f"https://t.me/{bot_username}",
                    "message": "Ro'yxatdan o'tish uchun avval Telegram botni oching va raqamingizni ulang.",
                }
            sent = await _send_telegram_otp(chat_id, otp, "")
            if not sent:
                raise HTTPException(status_code=500, detail="Telegram xabar yuborishda xato")

        from app.core.security import create_access_token
        otp_session = create_access_token(
            {"phone": normalized, "otp": otp, "purpose": "register", "type": "otp_session"},
            expires_delta=timedelta(minutes=5)
        )
        return {"sent": True, "dev_mode": is_dev_mode, "has_telegram": True, "otp_session": otp_session}
    else:
        raise HTTPException(status_code=400, detail="Noto'g'ri purpose: 'register' yoki 'reset' bo'lishi kerak")


@router.post("/verify-otp")
def verify_otp(data: VerifyOtpRequest):
    """OTP kodni tekshiradi va verified_token qaytaradi (JWT otp_session orqali)"""
    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")

    if not data.otp_session:
        raise HTTPException(status_code=400, detail="otp_session talab qilinadi. Qaytadan yuborish tugmasini bosing.")

    from app.core.security import decode_token, create_access_token
    session_data = decode_token(data.otp_session)

    if not session_data or session_data.get("type") != "otp_session":
        raise HTTPException(status_code=400, detail="OTP sessiyasi noto'g'ri yoki muddati o'tgan. Qaytadan yuborish tugmasini bosing.")

    if session_data.get("phone") != normalized:
        raise HTTPException(status_code=400, detail="OTP sessiyasi bu telefon uchun emas.")

    if session_data.get("otp") != data.otp.strip():
        raise HTTPException(status_code=400, detail="OTP noto'g'ri. Qayta urinib ko'ring.")

    # OTP to'g'ri — verified_token yaratish
    verified_token = create_access_token({"phone": normalized, "type": "otp_verified"}, expires_delta=timedelta(minutes=10))
    return {"verified": True, "verified_token": verified_token}


# ─── Register ────────────────────────────────────────────────────────────────

class CompanyRegisterRequest(BaseModel):
    company_name: str
    name: str
    phone: str
    region: str
    district: str
    password: str
    agent_code: Optional[str] = None
    otp_verified_token: Optional[str] = None  # OTP tasdiqlash tokeni


@router.post("/register", status_code=201)
@limiter.limit("3/hour")
def register_company(request: Request, data: CompanyRegisterRequest, db: Session = Depends(get_db)):
    # Telefon normalizatsiya
    data.phone = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")

    bot_token = _get_otp_bot_token()
    is_dev_mode = not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE"

    # OTP tekshirish (agar bot sozlangan bo'lsa)
    if not is_dev_mode:
        if not data.otp_verified_token:
            raise HTTPException(status_code=400, detail="Telegram OTP tasdiqlash talab qilinadi")
        from app.core.security import decode_token
        token_data = decode_token(data.otp_verified_token)
        if not token_data or token_data.get("type") != "otp_verified":
            raise HTTPException(status_code=400, detail="OTP token noto'g'ri yoki muddati o'tgan")
        if token_data.get("phone") != data.phone:
            raise HTTPException(status_code=400, detail="OTP token bu telefon uchun emas")

    # Telefon takrorlanishini tekshirish
    existing_user = db.query(User).filter(User.phone == data.phone).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Bu telefon raqam allaqachon ro'yxatdan o'tgan")

    existing_company = db.query(Company).filter(Company.name == data.company_name).first()
    if existing_company:
        raise HTTPException(status_code=400, detail="Bu korxona nomi allaqachon mavjud")

    agent_id = None
    if data.agent_code:
        code_val = str(data.agent_code).strip().upper()
        agent = db.query(Agent).filter(
            Agent.code == code_val,
            Agent.is_active == True
        ).first()
        if not agent:
            raise HTTPException(status_code=400, detail="Agent kodi topilmadi yoki faol emas")
        agent_id = agent.id

    org_code = _generate_org_code(db)

    from app.models.billing import Tariff
    trial_tariff = db.query(Tariff).filter(Tariff.is_active == True, Tariff.price_per_month <= 0).first()
    tariff_id = trial_tariff.id if trial_tariff else None
    subs_ends_at = datetime.now(timezone.utc) + timedelta(days=7) if trial_tariff else None

    company = Company(
        name=data.company_name,
        org_code=org_code,
        region=data.region,
        district=data.district,
        phone=data.phone,
        is_active=True,
        agent_id=agent_id,
        tariff_id=tariff_id,
        subscription_ends_at=subs_ends_at,
        is_trial=True,
    )
    db.add(company)
    db.flush()

    branch = Branch(
        name=f"{data.company_name} (Asosiy)",
        company_id=company.id,
        is_active=True,
    )
    db.add(branch)
    db.flush()

    # Bot orqali ulangan chat_id ni topamiz (bo'lsa DB ga saqlaymiz)
    reg_chat_id = _find_chat_id_by_phone(data.phone) if not is_dev_mode else None

    user = User(
        name=data.name,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role=UserRole.admin,
        branch_id=branch.id,
        company_id=company.id,
        status=UserStatus.active,
        tg_chat_id=reg_chat_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    existing_currency = db.query(Currency).filter(
        Currency.company_id == company.id,
        Currency.code == "UZS"
    ).first()
    if not existing_currency:
        default_currency = Currency(
            name="O'zbek so'mi",
            code="UZS",
            rate=1.0,
            is_default=True,
            is_active=True,
            company_id=company.id,
        )
        db.add(default_currency)
        db.commit()

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "org_code": org_code,
        "company_name": company.name,
        "user": UserOut.model_validate(user),
    }


# ─── Login ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    phone: str
    password: str


class LoginOtpVerifyRequest(BaseModel):
    phone: str
    otp: str
    otp_session: Optional[str] = None


# Rollarni aniqlash: bu rollar login da OTP talab qiladi
_OTP_REQUIRED_ROLES = {"cashier", "manager", "accountant", "warehouse"}

def _process_login_success(user: User, db: Session, request: Request, is_otp: bool = False) -> TokenResponse:
    from app.models.user_company import UserCompany
    companies = db.query(UserCompany).filter(UserCompany.user_id == user.id, UserCompany.is_active == True).all()

    if len(companies) > 1:
        # Multi-company
        from sqlalchemy.orm import joinedload
        companies_with_co = (
            db.query(UserCompany)
            .options(joinedload(UserCompany.company))
            .filter(UserCompany.user_id == user.id, UserCompany.is_active == True)
            .all()
        )
        comps = [
            {
                "company_id": c.company_id,
                "company_name": c.company.name if c.company else "Noma'lum",
                "role": c.role,
                "is_active": c.is_active
            } for c in companies_with_co
        ]
        user_out = UserOut.model_validate(user)
        action = "LOGIN_OTP_MULTI" if is_otp else "LOGIN_MULTI"
        log_action(db=db, action=action, entity_type="user", entity_id=user.id,
                   user_id=user.id, ip_address=request.client.host if request.client else None)
        db.commit()
        # Vaqtinchalik token
        from app.core.security import create_access_token
        temp_token = create_access_token({"user_id": user.id, "type": "temp_login"}, expires_delta=timedelta(minutes=15))
        return TokenResponse(
            needs_company_selection=True,
            companies=comps,
            user=user_out,
            temp_token=temp_token
        )

    # 1 yoki 0 korxona
    if len(companies) == 1:
        company_id = companies[0].company_id
        role = companies[0].role
    else:
        company_id = user.company_id
        role = user.role

    role_val = role.value if hasattr(role, 'value') else str(role)
    access_token = create_access_token({"sub": str(user.id), "role": role_val, "company_id": company_id})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    user_out = UserOut.model_validate(user)

    action = "LOGIN_OTP" if is_otp else "LOGIN"
    log_action(db=db, action=action, entity_type="user", entity_id=user.id,
               user_id=user.id, ip_address=request.client.host if request.client else None)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_out
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    try:
        normalized_phone = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
        user = db.query(User).filter(User.phone == normalized_phone, User.status == UserStatus.active).first()

        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Telefon yoki parol noto'g'ri",
            )

        # Admin, director, super_admin — OTP talab qilinmaydi
        user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
        if user_role not in _OTP_REQUIRED_ROLES:
            return _process_login_success(user, db, request, is_otp=False)

        # Kassir/boshqa rollar — OTP yuboramiz
        otp = _generate_otp()
        bot_token = _get_otp_bot_token()
        is_dev_mode = not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE"

        otp_sent = False
        if not is_dev_mode:
            chat_id = _find_chat_id_by_phone(normalized_phone)
            if not chat_id and user.tg_chat_id:
                chat_id = user.tg_chat_id
            if chat_id:
                try:
                    import httpx
                    httpx.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": chat_id,
                              "text": f"🔐 ERP kirish kodi: *{otp}*\n\nBu kod 5 daqiqa amal qiladi.",
                              "parse_mode": "Markdown"},
                        timeout=5,
                    )
                    otp_sent = True
                except Exception as e:
                    print(f"[OTP Login] Yuborishda xato: {e}")
        else:
            print(f"[OTP Login DEV] {normalized_phone} → {otp}")
            otp_sent = True

        from app.core.security import create_access_token
        otp_session = create_access_token(
            {"phone": normalized_phone, "otp": otp, "purpose": "login", "type": "otp_session"},
            expires_delta=timedelta(minutes=5)
        )

        # OTP talab qilinmoqda — to'liq token BERMAYMIZ
        raise HTTPException(
            status_code=202,
            detail={
                "otp_required": True,
                "otp_sent": otp_sent,
                "name": user.name,
                "dev_mode": is_dev_mode,
                "otp_session": otp_session,
                "message": "OTP Telegram orqali yuborildi" if otp_sent else "Telegram bot ulanmagan",
            }
        )

    except HTTPException:
        raise
    except Exception:
        import traceback
        print("LOGIN ERROR TRACEBACK:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/login-verify", response_model=TokenResponse)
def login_verify_otp(request: Request, data: LoginOtpVerifyRequest, db: Session = Depends(get_db)):
    """OTP ni tekshiradi va token beradi (kassir/sub-foydalanuvchilar uchun)"""
    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")

    if not data.otp_session:
        raise HTTPException(status_code=400, detail="otp_session talab qilinadi. Qaytadan urinib ko'ring.")

    from app.core.security import decode_token
    session_data = decode_token(data.otp_session)

    if not session_data or session_data.get("type") != "otp_session" or session_data.get("purpose") != "login":
        raise HTTPException(status_code=400, detail="OTP sessiyasi noto'g'ri yoki muddati o'tgan. Qaytadan urinib ko'ring.")

    if session_data.get("phone") != normalized:
        raise HTTPException(status_code=400, detail="OTP sessiyasi bu telefon uchun emas.")

    if session_data.get("otp") != data.otp.strip():
        raise HTTPException(status_code=400, detail="OTP noto'g'ri")

    user = db.query(User).filter(User.phone == normalized, User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    return _process_login_success(user, db, request, is_otp=True)


class SelectCompanyRequest(BaseModel):
    temp_token: str
    company_id: int

@router.post("/select-company", response_model=TokenResponse)
def select_company(request: Request, data: SelectCompanyRequest, db: Session = Depends(get_db)):
    """Ko'p korxonali foydalanuvchi korxonani tanlaganda token berish"""
    from app.core.security import decode_token
    token_data = decode_token(data.temp_token)
    if not token_data or token_data.get("type") != "temp_login":
        raise HTTPException(status_code=400, detail="Sessiya yaroqsiz yoki eskirgan. Iltimos qayta login qiling")
    
    user_id = token_data.get("user_id")
    user = db.query(User).filter(User.id == user_id, User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    
    from app.models.user_company import UserCompany
    uc = db.query(UserCompany).filter(
        UserCompany.user_id == user.id, 
        UserCompany.company_id == data.company_id,
        UserCompany.is_active == True
    ).first()
    
    if not uc:
        raise HTTPException(status_code=403, detail="Siz bu korxonaga biriktirilmagansiz")

    role_val = uc.role.value if hasattr(uc.role, 'value') else str(uc.role)
    access_token = create_access_token({"sub": str(user.id), "role": role_val, "company_id": uc.company_id})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    user_out = UserOut.model_validate(user)

    log_action(db=db, action="LOGIN_SELECT_COMPANY", entity_type="user", entity_id=user.id,
               user_id=user.id, ip_address=request.client.host if request.client else None)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=user_out
    )



@router.post("/refresh", response_model=TokenResponse)
def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token yaroqsiz")
    user = db.query(User).filter(User.id == int(payload["sub"]), User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Foydalanuvchi topilmadi")
    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_refresh_token = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ─── Parolni tiklash ─────────────────────────────────────────────────────────

class CheckPhoneRequest(BaseModel):
    phone: str


class ResetPasswordRequest(BaseModel):
    phone: str
    verified_token: str
    new_password: str


@router.post("/check-phone")
@limiter.limit("3/minute")
async def check_phone(request: Request, data: CheckPhoneRequest, db: Session = Depends(get_db)):
    """
    Telefon bazada borligini tekshiradi va OTP yuboradi.
    Dev modeda OTP consolega chiqariladi.
    Agar tg_chat_id yo'q bo'lsa — bot link qaytaradi.
    """
    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    user = db.query(User).filter(User.phone == normalized, User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=404, detail="Bu telefon raqam tizimda topilmadi")

    bot_token = _get_otp_bot_token()
    is_dev_mode = not bot_token or bot_token == "YOUR_TELEGRAM_BOT_TOKEN_HERE"

    otp = _generate_otp()

    if is_dev_mode:
        print(f"[DEV] Reset OTP for {normalized} ({user.name}): {otp}")
        from app.core.security import create_access_token
        otp_session = create_access_token(
            {"phone": normalized, "otp": otp, "purpose": "reset", "type": "otp_session"},
            expires_delta=timedelta(minutes=5)
        )
        return {
            "exists": True,
            "name": user.name,
            "otp_sent": True,
            "has_telegram": True,
            "dev_mode": True,
            "otp_session": otp_session,
        }

    # Avval DB dagi tg_chat_id ni tekshiramiz
    chat_id = user.tg_chat_id

    if not chat_id:
        chat_id = _find_chat_id_by_phone(normalized)
        if chat_id:
            user.tg_chat_id = chat_id
            db.commit()

    if not chat_id:
        return {
            "exists": True,
            "name": user.name,
            "otp_sent": False,
            "has_telegram": False,
            "bot_link": f"https://t.me/{_get_bot_username(bot_token)}",
            "message": "Telegram bot ulanmagan. Quyidagi botni oching, /start bosing va raqamingizni ulang.",
        }

    sent = await _send_telegram_otp(chat_id, otp, user.name)
    if not sent:
        raise HTTPException(status_code=500, detail="Telegram xabar yuborishda xato. Qayta urinib ko'ring.")

    from app.core.security import create_access_token
    otp_session = create_access_token(
        {"phone": normalized, "otp": otp, "purpose": "reset", "type": "otp_session"},
        expires_delta=timedelta(minutes=5)
    )
    return {
        "exists": True,
        "name": user.name,
        "otp_sent": True,
        "has_telegram": True,
        "dev_mode": False,
        "otp_session": otp_session,
    }


@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    """OTP verified_token orqali parolni tiklash"""
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Parol kamida 6 ta belgidan iborat bo'lishi kerak")

    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    from app.core.security import decode_token
    token_data = decode_token(data.verified_token)

    if not token_data or token_data.get("type") != "otp_verified":
        raise HTTPException(status_code=400, detail="OTP tasdiqlanmagan yoki muddati o'tgan. Qaytadan boshlang.")
    if token_data.get("phone") != normalized:
        raise HTTPException(status_code=400, detail="Token bu telefon raqam uchun emas")

    user = db.query(User).filter(User.phone == normalized, User.status == UserStatus.active).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")

    user.hashed_password = hash_password(data.new_password)
    db.commit()

    return {"message": "Parol muvaffaqiyatli yangilandi"}


# ─── Telegram bot ulash ───────────────────────────────────────────────────────

class LinkTelegramRequest(BaseModel):
    chat_id: str
    phone: str


@router.post("/link-telegram")
def link_telegram(data: LinkTelegramRequest, db: Session = Depends(get_db)):
    """Telegram bot orqali foydalanuvchi chat_id ni tizimga ulaydi."""
    normalized = data.phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    user = db.query(User).filter(User.phone == normalized, User.status == UserStatus.active).first()
    if not user:
        return {"linked": False, "message": "Foydalanuvchi topilmadi"}
    user.tg_chat_id = data.chat_id
    db.commit()
    return {"linked": True, "name": user.name}
