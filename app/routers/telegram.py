import io
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Request, BackgroundTasks, Depends  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
import httpx

from app.database import get_db  # type: ignore
from app.models.bot_session import BotSession  # type: ignore
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

# ── Telegram API helpers ──────────────────────────────────────────────────────

async def send_telegram_message(token: str, chat_id: str, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        print("Telegram xato:", e)


async def send_loyalty_card(token: str, chat_id: str, customer_name: str, card_number: str, cashback_percent: float = 0):
    """Barcode ko'rinishida loyallik kartasini yuboradi."""
    caption = (
        f"🎫 <b>{customer_name}</b>\n\n"
        f"💳 Karta raqami: <code>{card_number}</code>\n"
        f"🔄 Keshbek: <b>{cashback_percent}%</b> har xariddan\n\n"
        f"ℹ️ Shtrix-kodni kassirga ko'rsating — naqd pul yig'asiz!"
    )
    try:
        import barcode  # type: ignore
        from barcode.writer import ImageWriter  # type: ignore

        Code128 = barcode.get_barcode_class("code128")
        buf = io.BytesIO()
        Code128(card_number, writer=ImageWriter()).write(buf, options={
            "module_height": 12.0,
            "module_width": 0.38,
            "quiet_zone": 6.5,
            "font_size": 10,
            "text_distance": 4.0,
        })
        buf.seek(0)

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post(
                url,
                data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                files={"photo": ("card.png", buf.read(), "image/png")},
            )
    except Exception as e:
        print("Barcode xato:", e)
        # Fallback: matn ko'rinishida yuboradi
        await send_telegram_message(token, chat_id, caption, _build_main_keyboard())


# ── DB helpers ────────────────────────────────────────────────────────────────

def _find_customer_by_chat(db: Session, token: str, chat_id: str):
    company = db.query(Company).filter(Company.tg_bot_token == token).first()
    if not company:
        return None, None
    customer = db.query(Customer).filter(
        Customer.company_id == company.id,
        Customer.tg_chat_id == chat_id,
    ).first()
    return company, customer


def _get_session(db: Session, chat_id: str, token: str):
    return db.query(BotSession).filter(
        BotSession.chat_id == chat_id,
        BotSession.token == token,
    ).first()


def _upsert_session(db: Session, chat_id: str, token: str, step: str, temp_name: str = None):
    session = _get_session(db, chat_id, token)
    if session:
        session.step = step
        session.temp_name = temp_name
    else:
        session = BotSession(chat_id=chat_id, token=token, step=step, temp_name=temp_name)
        db.add(session)
    db.commit()


def _delete_session(db: Session, chat_id: str, token: str):
    db.query(BotSession).filter(
        BotSession.chat_id == chat_id,
        BotSession.token == token,
    ).delete()
    db.commit()


def _generate_card_number(db: Session, company_id: int) -> str:
    """13 xonali unique loyallik karta raqami."""
    existing = {
        r[0] for r in db.query(Customer.card_number).filter(
            Customer.company_id == company_id,
            Customer.card_number.isnot(None),
        ).all()
    }
    while True:
        num = "2" + "".join(str(random.randint(0, 9)) for _ in range(12))
        if num not in existing:
            return num


# ── Klaviatura ────────────────────────────────────────────────────────────────

def _build_main_keyboard():
    return {
        "keyboard": [
            [{"text": "💰 Qarz va to'lovlar"}, {"text": "📦 Oxirgi xaridlar"}],
            [{"text": "🎫 Mening kartam"}, {"text": "❓ Yordam"}],
        ],
        "resize_keyboard": True,
    }

def _build_phone_keyboard():
    return {
        "keyboard": [[{"text": "📞 Telefon raqamni yuborish", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


# ── Command handlers ──────────────────────────────────────────────────────────

async def _handle_balans(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    if not customer:
        bg.add_task(send_telegram_message, token, chat_id,
            "💰 Profilingiz topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard())
        return

    lines = [f"💳 <b>{customer.name}</b>\n"]
    lines.append(f"📌 Joriy qarz: <b>{FMT(customer.debt_balance)} so'm</b>")
    lines.append(f"📊 Qarz limiti: <b>{FMT(customer.debt_limit)} so'm</b>")
    if float(customer.bonus_balance or 0) > 0:
        lines.append(f"⭐ Bonus: <b>{FMT(customer.bonus_balance)} so'm</b>")
    if float(customer.discount_percent or 0) > 0:
        lines.append(f"🏷 Chegirma: <b>{customer.discount_percent}%</b>")
    if float(customer.cashback_percent or 0) > 0:
        lines.append(f"🔄 Keshbek: <b>{customer.cashback_percent}%</b>")
    lines.append(f"🏆 Daraja: <b>{customer.tier}</b>")

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
        bg.add_task(send_telegram_message, token, chat_id,
            "📦 Profil topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard())
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


async def _handle_karta(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    if not customer:
        bg.add_task(send_telegram_message, token, chat_id,
            "🎫 Profil topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard())
        return

    if not customer.card_number:
        card_number = _generate_card_number(db, company.id)
        customer.card_number = card_number
        db.commit()
    else:
        card_number = customer.card_number

    cashback = float(customer.cashback_percent or 0)
    bg.add_task(send_loyalty_card, token, chat_id, customer.name, card_number, cashback)


async def _handle_yordam(db, token, chat_id, company, customer, bg):
    msg = (
        "📋 <b>Botdan foydalanish yo'riqnomasi:</b>\n\n"
        "💰 <b>Qarz va to'lovlar</b> — Joriy qarz, muddat va bonus\n"
        "📦 <b>Oxirgi xaridlar</b> — So'nggi 5 ta xarid\n"
        "🎫 <b>Mening kartam</b> — Loyallik karta va barcode\n\n"
        "<b>Buyruqlar:</b>\n"
        "/balans — Qarz holati\n"
        "/karta — Loyallik kartam\n"
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
    "🎫 mening kartam": _handle_karta,
    "/karta": _handle_karta,
    "❓ yordam": _handle_yordam,
    "/yordam": _handle_yordam,
    "/help": _handle_yordam,
}


# ── Webhook ───────────────────────────────────────────────────────────────────

@router.post("/webhook/{token}")
async def telegram_webhook(
    token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        data = await request.json()
        if "message" not in data:
            return {"ok": True}

        message = data["message"]
        chat_id = str(message["chat"]["id"])
        text = message.get("text", "").strip()

        # ── /start ───────────────────────────────────────────────
        if text.startswith("/start"):
            company, customer = _find_customer_by_chat(db, token, chat_id)
            if not company:
                background_tasks.add_task(send_telegram_message, token, chat_id,
                    "❌ Bot sozlanmagan yoki kompaniya topilmadi.")
                return {"ok": True}

            if customer:
                # Allaqachon ro'yxatdan o'tgan — xush kelibsiz
                _delete_session(db, chat_id, token)
                reply = (
                    f"👋 <b>Assalomu alaykum, {customer.name}!</b>\n\n"
                    f"Siz <b>{company.name}</b> tizimiga ulangansiz.\n"
                    "Quyidagi tugmalardan foydalaning 👇"
                )
                background_tasks.add_task(send_telegram_message, token, chat_id, reply, _build_main_keyboard())
            else:
                # Yangi foydalanuvchi — ismini so'raymiz
                _upsert_session(db, chat_id, token, step="awaiting_name")
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    f"👋 <b>Assalomu alaykum!</b>\n\n"
                    f"<b>{company.name}</b> do'konining loyallik tizimiga xush kelibsiz!\n\n"
                    f"Ro'yxatdan o'tish uchun <b>ismingizni</b> kiriting:",
                    {"remove_keyboard": True},
                )
            return {"ok": True}

        # ── Kontakt (telefon raqam) ───────────────────────────────
        if "contact" in message:
            contact = message["contact"]
            phone = contact.get("phone_number", "")
            p_clean = "".join(filter(str.isdigit, str(phone)))

            company = db.query(Company).filter(Company.tg_bot_token == token).first()
            if not company:
                background_tasks.add_task(send_telegram_message, token, chat_id,
                    "❌ Kompaniya topilmadi.", {"remove_keyboard": True})
                return {"ok": True}

            # Bazada telefon bo'yicha mijoz qidirish
            found_customer = None
            for c in db.query(Customer).filter(Customer.company_id == company.id).all():
                if c.phone:
                    c_clean = "".join(filter(str.isdigit, str(c.phone)))
                    if len(c_clean) >= 9 and len(p_clean) >= 9 and c_clean[-9:] == p_clean[-9:]:
                        found_customer = c
                        break

            session = _get_session(db, chat_id, token)

            if found_customer:
                # Mavjud mijoz — ulab, kartasini yuboramiz
                found_customer.tg_chat_id = chat_id
                if not found_customer.card_number:
                    found_customer.card_number = _generate_card_number(db, company.id)
                db.commit()
                _delete_session(db, chat_id, token)

                cashback = float(found_customer.cashback_percent or 0)
                welcome = (
                    f"✅ <b>Assalomu alaykum, {found_customer.name}!</b>\n\n"
                    f"Profilingiz <b>{company.name}</b> tizimiga ulandi. 🎉\n\n"
                    "Loyallik kartangiz:"
                )
                background_tasks.add_task(send_telegram_message, token, chat_id, welcome, _build_main_keyboard())
                background_tasks.add_task(send_loyalty_card, token, chat_id,
                    found_customer.name, found_customer.card_number, cashback)
            elif session and session.temp_name:
                # Yangi mijoz — ro'yxatdan o'tkazamiz
                temp_name = session.temp_name
                card_number = _generate_card_number(db, company.id)
                new_customer = Customer(
                    name=temp_name,
                    phone=phone,
                    company_id=company.id,
                    tg_chat_id=chat_id,
                    card_number=card_number,
                )
                db.add(new_customer)
                db.commit()
                db.refresh(new_customer)
                _delete_session(db, chat_id, token)

                cashback = float(new_customer.cashback_percent or 0)
                welcome = (
                    f"✅ <b>Ro'yxatdan o'tish muvaffaqiyatli!</b>\n\n"
                    f"👤 Ism: <b>{temp_name}</b>\n"
                    f"📞 Telefon: <b>{phone}</b>\n\n"
                    f"Loyallik kartangiz:"
                )
                background_tasks.add_task(send_telegram_message, token, chat_id, welcome, _build_main_keyboard())
                background_tasks.add_task(send_loyalty_card, token, chat_id,
                    temp_name, card_number, cashback)
            else:
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    "❌ Bu raqam tizimda topilmadi.\n\n"
                    "Ro'yxatdan o'tish uchun /start bosing.",
                    {"remove_keyboard": True},
                )
            return {"ok": True}

        # ── Matn xabar — ro'yxatdan o'tish holati tekshiruvi ─────
        session = _get_session(db, chat_id, token)
        if session and session.step == "awaiting_name" and text and not text.startswith("/"):
            # Ismni saqlaymiz, telefon so'raymiz
            _upsert_session(db, chat_id, token, step="awaiting_phone", temp_name=text[:200])
            background_tasks.add_task(
                send_telegram_message, token, chat_id,
                f"✍️ Ism qabul qilindi: <b>{text}</b>\n\n"
                f"Endi <b>📞 Telefon raqamni yuborish</b> tugmasini bosing:",
                _build_phone_keyboard(),
            )
            return {"ok": True}

        # ── Komandalar va klaviatura tugmalari ────────────────────
        txt = text.lower()
        handler = COMMAND_MAP.get(txt)
        if not handler:
            if any(k in txt for k in ("balans", "qarz", "tolov", "to'lov")):
                handler = _handle_balans
            elif any(k in txt for k in ("xarid", "sotuv", "tarix")):
                handler = _handle_sotuvlar
            elif any(k in txt for k in ("karta", "card", "bonus")):
                handler = _handle_karta
            elif any(k in txt for k in ("yordam", "help")):
                handler = _handle_yordam

        if handler:
            company, customer = _find_customer_by_chat(db, token, chat_id)
            if not company:
                background_tasks.add_task(send_telegram_message, token, chat_id,
                    "❌ Kompaniya topilmadi.", {"remove_keyboard": True})
            else:
                await handler(db, token, chat_id, company, customer, background_tasks)
            return {"ok": True}

        # ── Noma'lum buyruq ───────────────────────────────────────
        if text.startswith("/"):
            help_msg = (
                "📋 <b>Mavjud buyruqlar:</b>\n\n"
                "/balans — 💰 Qarz va balans\n"
                "/karta — 🎫 Loyallik kartam\n"
                "/sotuvlar — 📦 Oxirgi xaridlar\n"
                "/yordam — ❓ Yordam\n"
                "/start — 🔄 Qayta ro'yxatdan o'tish"
            )
            background_tasks.add_task(send_telegram_message, token, chat_id, help_msg, _build_main_keyboard())
        else:
            background_tasks.add_task(
                send_telegram_message, token, chat_id,
                "⚙️ Menyu yangilandi. Quyidagi tugmalardan foydalaning:",
                _build_main_keyboard(),
            )

        return {"ok": True}
    except Exception as e:
        print("Webhook Error:", e)
        return {"ok": False}
