from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request, BackgroundTasks, Depends  # type: ignore
from sqlalchemy import func  # type: ignore
from sqlalchemy.orm import Session, joinedload  # type: ignore
import httpx

from app.database import get_db  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.sale import Sale  # type: ignore
from app.models.inventory import StockLevel  # type: ignore
from app.models.product import Product  # type: ignore

router = APIRouter(prefix="/telegram", tags=["Telegram"])

FMT = lambda v: f"{float(v or 0):,.0f}".replace(",", " ")


async def send_telegram_message(token: str, chat_id: str, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload)
    except Exception as e:
        print("Telegram xato:", str(e))


def _find_customer_by_chat(db: Session, token: str, chat_id: str):
    """Token bo'yicha kompaniya va chat_id bo'yicha mijozni topadi."""
    company = db.query(Company).filter(Company.tg_bot_token == token).first()
    if not company:
        return None, None
    customer = db.query(Customer).filter(
        Customer.company_id == company.id,
        Customer.tg_chat_id == chat_id
    ).first()
    return company, customer


def _build_main_keyboard():
    return {
        "keyboard": [
            [{"text": "💰 Qarz va to'lovlar"}],
        ],
        "resize_keyboard": True,
    }


async def _handle_balans(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    """Mijoz balansi va qarz holati."""
    if customer:
        msg = (
            f"💰 <b>{customer.name}</b>\n\n"
            f"📌 Jami Qarz (Joriy qarz): <b>{FMT(customer.debt_balance)} so'm</b>\n"
            f"📌 Qarz limiti: <b>{FMT(customer.debt_limit)} so'm</b>\n"
            f"⭐ Bonus balansi: <b>{FMT(customer.bonus_balance or 0)} so'm</b>\n"
            f"🏷 Daraja: <b>{customer.tier}</b>\n"
        )
    else:
        msg = "💰 Sizning profilingiz topilmadi. /start buyrug'i bilan ro'yxatdan o'ting."
    bg.add_task(send_telegram_message, token, chat_id, msg, _build_main_keyboard())


COMMAND_MAP = {
    "/balans": _handle_balans,
    "💰 balans": _handle_balans,
    "💰 qarz va to'lovlar": _handle_balans,
}


@router.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Kompaniya o'zining telegram botiga webhook ulagan bo'lsa, xabarlar shu yerga keladi.
    Webhook URL: https://[SIZNING_DOMAININGIZ]/api/telegram/webhook/{bot_token}
    """
    try:
        data = await request.json()
        if "message" not in data:
            return {"ok": True}

        message = data["message"]
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()

        # /start — telefon raqam so'rash
        if text.startswith("/start"):
            keyboard = {
                "keyboard": [
                    [{"text": "📞 Raqamni yuborish", "request_contact": True}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
            msg_text = "👋 Assalomu alaykum!\n\nIltimos, tizimga ulanish (identifikatsiya) uchun pastdagi <b>Raqamni yuborish</b> tugmasini bosing."
            background_tasks.add_task(send_telegram_message, token, chat_id, msg_text, keyboard)
            return {"ok": True}

        # Kontakt yuborish — ro'yxatdan o'tish
        if "contact" in message:
            contact = message["contact"]
            phone = contact.get("phone_number", "")
            p_clean = "".join(filter(str.isdigit, str(phone)))

            company = db.query(Company).filter(Company.tg_bot_token == token).first()
            if not company:
                background_tasks.add_task(send_telegram_message, token, chat_id, "❌ Kompaniya topilmadi yoki bot xato sozlangan.", {"remove_keyboard": True})
                return {"ok": True}

            customers = db.query(Customer).filter(Customer.company_id == company.id).all()
            found_customer = None
            for c in customers:
                if c.phone:
                    c_clean = "".join(filter(str.isdigit, str(c.phone)))
                    if len(c_clean) >= 9 and len(p_clean) >= 9 and c_clean[-9:] == p_clean[-9:]:
                        found_customer = c
                        break

            if found_customer:
                found_customer.tg_chat_id = chat_id
                db.commit()
                reply_text = (
                    f"✅ Assalomu alaykum, <b>{found_customer.name}</b>!\n\n"
                    f"Sizning profilingiz <b>{company.name}</b> tizimiga muvaffaqiyatli ulandi. 🎉\n\n"
                    f"Quyidagi buyruqlardan foydalanishingiz mumkin:"
                )
                background_tasks.add_task(send_telegram_message, token, chat_id, reply_text, _build_main_keyboard())
            else:
                msg_err = "❌ Kechirasiz, sizning raqamingiz bo'yicha mijoz topilmadi. Avval do'kondan ro'yxatdan o'tishingiz yoki xarid qilishingiz kerak!"
                background_tasks.add_task(send_telegram_message, token, chat_id, msg_err, {"remove_keyboard": True})
            return {"ok": True}

        # Komandalar — /sotuv, /ombor, /balans + keyboard tugmalari
        txt = text.lower()
        handler = COMMAND_MAP.get(txt)
        if not handler:
            if "balans" in txt or "qarz" in txt or "tolov" in txt or "to'lov" in txt or "to`lov" in txt:
                handler = _handle_balans

        if handler:
            company, customer = _find_customer_by_chat(db, token, chat_id)
            if not company:
                background_tasks.add_task(send_telegram_message, token, chat_id, "❌ Kompaniya topilmadi.", {"remove_keyboard": True})
            else:
                await handler(db, token, chat_id, company, customer, background_tasks)
            return {"ok": True}

        # Noma'lum komanda — yordam
        if text.startswith("/"):
            help_msg = (
                "📋 <b>Mavjud buyruqlar:</b>\n\n"
                "/balans — 💰 Qarz va joriy to'lovlar ma'lumotlari\n"
                "/start — 🔄 Qayta ro'yxatdan o'tish"
            )
            background_tasks.add_task(send_telegram_message, token, chat_id, help_msg, _build_main_keyboard())
        else:
            # Har qanday tushunarsiz matn kelsa (masalan eski menyu tugmasi bossa), yangi menyuni yuborib yangilab qoyamiz.
            background_tasks.add_task(send_telegram_message, token, chat_id, "⚙️ Menyu yangilandi. Iltimos quyidagi tugmalardan foydalaning:", _build_main_keyboard())

        return {"ok": True}
    except Exception as e:
        print("Webhook Error:", str(e))
        return {"ok": False}
