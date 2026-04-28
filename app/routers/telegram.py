from datetime import datetime, timezone

from fastapi import APIRouter, Request, BackgroundTasks, Depends  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
import httpx

from app.database import get_db  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.sale import Sale, PaymentType  # type: ignore

router = APIRouter(prefix="/telegram", tags=["Telegram"])

FMT = lambda v: f"{float(v or 0):,.0f}".replace(",", " ")

PAY_EMOJI = {
    PaymentType.cash: "💵",
    PaymentType.card: "💳",
    PaymentType.uzcard: "💳",
    PaymentType.humo: "💳",
    PaymentType.bank: "🏦",
    PaymentType.click: "📱",
    PaymentType.payme: "📱",
    PaymentType.visa: "💳",
    PaymentType.uzum: "📱",
    PaymentType.debt: "🔖",
    PaymentType.mixed: "💰",
}


async def send_telegram_message(token: str, chat_id: str, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        print("Telegram xato:", str(e))


def _find_customer_by_chat(db: Session, token: str, chat_id: str):
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
            [{"text": "💰 Qarz va to'lovlar"}, {"text": "📦 Oxirgi xaridlar"}],
            [{"text": "❓ Yordam"}],
        ],
        "resize_keyboard": True,
    }


async def _handle_balans(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    if not customer:
        bg.add_task(
            send_telegram_message, token, chat_id,
            "💰 Sizning profilingiz topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard(),
        )
        return

    lines = [f"💳 <b>{customer.name}</b>\n"]
    lines.append(f"📌 Joriy qarz: <b>{FMT(customer.debt_balance)} so'm</b>")
    lines.append(f"📊 Qarz limiti: <b>{FMT(customer.debt_limit)} so'm</b>")

    if float(customer.bonus_balance or 0) > 0:
        lines.append(f"⭐ Bonus balans: <b>{FMT(customer.bonus_balance)} so'm</b>")
    if float(customer.discount_percent or 0) > 0:
        lines.append(f"🏷 Shaxsiy chegirma: <b>{customer.discount_percent}%</b>")
    if float(customer.cashback_percent or 0) > 0:
        lines.append(f"🔄 Keshbek: <b>{customer.cashback_percent}%</b>")
    lines.append(f"🏆 Daraja: <b>{customer.tier}</b>")

    # Qarz muddatlari
    today = datetime.now(timezone.utc).date()
    debt_sales = (
        db.query(Sale)
        .filter(
            Sale.customer_id == customer.id,
            Sale.payment_type == PaymentType.debt,
            Sale.status == "completed",
            Sale.debt_due_date.isnot(None),
        )
        .order_by(Sale.debt_due_date)
        .limit(5)
        .all()
    )

    if debt_sales:
        lines.append("\n📅 <b>Qarz muddatlari:</b>")
        for s in debt_sales:
            delta = (s.debt_due_date - today).days
            if delta < 0:
                lines.append(f"🔴 {s.debt_due_date.strftime('%d.%m.%Y')} — muddati o'tgan! ({abs(delta)} kun)")
            elif delta == 0:
                lines.append(f"🟠 {s.debt_due_date.strftime('%d.%m.%Y')} — <b>bugun!</b>")
            elif delta <= 3:
                lines.append(f"🟡 {s.debt_due_date.strftime('%d.%m.%Y')} — {delta} kun qoldi")
            else:
                lines.append(f"🟢 {s.debt_due_date.strftime('%d.%m.%Y')} — {delta} kun qoldi")

    bg.add_task(send_telegram_message, token, chat_id, "\n".join(lines), _build_main_keyboard())


async def _handle_sotuvlar(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    if not customer:
        bg.add_task(
            send_telegram_message, token, chat_id,
            "📦 Profil topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard(),
        )
        return

    sales = (
        db.query(Sale)
        .filter(Sale.customer_id == customer.id)
        .order_by(Sale.created_at.desc())
        .limit(5)
        .all()
    )

    if not sales:
        msg = f"📦 <b>{customer.name}</b>\n\nHozircha xarid tarixi mavjud emas."
    else:
        lines = [f"📦 <b>{customer.name}</b> — oxirgi xaridlar:\n"]
        for s in sales:
            d = s.created_at.strftime("%d.%m.%Y")
            emoji = PAY_EMOJI.get(s.payment_type, "💰")
            lines.append(f"{emoji} {d} — <b>{FMT(s.total_amount)} so'm</b>")
            if s.payment_type == PaymentType.debt and s.debt_due_date:
                lines.append(f"   └ Muddat: {s.debt_due_date.strftime('%d.%m.%Y')}")
        msg = "\n".join(lines)

    bg.add_task(send_telegram_message, token, chat_id, msg, _build_main_keyboard())


async def _handle_yordam(db, token, chat_id, company, customer, bg):
    msg = (
        "📋 <b>Botdan foydalanish yo'riqnomasi:</b>\n\n"
        "💰 <b>Qarz va to'lovlar</b>\n"
        "   Joriy qarz, qarz muddatlari, bonus va chegirma\n\n"
        "📦 <b>Oxirgi xaridlar</b>\n"
        "   So'nggi 5 ta xaridingiz tarixi\n\n"
        "<b>Buyruqlar:</b>\n"
        "/balans — Qarz va balans holati\n"
        "/start — Qayta ro'yxatdan o'tish\n\n"
        "❓ Muammolar bo'lsa do'kon xodimlari bilan bog'laning."
    )
    bg.add_task(send_telegram_message, token, chat_id, msg, _build_main_keyboard())


COMMAND_MAP = {
    "/balans": _handle_balans,
    "💰 balans": _handle_balans,
    "💰 qarz va to'lovlar": _handle_balans,
    "📦 oxirgi xaridlar": _handle_sotuvlar,
    "/sotuvlar": _handle_sotuvlar,
    "❓ yordam": _handle_yordam,
    "/yordam": _handle_yordam,
    "/help": _handle_yordam,
}


@router.post("/webhook/{token}")
async def telegram_webhook(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Kompaniya Telegram botiga webhook ulangan bo'lsa, xabarlar shu yerga keladi.
    Webhook URL: https://[DOMAININGIZ]/api/telegram/webhook/{bot_token}
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
                "keyboard": [[{"text": "📞 Raqamni yuborish", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            }
            msg_text = (
                "👋 <b>Assalomu alaykum!</b>\n\n"
                "Tizimga ulanish uchun pastdagi <b>📞 Raqamni yuborish</b> "
                "tugmasini bosing.\n\n"
                "Tizim raqamingizni avtomatik taniydi va profilingizni ulaydi."
            )
            background_tasks.add_task(send_telegram_message, token, chat_id, msg_text, keyboard)
            return {"ok": True}

        # Kontakt yuborish — ro'yxatdan o'tish
        if "contact" in message:
            contact = message["contact"]
            phone = contact.get("phone_number", "")
            p_clean = "".join(filter(str.isdigit, str(phone)))

            company = db.query(Company).filter(Company.tg_bot_token == token).first()
            if not company:
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    "❌ Kompaniya topilmadi yoki bot xato sozlangan.",
                    {"remove_keyboard": True},
                )
                return {"ok": True}

            found_customer = None
            for c in db.query(Customer).filter(Customer.company_id == company.id).all():
                if c.phone:
                    c_clean = "".join(filter(str.isdigit, str(c.phone)))
                    if len(c_clean) >= 9 and len(p_clean) >= 9 and c_clean[-9:] == p_clean[-9:]:
                        found_customer = c
                        break

            if found_customer:
                found_customer.tg_chat_id = chat_id
                db.commit()
                reply_text = (
                    f"✅ <b>Assalomu alaykum, {found_customer.name}!</b>\n\n"
                    f"Profilingiz <b>{company.name}</b> tizimiga muvaffaqiyatli ulandi. 🎉\n\n"
                    "Quyidagi tugmalardan foydalanishingiz mumkin 👇"
                )
                background_tasks.add_task(
                    send_telegram_message, token, chat_id, reply_text, _build_main_keyboard()
                )
            else:
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    "❌ Kechirasiz, bu raqam bo'yicha mijoz topilmadi.\n\n"
                    "Avval do'kondan ro'yxatdan o'tishingiz kerak.",
                    {"remove_keyboard": True},
                )
            return {"ok": True}

        # Komandalar va klaviatura tugmalari
        txt = text.lower()
        handler = COMMAND_MAP.get(txt)
        if not handler:
            if any(k in txt for k in ("balans", "qarz", "tolov", "to'lov", "to`lov")):
                handler = _handle_balans
            elif any(k in txt for k in ("xarid", "sotuv", "tarix")):
                handler = _handle_sotuvlar
            elif any(k in txt for k in ("yordam", "help")):
                handler = _handle_yordam

        if handler:
            company, customer = _find_customer_by_chat(db, token, chat_id)
            if not company:
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    "❌ Kompaniya topilmadi.", {"remove_keyboard": True}
                )
            else:
                await handler(db, token, chat_id, company, customer, background_tasks)
            return {"ok": True}

        # Noma'lum buyruq
        if text.startswith("/"):
            help_msg = (
                "📋 <b>Mavjud buyruqlar:</b>\n\n"
                "/balans — 💰 Qarz va balans\n"
                "/sotuvlar — 📦 Oxirgi xaridlar\n"
                "/yordam — ❓ Yordam\n"
                "/start — 🔄 Qayta ro'yxatdan o'tish"
            )
            background_tasks.add_task(
                send_telegram_message, token, chat_id, help_msg, _build_main_keyboard()
            )
        else:
            background_tasks.add_task(
                send_telegram_message, token, chat_id,
                "⚙️ Menyu yangilandi. Quyidagi tugmalardan foydalaning:",
                _build_main_keyboard(),
            )

        return {"ok": True}
    except Exception as e:
        print("Webhook Error:", str(e))
        return {"ok": False}
