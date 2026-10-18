import html
import io
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Request, BackgroundTasks, Depends  # type: ignore
from sqlalchemy import func, literal_column  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
import httpx

from app.database import get_db  # type: ignore
from app.models.bot_session import BotSession  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.sale import Sale, PaymentType  # type: ignore
from app.services.shop_branch import default_branch_for_new_customer  # type: ignore

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

def _clean_name(text: str) -> str:
    """Mijoz ismini tozalaydi: `<` `>` belgilarini olib tashlaydi (XSS: chek/HTML ga tushmasin)."""
    t = (text or "").replace("<", "").replace(">", "")
    return " ".join(t.split())[:200]


def _h(value) -> str:
    """Telegram HTML parse_mode uchun matnni escape qiladi."""
    return html.escape(str(value if value is not None else ""), quote=False)


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


async def answer_callback_query(token: str, callback_query_id: str, text: str = None, show_alert: bool = False):
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        print("Telegram answerCallbackQuery xato:", e)


async def edit_telegram_message(token: str, chat_id: str, message_id: int, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    try:
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=payload)
    except Exception as e:
        print("Telegram editMessageText xato:", e)


async def send_loyalty_card(token: str, chat_id: str, customer_name: str, card_number: str, cashback_percent: float = 0, company=None):
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
        await send_telegram_message(token, chat_id, caption, _build_main_keyboard(company, chat_id))


# ── DB helpers ────────────────────────────────────────────────────────────────

def _find_customer_by_chat(db: Session, token: str, chat_id: str):
    company = db.query(Company).filter(Company.tg_bot_token == token).first()
    if not company:
        return None, None
    customer = db.query(Customer).filter(
        Customer.company_id == company.id,
        Customer.tg_chat_id == chat_id,
        Customer.is_active.is_(True),  # T0.26: arxivlangan mijoz botda ko'rinmaydi
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
    """13 xonali unique loyallik karta raqami (`29…`, app.utils.loyalty_card.generate_card_number)."""
    from app.utils.loyalty_card import generate_card_number
    existing = [
        r[0] for r in db.query(Customer.card_number).filter(
            Customer.company_id == company_id,
            Customer.card_number.isnot(None),
        ).all()
    ]
    return generate_card_number(existing)


# ── Klaviatura ────────────────────────────────────────────────────────────────

SHOP_BASE_URL = "https://savdo.e-code.uz/shop"


def _generate_shop_token(chat_id: str, bot_token: str) -> str:
    """Mijozga xos shaxsiy havola uchun imzo — Telegram initData'ga muqobil,
    chunki reply-keyboard web_app tugmasi ba'zi klientlarda initData'ni bo'sh qaytaradi."""
    import hmac
    import hashlib
    return hmac.new(bot_token.encode(), chat_id.encode(), hashlib.sha256).hexdigest()[:24]


def _build_main_keyboard(company=None, chat_id=None):
    dokon_button = {"text": "🏪 Dokon"}
    if company is not None and getattr(company, "id", None) and chat_id and getattr(company, "tg_bot_token", None):
        token = _generate_shop_token(str(chat_id), company.tg_bot_token)
        url = f"{SHOP_BASE_URL}?c={company.id}&u={chat_id}&t={token}"
        dokon_button = {"text": "🏪 Dokon", "web_app": {"url": url}}

    # Barcha funksiyalar (Balans, Kartam, Buyurtmalarim, Xaridlar tarixi)
    # endi Mini App ichida (hamburger menyu) — pastki klaviaturada faqat
    # Dokon qoladi. Eski matn buyruqlari (/balans, /karta, /yordam) hali
    # ham ishlaydi, faqat alohida tugma sifatida ko'rsatilmaydi.
    return {
        "keyboard": [
            [dokon_button],
            [{"text": "🎫 Mening kartam"}, {"text": "⚙️ Chek sozlamalari"}],
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
            _build_main_keyboard(company, chat_id))
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

    bg.add_task(send_telegram_message, token, chat_id, "\n".join(lines), _build_main_keyboard(company, chat_id))


async def _handle_sotuvlar(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    if not customer:
        bg.add_task(send_telegram_message, token, chat_id,
            "📦 Profil topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard(company, chat_id))
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

    bg.add_task(send_telegram_message, token, chat_id, msg, _build_main_keyboard(company, chat_id))


async def _handle_karta(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    if not customer:
        bg.add_task(send_telegram_message, token, chat_id,
            "🎫 Profil topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard(company, chat_id))
        return

    if not customer.card_number:
        card_number = _generate_card_number(db, company.id)
        customer.card_number = card_number
        db.commit()
    else:
        card_number = customer.card_number

    cashback = float(customer.cashback_percent or 0)
    bg.add_task(send_loyalty_card, token, chat_id, customer.name, card_number, cashback, company)


async def _handle_yordam(db, token, chat_id, company, customer, bg):
    msg = (
        "📋 <b>Botdan foydalanish yo'riqnomasi:</b>\n\n"
        "🏪 <b>Dokon</b> tugmasini bosing — mahsulotlar katalogi, "
        "buyurtma berish, balansingiz, loyallik kartangiz va xaridlar "
        "tarixi bir oynada ochiladi.\n\n"
        "<b>Buyruqlar:</b>\n"
        "/balans — Qarz holati\n"
        "/karta — Loyallik kartam\n"
        "/start — Qayta ro'yxatdan o'tish\n\n"
        "❓ Muammolar bo'lsa do'kon xodimlari bilan bog'laning."
    )
    bg.add_task(send_telegram_message, token, chat_id, msg, _build_main_keyboard(company, chat_id))


async def _handle_settings(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    if not customer:
        bg.add_task(send_telegram_message, token, chat_id,
            "⚙️ Profilingiz topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard(company, chat_id))
        return

    cur_fmt = getattr(customer, "receipt_format", None) or getattr(company, "receipt_format", "text") or "text"
    fmt_labels = {
        "image": "🖼 Rasm (A4 Nakladnoy)",
        "pdf": "📄 PDF hujjat (A4 Nakladnoy)",
        "text": "📝 Matn ko'rinishida",
    }
    cur_label = fmt_labels.get(cur_fmt, "📝 Matn ko'rinishida")

    msg = (
        f"⚙️ <b>Chek yuborish sozlamalari</b>\n\n"
        f"Do'kondan xarid qilganingizda chek sizga qaysi ko'rinishda yuborilishini tanlang:\n\n"
        f"📌 Hozirgi tanlov: <b>{cur_label}</b>"
    )
    kb = {
        "inline_keyboard": [
            [{"text": f"{'✅ ' if cur_fmt == 'image' else ''}🖼 Rasm (A4 Nakladnoy)", "callback_data": "set_fmt:image"}],
            [{"text": f"{'✅ ' if cur_fmt == 'pdf' else ''}📄 PDF hujjat (A4)", "callback_data": "set_fmt:pdf"}],
            [{"text": f"{'✅ ' if cur_fmt == 'text' else ''}📝 Matn ko'rinishida", "callback_data": "set_fmt:text"}],
        ]
    }
    bg.add_task(send_telegram_message, token, chat_id, msg, kb)


def _find_customer_by_phone_tail(db: Session, company_id: int, p_clean: str):
    """Oxirgi 9 raqam bo'yicha mijozni topadi (T3.8: bitta SQL so'rov, mijozlar Python'da aylanilmaydi).
    Faqat faol mijozlar (T0.26: arxivlangan mijoz qayta bog'lanmaydi)."""
    tail = p_clean[-9:]
    q = db.query(Customer).filter(
        Customer.company_id == company_id, Customer.phone.isnot(None),
        Customer.is_active.is_(True),
    )
    if db.get_bind().dialect.name == "postgresql":
        # literal_column: ifoda ix_customers_phone_tail funksional indeksi bilan aynan mos tushsin
        digits = func.regexp_replace(Customer.phone, literal_column(r"'\D'"), literal_column("''"), literal_column("'g'"))
        return q.filter(func.right(digits, literal_column("9")) == tail).order_by(Customer.id).first()
    # Postgres bo'lmagan muhit (test/SQLite): regexp_replace yo'q
    for c in q.order_by(Customer.id).all():
        c_clean = "".join(filter(str.isdigit, str(c.phone)))
        if len(c_clean) >= 9 and c_clean[-9:] == tail:
            return c
    return None


async def _handle_dokon(db: Session, token: str, chat_id: str, company, customer, bg: BackgroundTasks):
    """Dokon: katalog Mini App da (filial tanlovi, filial qoldig'i) — bu yerda faqat Mini App tugmasi.
    T3.13: ombor/qoldiq so'rovlari yo'q (avval barcha omborlar bo'yicha takroriy ro'yxat chiqardi)."""
    if not customer:
        bg.add_task(send_telegram_message, token, chat_id,
            "🏪 Profilingiz topilmadi. /start buyrug'i bilan ro'yxatdan o'ting.",
            _build_main_keyboard(company, chat_id))
        return

    msg = (
        "🏪 <b>Dokon</b>\n\n"
        "Mahsulotlar katalogi, filial tanlash va buyurtma berish uchun "
        "pastdagi <b>🏪 Dokon</b> tugmasini bosing."
    )
    bg.add_task(send_telegram_message, token, chat_id, msg, _build_main_keyboard(company, chat_id))


async def _handle_barcode_search(db: Session, token: str, chat_id: str, company, requester, bg: BackgroundTasks, barcode_input: str):
    """Foydalanuvchi noma'lum matn yuborganda, agar bu uning O'Z karta raqami
    bo'lsa, kartasini qayta yuboradi. Boshqa mijozlarni qidirish uchun EMAS —
    mijoz botida begona mijozning ismi/kartasini oshkor qilmaslik kerak
    (bu faqat kassir/admin panelida ruxsat etilgan amal)."""
    if not barcode_input or not barcode_input.strip():
        bg.add_task(send_telegram_message, token, chat_id,
            "❌ Buyruqni tushunmadim. Quyidagi tugmalardan birini tanlang.",
            _build_main_keyboard(company, chat_id))
        return

    if not requester or requester.card_number != barcode_input.strip():
        bg.add_task(send_telegram_message, token, chat_id,
            "❌ Buyruqni tushunmadim. Quyidagi tugmalardan birini tanlang.",
            _build_main_keyboard(company, chat_id))
        return

    customer = requester
    cashback = float(customer.cashback_percent or 0)
    welcome = (
        f"✅ <b>{customer.name}</b> topildi!\n\n"
        f"💳 Karta raqami: <code>{customer.card_number}</code>\n"
        f"🔄 Keshbek: <b>{customer.cashback_percent}%</b>"
    )
    bg.add_task(send_telegram_message, token, chat_id, welcome, _build_main_keyboard(company, chat_id))
    bg.add_task(send_loyalty_card, token, chat_id, customer.name, customer.card_number, cashback, company)


COMMAND_MAP = {
    "/balans": _handle_balans,
    "💰 balans": _handle_balans,
    "💰 qarz va to'lovlar": _handle_balans,
    "📦 oxirgi xaridlar": _handle_sotuvlar,
    "/sotuvlar": _handle_sotuvlar,
    "🎫 mening kartam": _handle_karta,
    "🎫 kartam": _handle_karta,
    "/karta": _handle_karta,
    "🏪 dokon": _handle_dokon,
    "/dokon": _handle_dokon,
    "⚙️ sozlamalar": _handle_settings,
    "⚙️ chek sozlamalari": _handle_settings,
    "/sozlamalar": _handle_settings,
    "/settings": _handle_settings,
    "/format": _handle_settings,
    "❓ yordam": _handle_yordam,
    "/yordam": _handle_yordam,
    "/help": _handle_yordam,
}


async def _process_phone_auth(db: Session, token: str, chat_id: str, phone: str, company, background_tasks: BackgroundTasks):
    """Telefon raqam (kontakt yoki matn) orqali mijozni aniqlaydi va kartasini beradi."""
    p_clean = "".join(filter(str.isdigit, str(phone)))
    if len(p_clean) < 9:
        background_tasks.add_task(
            send_telegram_message, token, chat_id,
            "⚠️ Telefon raqam noto'g'ri kiritildi. Iltimos, qaytadan yuboring:",
            _build_phone_keyboard(),
        )
        return

    found_customer = _find_customer_by_phone_tail(db, company.id, p_clean)
    if not found_customer:
        found_customer = db.query(Customer).filter(
            Customer.company_id == company.id,
            Customer.tg_chat_id == chat_id,
            Customer.is_active.is_(True),
        ).first()

    session = _get_session(db, chat_id, token)

    if found_customer:
        # Bazada bor bo'lgan mijoz — yangilab, kartasini yuboramiz
        found_customer.tg_chat_id = chat_id
        if not found_customer.card_number:
            found_customer.card_number = _generate_card_number(db, company.id)
        try:
            db.commit()
        except Exception as ex:
            db.rollback()
            print("Commit xato (found_customer):", ex)
        _delete_session(db, chat_id, token)

        cashback = float(found_customer.cashback_percent or 0)
        welcome = (
            f"✅ <b>Assalomu alaykum, {_h(found_customer.name)}!</b>\n\n"
            f"Profilingiz <b>{_h(company.name)}</b> loyallik tizimiga ulandi. 🎉\n\n"
            "Loyallik kartangiz:"
        )
        background_tasks.add_task(send_telegram_message, token, chat_id, welcome, _build_main_keyboard(company, chat_id))
        background_tasks.add_task(send_loyalty_card, token, chat_id,
            str(found_customer.name), str(found_customer.card_number or ""), cashback, company)
    elif session and session.temp_name and not session.temp_name.startswith("phone:"):
        # Yangi mijoz — avval ism kiritgan bo'lsa
        temp_name = _clean_name(session.temp_name)
        card_number = _generate_card_number(db, company.id)
        try:
            new_customer = Customer(
                name=temp_name,
                phone=phone,
                company_id=company.id,
                tg_chat_id=chat_id,
                card_number=card_number,
                branch_id=default_branch_for_new_customer(db, company),
            )
            db.add(new_customer)
            db.commit()
            db.refresh(new_customer)
            _delete_session(db, chat_id, token)
            cashback = float(new_customer.cashback_percent or 0)
            welcome = (
                f"✅ <b>Siz <u>{_h(company.name)}</u> do'konidan muvaffaqiyatli ro'yxatdan o'tdingiz!</b> 🎉\n\n"
                f"👤 Ism: <b>{_h(temp_name)}</b>\n"
                f"📞 Telefon: <b>{phone}</b>\n\n"
                f"🎫 Loyallik kartangiz tayyor! Har bir xaridingizda keshbek to'planadi."
            )
            background_tasks.add_task(send_telegram_message, token, chat_id, welcome, _build_main_keyboard(company, chat_id))
            background_tasks.add_task(send_loyalty_card, token, chat_id,
                temp_name, card_number, cashback, company)
        except Exception as ex:
            db.rollback()
            print("Yangi mijoz yaratish xato:", ex)
            _delete_session(db, chat_id, token)
            background_tasks.add_task(
                send_telegram_message, token, chat_id,
                f"✅ <b>Siz <u>{_h(company.name)}</u> do'konidan ro'yxatdan o'tdingiz!</b> 🎉\n\n"
                f"👤 Ism: <b>{_h(temp_name)}</b>\n"
                f"📞 Telefon: <b>{phone}</b>",
                _build_main_keyboard(company, chat_id),
            )
    else:
        # Yangi mijoz, lekin hali ismi kiritilmagan — ismini so'raymiz
        _upsert_session(db, chat_id, token, step="awaiting_name", temp_name=f"phone:{phone}")
        background_tasks.add_task(
            send_telegram_message, token, chat_id,
            f"👋 <b>{_h(company.name)}</b> loyallik tizimiga xush kelibsiz!\n\n"
            f"Siz tizimimizda yangisiz. Ro'yxatdan o'tish va kartangizni olish uchun <b>ismingizni</b> kiriting:",
            {"remove_keyboard": True},
        )


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

        # ── Callback query (inline tugmalar: masalan chek formati tanlovi) ──
        if "callback_query" in data:
            cb = data["callback_query"]
            cb_id = str(cb.get("id"))
            cb_data = str(cb.get("data", ""))
            cb_msg = cb.get("message", {})
            chat_id = str(cb_msg.get("chat", {}).get("id") or cb.get("from", {}).get("id"))
            msg_id = cb_msg.get("message_id")

            if cb_data.startswith("set_fmt:"):
                new_fmt = cb_data.split(":", 1)[1].strip().lower()
                if new_fmt in ("image", "pdf", "text"):
                    company, customer = _find_customer_by_chat(db, token, chat_id)
                    if customer:
                        customer.receipt_format = new_fmt
                        db.commit()

                        fmt_labels = {
                            "image": "🖼 Rasm (A4 Nakladnoy)",
                            "pdf": "📄 PDF hujjat (A4 Nakladnoy)",
                            "text": "📝 Matn ko'rinishida",
                        }
                        cur_label = fmt_labels.get(new_fmt, new_fmt)

                        background_tasks.add_task(
                            answer_callback_query, token, cb_id,
                            f"✅ Saqlandi: {cur_label}", False
                        )

                        updated_text = (
                            f"⚙️ <b>Chek yuborish sozlamalari</b>\n\n"
                            f"Do'kondan xarid qilganingizda chek sizga qaysi ko'rinishda yuborilishini tanlang:\n\n"
                            f"📌 Hozirgi tanlov: <b>{cur_label}</b>"
                        )
                        updated_kb = {
                            "inline_keyboard": [
                                [{"text": f"{'✅ ' if new_fmt == 'image' else ''}🖼 Rasm (A4 Nakladnoy)", "callback_data": "set_fmt:image"}],
                                [{"text": f"{'✅ ' if new_fmt == 'pdf' else ''}📄 PDF hujjat (A4)", "callback_data": "set_fmt:pdf"}],
                                [{"text": f"{'✅ ' if new_fmt == 'text' else ''}📝 Matn ko'rinishida", "callback_data": "set_fmt:text"}],
                            ]
                        }
                        if msg_id:
                            background_tasks.add_task(edit_telegram_message, token, chat_id, msg_id, updated_text, updated_kb)
                    else:
                        background_tasks.add_task(answer_callback_query, token, cb_id, "Mijoz topilmadi", True)
                return {"ok": True}

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
                # Allaqachon ro'yxatdan o'tgan — salom berib, kartasini tashab beramiz!
                _delete_session(db, chat_id, token)
                if not customer.card_number:
                    customer.card_number = _generate_card_number(db, company.id)
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                cashback = float(customer.cashback_percent or 0)
                reply = (
                    f"👋 <b>Assalomu alaykum, {_h(customer.name)}!</b>\n\n"
                    f"Siz <b>{_h(company.name)}</b> loyallik tizimiga ulangansiz.\n"
                    "Loyallik kartangiz quyida keltirilgan 👇"
                )
                background_tasks.add_task(send_telegram_message, token, chat_id, reply, _build_main_keyboard(company, chat_id))
                background_tasks.add_task(send_loyalty_card, token, chat_id, str(customer.name), str(customer.card_number or ""), cashback, company)
            else:
                # Yangi yoki hali chat bog'lanmagan foydalanuvchi — telefon so'raymiz
                _upsert_session(db, chat_id, token, step="awaiting_phone")
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    f"👋 <b>Assalomu alaykum!</b>\n\n"
                    f"<b>{_h(company.name)}</b> do'konining loyallik tizimiga xush kelibsiz!\n\n"
                    f"Profilingizni aniqlash va loyallik kartangizni olish uchun pastdagi <b>📞 Telefon raqamni yuborish</b> tugmasini bosing yoki telefon raqamingizni yozib yuboring (masalan: +998901234567):",
                    _build_phone_keyboard(),
                )
            return {"ok": True}

        # ── Joylashuv (lokatsiya) — mijoz manzilini biriktirish ──
        if "location" in message:
            company, customer = _find_customer_by_chat(db, token, chat_id)
            if not company:
                return {"ok": True}
            if not customer:
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    "ℹ️ Joylashuvni saqlash uchun avval ro'yxatdan o'ting: /start",
                )
                return {"ok": True}
            loc = message["location"]
            try:
                lat, lng = float(loc["latitude"]), float(loc["longitude"])
            except (KeyError, TypeError, ValueError):
                return {"ok": True}
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                return {"ok": True}
            customer.lat = round(lat, 7)
            customer.lng = round(lng, 7)
            customer.location_source = "telegram"
            db.commit()
            background_tasks.add_task(
                send_telegram_message, token, chat_id,
                "✅ Joylashuvingiz saqlandi. Buyurtmalaringiz shu manzilga yetkaziladi.",
                _build_main_keyboard(company, chat_id),
            )
            return {"ok": True}

        # ── Kontakt (telefon raqam) ───────────────────────────────
        if "contact" in message:
            contact = message["contact"]
            phone = contact.get("phone_number", "")
            company = db.query(Company).filter(Company.tg_bot_token == token).first()
            if not company:
                background_tasks.add_task(send_telegram_message, token, chat_id,
                    "❌ Kompaniya topilmadi.", {"remove_keyboard": True})
                return {"ok": True}
            await _process_phone_auth(db, token, chat_id, phone, company, background_tasks)
            return {"ok": True}

        # ── Matnda telefon raqam yozilgan bo'lsa (kamida 9 ta raqam) ──
        clean_text_digits = "".join(filter(str.isdigit, text))
        if len(clean_text_digits) >= 9 and not text.startswith("/"):
            company = db.query(Company).filter(Company.tg_bot_token == token).first()
            if company:
                await _process_phone_auth(db, token, chat_id, text, company, background_tasks)
                return {"ok": True}

        # ── Matn xabar — yangi mijoz ismini kiritishi holati ─────
        session = _get_session(db, chat_id, token)
        if session and session.step == "awaiting_name" and text and not text.startswith("/"):
            clean_name = _clean_name(text)
            if not clean_name:
                background_tasks.add_task(
                    send_telegram_message, token, chat_id,
                    "⚠️ Iltimos, ismingizni oddiy matn bilan kiriting.",
                )
                return {"ok": True}

            company = db.query(Company).filter(Company.tg_bot_token == token).first()
            if not company:
                return {"ok": True}

            if session.temp_name and session.temp_name.startswith("phone:"):
                saved_phone = session.temp_name.replace("phone:", "").strip()
                card_number = _generate_card_number(db, company.id)
                try:
                    new_customer = Customer(
                        name=clean_name,
                        phone=saved_phone,
                        company_id=company.id,
                        tg_chat_id=chat_id,
                        card_number=card_number,
                        branch_id=default_branch_for_new_customer(db, company),
                    )
                    db.add(new_customer)
                    db.commit()
                    db.refresh(new_customer)
                    _delete_session(db, chat_id, token)
                    cashback = float(new_customer.cashback_percent or 0)
                    welcome = (
                        f"✅ <b>Assalomu alaykum, {_h(clean_name)}!</b> 🎉\n\n"
                        f"Siz <u>{_h(company.name)}</u> tizimidan muvaffaqiyatli ro'yxatdan o'tdingiz!\n\n"
                        f"🎫 Loyallik kartangiz tayyor! Har bir xaridingizda keshbek to'planadi."
                    )
                    background_tasks.add_task(send_telegram_message, token, chat_id, welcome, _build_main_keyboard(company, chat_id))
                    background_tasks.add_task(send_loyalty_card, token, chat_id, clean_name, card_number, cashback, company)
                    return {"ok": True}
                except Exception as ex:
                    db.rollback()
                    print("Yangi mijoz yaratish xato:", ex)

            _upsert_session(db, chat_id, token, step="awaiting_phone", temp_name=clean_name)
            background_tasks.add_task(
                send_telegram_message, token, chat_id,
                f"✍️ Ism qabul qilindi: <b>{_h(clean_name)}</b>\n\n"
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
            elif any(k in txt for k in ("sozlama", "format", "settings", "chek sozlama")):
                handler = _handle_settings
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

        # ── Shtrix kod orqali qidirish ────────────────────────────
        company, customer = _find_customer_by_chat(db, token, chat_id)
        if company and customer and text and not text.startswith("/"):
            await _handle_barcode_search(db, token, chat_id, company, customer, background_tasks, text)
            return {"ok": True}

        # ── Noma'lum buyruq ───────────────────────────────────────
        if text.startswith("/"):
            help_msg = (
                "📋 <b>Mavjud buyruqlar:</b>\n\n"
                "/balans — 💰 Qarz va balans\n"
                "/karta — 🎫 Loyallik kartam\n"
                "/sozlamalar — ⚙️ Chek sozlamalari (Rasm / PDF / Matn)\n"
                "/sotuvlar — 📦 Oxirgi xaridlar\n"
                "/yordam — ❓ Yordam\n"
                "/start — 🔄 Qayta ro'yxatdan o'tish"
            )
            background_tasks.add_task(send_telegram_message, token, chat_id, help_msg, _build_main_keyboard(company, chat_id))
        else:
            background_tasks.add_task(
                send_telegram_message, token, chat_id,
                "⚙️ Menyu yangilandi. Quyidagi tugmalardan foydalaning:",
                _build_main_keyboard(company, chat_id),
            )

        return {"ok": True}
    except Exception as e:
        print("Webhook Error:", e)
        return {"ok": False}
