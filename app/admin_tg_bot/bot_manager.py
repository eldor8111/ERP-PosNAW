import asyncio
import re
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from aiogram import BaseMiddleware

from app.database import SessionLocal, engine
from app.admin_tg_bot.models import CompanyBot
from app.admin_tg_bot.recipients import BOT_MEMBER_ROLES, company_members, get_bot_member
from app.models.branch import Branch
from app.models.company import Company  # noqa: F401 — relationship uchun mapper registryga ro'yxatdan o'tkazish shart
from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany
from app.utils.telegram_text import esc
from app.models.sale import Sale
from app.utils.report_utils import (
    local_today, local_day_start, sales_summary, day_sales_summary, sale_doc_filter, sale_branch_filter,
)


class CompanyIdMiddleware(BaseMiddleware):
    """Har bir bot uchun company_id ni context orqali o'tkazadi."""

    def __init__(self, company_id: int):
        super().__init__()
        self.company_id = company_id

    async def __call__(self, handler, event, data):
        data["company_id"] = self.company_id
        return await handler(event, data)


class RegisterStates(StatesGroup):
    waiting_for_phone = State()


NOT_MEMBER_TEXT = (
    "❌ Siz bu korxona boti uchun ro'yxatdan o'tmagansiz.\n\n"
    "Ro'yxatdan o'tish uchun telefon raqamingizni yuboring 👇"
)


def normalize_phone(phone: str) -> str:
    """Solishtirish uchun raqamni oxirgi 9 ta raqamiga qisqartiradi (+998, bo'shliq, tire farqi muammo bo'lmasin)."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-9:] if len(digits) >= 9 else digits


def get_company_id_by_bot_token(bot_token: str) -> int | None:
    """Bot token orqali company_id ni olish."""
    db = SessionLocal()
    try:
        company_bot = db.query(CompanyBot).filter(
            CompanyBot.bot_token == bot_token,
            CompanyBot.bot_type == "admin"
        ).first()
        return company_bot.company_id if company_bot else None
    finally:
        db.close()


def fetch_member_by_tg_id(tg_id: str, company_id: int):
    """BOT KORXONASINING faol admin/direktor/menejeri: `(User, rol, filial_id)` (begona korxona xodimi — None)."""
    db = SessionLocal()
    try:
        return get_bot_member(db, tg_id, company_id)
    finally:
        db.close()


def list_active_branches(company_id: int) -> list:
    """Korxonaning faol filiallari: `[(id, nomi)]`."""
    db = SessionLocal()
    try:
        return [(b.id, b.name) for b in db.query(Branch.id, Branch.name).filter(
            Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
        ).order_by(Branch.id).all()]
    finally:
        db.close()


def _is_company_member(db, user: User, company_id: int) -> bool:
    """Foydalanuvchi (istalgan rol) shu korxonaning faol a'zosimi."""
    if user.status != UserStatus.active:
        return False
    if user.company_id == company_id:
        return True
    return db.query(UserCompany).filter(
        UserCompany.user_id == user.id,
        UserCompany.company_id == company_id,
        UserCompany.is_active == True,
    ).first() is not None


def link_admin_by_phone(phone: str, tg_id: str, tg_full_name: str | None, company_id: int):
    """Mavjud admin/direktor/menejerni telefon bo'yicha Telegramga bog'laydi. Yangi foydalanuvchi YARATILMAYDI.

    A'zolik `user_companies` (faol) yoki eski `users.company_id` orqali (ko'p korxonali xodim ham ulanadi).
    Korxonadan bir nechta rahbar ulana oladi (T3.16); begona odam (tizimda/korxonada yo'q raqam) — ulana olmaydi.
    tg_full_name mavjud ismni ALMASHTIRMAYDI: faqat users.name bo'sh bo'lsagina to'ldiriladi.
    """
    db = SessionLocal()
    try:
        normalized_phone = normalize_phone(phone)
        if len(normalized_phone) < 9:
            return None, "not_found"

        # Oxirgi 9 raqam bo'yicha ANIQ solishtirish (like faqat nomzodlarni toraytiradi)
        candidates = [
            u for u in db.query(User).filter(User.phone.like(f"%{normalized_phone}")).all()
            if normalize_phone(u.phone) == normalized_phone
        ]
        if not candidates:
            return None, "not_found"

        # Bot korxonasining faol admin/direktor/menejeri (user_companies yoki eski company_id orqali)
        cand_ids = {u.id for u in candidates}
        user = next(
            (u for u, role, _ in company_members(db, company_id, with_tg_only=False)
             if u.id in cand_ids and role in BOT_MEMBER_ROLES),
            None,
        )

        if not user:
            # Korxona a'zosi, lekin rahbar/menejer emas — "not_allowed"; aks holda — bu korxonada yo'q
            if any(_is_company_member(db, u, company_id) for u in candidates):
                return None, "not_allowed"
            return None, "not_found"

        if user.tg_chat_id and user.tg_chat_id != tg_id:
            return None, "already_linked"

        user.tg_chat_id = tg_id
        if tg_full_name and not (user.name or "").strip():
            user.name = tg_full_name
        db.commit()
        db.refresh(user)
        return user, "success"
    finally:
        db.close()


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _report_fields(summary: dict) -> dict:
    """Bot xabari uchun umumiy maydonlar (UZS; qaytarishlar alohida va ayirilgan)."""
    count = summary["count"]
    return {
        "sales_count": count,
        "total_amount": round(summary["gross"], 2),
        "returns_count": summary["returns_count"],
        "returns_amount": round(summary["returns"], 2),
        "net_amount": round(summary["net"], 2),
        "total_discount": round(summary["discount"], 2),
        "avg_check": round(summary["gross"] / count, 2) if count else 0,
    }


def _branch_name(db, company_id: int, branch_id) -> str | None:
    if not branch_id:
        return None
    return db.query(Branch.name).filter(Branch.id == branch_id, Branch.company_id == company_id).scalar()


def get_daily_sales_report(company_id: int, report_date: date = None, branch_id: int | None = None) -> dict:
    """Kunlik sotuv hisoboti (Hisobotlar bo'limi bilan bir xil qoida). `branch_id` — faqat shu filial (T1.9 snapshot)."""
    if report_date is None:
        report_date = local_today()

    db = SessionLocal()
    try:
        flt = sale_branch_filter(branch_id, db, company_id)
        summary = day_sales_summary(db, company_id, report_date, sale_filter=flt)
        return {
            "date": report_date.strftime("%d.%m.%Y"), "branch_id": branch_id,
            "branch_name": _branch_name(db, company_id, branch_id), **_report_fields(summary),
        }
    finally:
        db.close()


def get_monthly_sales_report(company_id: int, year: int = None, month: int = None,
                             branch_id: int | None = None) -> dict:
    """Oylik sotuv hisoboti. `branch_id` — faqat shu filial."""
    today = local_today()
    year = year or today.year
    month = month or today.month

    db = SessionLocal()
    try:
        first_day = date(year, month, 1)
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        start, end = local_day_start(first_day), local_day_start(next_month)
        flt = sale_branch_filter(branch_id, db, company_id)
        summary = sales_summary(db, company_id, start, end, sale_filter=flt)

        # Kunlik bo'yicha guruhlash (sotuv hujjatlari, UZS)
        from sqlalchemy import func
        day_col = func.date(Sale.created_at)
        daily_q = db.query(
            day_col.label("day"),
            func.count(Sale.id).label("count"),
            func.sum(Sale.total_amount).label("amount")
        ).filter(
            Sale.company_id == company_id,
            Sale.created_at >= start,
            Sale.created_at < end,
            sale_doc_filter(),
        )
        if flt is not None:
            daily_q = daily_q.filter(flt)
        daily_data = daily_q.group_by(day_col).order_by(day_col).all()

        daily_summary = [
            {
                "date": d.day.strftime("%d.%m.%Y") if hasattr(d.day, "strftime") else str(d.day),
                "count": d.count,
                "amount": float(d.amount or 0)
            }
            for d in daily_data
        ]

        return {
            "month": f"{year}-{month:02d}", "branch_id": branch_id,
            "branch_name": _branch_name(db, company_id, branch_id),
            **_report_fields(summary), "daily_data": daily_summary,
        }
    finally:
        db.close()


def _returns_lines(report: dict) -> str:
    """Qaytarish bo'lsa — qaytarish va sof tushum qatorlari."""
    if not report.get("returns_count"):
        return ""
    return (
        f"↩️ Qaytarishlar: <b>{report['returns_count']} ta, {report['returns_amount']:,} UZS</b>\n"
        f"✅ Sof tushum: <b>{report['net_amount']:,} UZS</b>\n"
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Kunlik hisobot")],
            [KeyboardButton(text="📈 Oylik hisobot")],
        ],
        resize_keyboard=True,
    )


async def send_welcome(message: Message, user: User | None, greeting: str = "", company_id: int | None = None,
                       role: UserRole | None = None) -> None:
    if not user:
        await message.answer(
            f"{greeting}👋 Assalomu alaykum!\n\n"
            f"🏢 <b>E-CODE Admin</b> botiga xush kelibsiz!\n"
            f"👤 Ism: <b>—</b>\n"
            f"🏬 Kompaniya: <b>—</b>",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Fetch company name (bot korxonasi; ko'p korxonali direktor uchun users.company_id boshqa bo'lishi mumkin)
    company_name = "—"
    shown_company_id = company_id or user.company_id
    if shown_company_id:
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == shown_company_id).first()
            if company:
                company_name = company.name
        finally:
            db.close()

    # Role mapping
    role_display = {
        UserRole.director: "Direktor",
        UserRole.admin: "Admin",
        UserRole.manager: "Menejer",
        UserRole.cashier: "Kassir",
        UserRole.warehouse: "Omborchi",
        UserRole.accountant: "Buxgalter",
        UserRole.super_admin: "Super Admin",
    }.get(role or user.role, str(role or user.role))

    await message.answer(
        f"{greeting}👋 Assalomu alaykum!\n\n"
        f"🏢 <b>E-CODE Admin</b> botiga xush kelibsiz!\n"
        f"👤 Ism: <b>{user.name}</b>\n"
        f"🏬 Kompaniya: <b>{company_name}</b>\n"
        f"🔑 Rol: <b>{role_display}</b>",
        reply_markup=main_menu_keyboard(),
    )


async def _ask_registration(message: Message, state: FSMContext) -> None:
    """Bot korxonasining a'zosi bo'lmagan odamga — hisobotsiz, ro'yxatdan o'tish taklifi."""
    await state.set_state(RegisterStates.waiting_for_phone)
    await message.answer(NOT_MEMBER_TEXT, reply_markup=contact_keyboard())


async def cmd_start(message: Message, state: FSMContext, company_id: int) -> None:
    tg_id = str(message.from_user.id)
    member = await asyncio.to_thread(fetch_member_by_tg_id, tg_id, company_id)

    if member:
        await send_welcome(message, member[0], company_id=company_id, role=member[1])
        await state.clear()
        return

    await _ask_registration(message, state)


def _branch_line(report: dict, all_branches: bool) -> str:
    """Hisobot sarlavhasidagi filial qatori (filial tanlangan yoki "Barcha filiallar")."""
    if report.get("branch_name"):
        return f"🏬 Filial: <b>{esc(report['branch_name'])}</b>\n"
    return "🏬 <b>Barcha filiallar</b>\n" if all_branches else ""


def _daily_report_text(report: dict, all_branches: bool = False) -> str:
    return (
        f"📊 <b>Kunlik Sotuv Hisoboti</b>\n\n"
        f"{_branch_line(report, all_branches)}"
        f"📅 Sana: <b>{report['date']}</b>\n"
        f"🛒 Sotuvlar soni: <b>{report['sales_count']}</b>\n"
        f"💰 Jami summa: <b>{report['total_amount']:,} UZS</b>\n"
        f"{_returns_lines(report)}"
        f"🎁 Chegirma: <b>{report['total_discount']:,} UZS</b>\n"
        f"📊 O'rtacha chek: <b>{report['avg_check']:,} UZS</b>"
    )


def _monthly_report_text(report: dict, all_branches: bool = False) -> str:
    daily_text = "\n".join(
        f"  {d['date']}: {d['count']} ta, {d['amount']:,} UZS"
        for d in report['daily_data'][-7:]  # Oxirgi 7 kun
    )
    return (
        f"📈 <b>Oylik Sotuv Hisoboti</b>\n\n"
        f"{_branch_line(report, all_branches)}"
        f"📅 Oy: <b>{report['month']}</b>\n"
        f"🛒 Sotuvlar soni: <b>{report['sales_count']}</b>\n"
        f"💰 Jami summa: <b>{report['total_amount']:,} UZS</b>\n"
        f"{_returns_lines(report)}"
        f"🎁 Chegirma: <b>{report['total_discount']:,} UZS</b>\n"
        f"📊 O'rtacha chek: <b>{report['avg_check']:,} UZS</b>\n\n"
        f"📊 <b>Oxirgi 7 kun:</b>\n{daily_text if daily_text else ''}"
    )


def _build_report(kind: str, company_id: int, branch_id: int | None) -> dict:
    """Hisobot ma'lumoti. branch_id berilmasa filial argumenti uzatilmaydi (butun korxona)."""
    fn = get_daily_sales_report if kind == "daily" else get_monthly_sales_report
    return fn(company_id, branch_id=branch_id) if branch_id else fn(company_id)


async def _send_report(message: Message, kind: str, company_id: int, branch_id: int | None,
                       all_branches: bool = False) -> None:
    report = await asyncio.to_thread(_build_report, kind, company_id, branch_id)
    text = _daily_report_text(report, all_branches) if kind == "daily" else _monthly_report_text(report, all_branches)
    await message.answer(text, reply_markup=main_menu_keyboard())


def branch_picker_keyboard(kind: str, branches: list) -> InlineKeyboardMarkup:
    """Filial tanlash: "Barcha filiallar" + har bir filial (callback `rep:<daily|monthly>:<id|all>`)."""
    rows = [[InlineKeyboardButton(text="🏢 Barcha filiallar", callback_data=f"rep:{kind}:all")]]
    rows += [[InlineKeyboardButton(text=f"🏬 {name}", callback_data=f"rep:{kind}:{bid}")] for bid, name in branches]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _handle_report_request(message: Message, state: FSMContext, company_id: int, kind: str) -> None:
    """Kunlik/oylik hisobot tugmasi: menejer — faqat o'z filiali; admin/direktor — ≥2 filial bo'lsa filial tanlaydi."""
    tg_id = str(message.from_user.id)
    member = await asyncio.to_thread(fetch_member_by_tg_id, tg_id, company_id)

    if not member:
        await _ask_registration(message, state)
        return

    _, role, branch_id = member
    if role == UserRole.manager:
        if not branch_id:
            await message.answer("❌ Sizga filial biriktirilmagan. Administratorga murojaat qiling.")
            return
        await _send_report(message, kind, company_id, branch_id)
        return

    if role not in (UserRole.director, UserRole.admin):
        await message.answer("❌ Kechirasiz, hisobotlarni faqat rahbarlar ko'ra oladi.")
        return

    branches = await asyncio.to_thread(list_active_branches, company_id)
    if len(branches) >= 2:
        await message.answer("🏬 Qaysi filial hisoboti kerak?", reply_markup=branch_picker_keyboard(kind, branches))
        return
    await _send_report(message, kind, company_id, None)


async def handle_daily_report(message: Message, state: FSMContext, company_id: int) -> None:
    """Kunlik hisobot tugmasi"""
    await _handle_report_request(message, state, company_id, "daily")


async def handle_monthly_report(message: Message, state: FSMContext, company_id: int) -> None:
    """Oylik hisobot tugmasi"""
    await _handle_report_request(message, state, company_id, "monthly")


async def handle_report_callback(callback: CallbackQuery, company_id: int) -> None:
    """Filial tanlash tugmasi (`rep:<daily|monthly>:<id|all>`): ruxsat QAYTA tekshiriladi (soxta callback)."""
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[0] != "rep" or parts[1] not in ("daily", "monthly"):
        await callback.answer()
        return
    kind, sel = parts[1], parts[2]
    member = await asyncio.to_thread(fetch_member_by_tg_id, str(callback.from_user.id), company_id)
    if not member:
        await callback.answer("❌ Siz bu korxona boti uchun ro'yxatdan o'tmagansiz.", show_alert=True)
        return

    _, role, own_branch = member
    branch_id = None
    if role == UserRole.manager:
        # Menejer faqat o'z filiali
        if not own_branch or sel != str(own_branch):
            await callback.answer("❌ Siz faqat o'z filialingiz hisobotini ko'ra olasiz.", show_alert=True)
            return
        branch_id = own_branch
    elif role in (UserRole.director, UserRole.admin):
        if sel != "all":
            branches = await asyncio.to_thread(list_active_branches, company_id)
            if not sel.isdigit() or int(sel) not in {b[0] for b in branches}:
                await callback.answer("❌ Filial topilmadi.", show_alert=True)
                return
            branch_id = int(sel)
    else:
        await callback.answer("❌ Hisobotlarni faqat rahbarlar ko'ra oladi.", show_alert=True)
        return

    await callback.answer()
    if callback.message is not None:
        await _send_report(callback.message, kind, company_id, branch_id, all_branches=branch_id is None)


def _decide_approval_sync(request_id: int, user_id: int, company_id: int, approve: bool, role, branch_id) -> tuple:
    """T4.6 (sinxron, `asyncio.to_thread` ichida): so'rovni `approval_service.decide` orqali hal qiladi.
    Qaytaradi `(ok, matn)`. Korxona BOT korxonasi bilan cheklanadi (begona korxona so'rovi — 404)."""
    from fastapi import HTTPException
    from app.services import approval_service

    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return False, "❌ Foydalanuvchi topilmadi."
        approval_service.decide(
            db, request_id, user, approve, None, role=role,
            branch_ids={branch_id} if branch_id else set(), company_id=company_id,
        )
        return True, "✅ Tasdiqlandi" if approve else "❌ Rad etildi"
    except HTTPException as e:
        db.rollback()
        return False, f"⚠️ {e.detail}"
    except Exception as e:
        db.rollback()
        print(f"[Admin Bot] Tasdiq xatosi (so'rov {request_id}): {e}")
        return False, "⚠️ Xatolik yuz berdi. Keyinroq urinib ko'ring."
    finally:
        db.close()


async def handle_approval_callback(callback: CallbackQuery, company_id: int) -> None:
    """Tasdiq tugmalari (`appr:ok:<id>` / `appr:no:<id>`): foydalanuvchi BOT korxonasining admin/direktor/menejeri
    bo'lishi shart (soxta callback va begona korxona rad etiladi); menejer faqat o'z filiali so'rovini hal qiladi."""
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[0] != "appr" or parts[1] not in ("ok", "no") or not parts[2].isdigit():
        await callback.answer()
        return
    member = await asyncio.to_thread(fetch_member_by_tg_id, str(callback.from_user.id), company_id)
    if not member:
        await callback.answer("❌ Siz bu korxona boti uchun ro'yxatdan o'tmagansiz.", show_alert=True)
        return
    user, role, own_branch = member
    ok, text = await asyncio.to_thread(
        _decide_approval_sync, int(parts[2]), user.id, company_id, parts[1] == "ok", role, own_branch,
    )
    await callback.answer(text, show_alert=True)
    if ok and callback.message is not None:
        # Qaror qabul qilindi: tugmalarni olib tashlab, natijani xabarga yozamiz
        try:
            await callback.message.edit_text(f"{callback.message.html_text}\n\n{text} — {esc(user.name)}", reply_markup=None)
        except Exception:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass


async def process_contact(message: Message, state: FSMContext, company_id: int) -> None:
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("⚠️ Iltimos, faqat o'zingizning raqamingizni yuboring.")
        return

    tg_id = str(message.from_user.id)
    admin, status = await asyncio.to_thread(
        link_admin_by_phone, contact.phone_number, tg_id, message.from_user.full_name, company_id
    )

    if status == "not_allowed":
        await message.answer(
            "❌ Kechirasiz, ushbu botdan faqat kompaniya admini, direktori yoki filial menejeri foydalana oladi.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    if status == "not_found":
        # Botdan yangi foydalanuvchi yaratilmaydi — rahbar faqat veb-paneldan qo'shiladi
        await message.answer(
            "❌ Bu raqam shu korxona rahbarlari ro'yxatida yo'q.\n"
            "Administrator sizni veb-paneldan (Xodimlar) qo'shishi kerak.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    if status == "already_linked":
        await message.answer(
            "⚠️ Bu raqam allaqachon boshqa Telegram akkauntga bog'langan.\n"
            "Administratorga murojaat qiling.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    await state.clear()
    member = await asyncio.to_thread(fetch_member_by_tg_id, tg_id, company_id)
    await send_welcome(message, admin, greeting="✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n", company_id=company_id,
                       role=member[1] if member else None)


async def waiting_for_phone_fallback(message: Message) -> None:
    await message.answer(
        "Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring 👇",
        reply_markup=contact_keyboard(),
    )


def create_tables():
    """Jadvallarni yaratadi agar mavjud bo'lmasa."""
    from app.admin_tg_bot.models import CompanyBot
    CompanyBot.__table__.create(bind=engine, checkfirst=True)


def create_dispatcher() -> Dispatcher:
    """Yangi dispatcher yaratadi."""
    return Dispatcher(storage=MemoryStorage())


def register_handlers(dp: Dispatcher, company_id: int):
    """Dispatcher ga handlerlarni ro'yxatdan o'tkazadi."""
    dp.message(CommandStart())(cmd_start)
    dp.message(F.text == "📊 Kunlik hisobot")(handle_daily_report)
    dp.message(F.text == "📈 Oylik hisobot")(handle_monthly_report)

    async def _report_callback(callback: CallbackQuery) -> None:
        # callback_query uchun middleware yo'q — company_id yopilma (closure) orqali uzatiladi
        await handle_report_callback(callback, company_id)

    dp.callback_query(F.data.startswith("rep:"))(_report_callback)

    async def _approval_callback(callback: CallbackQuery) -> None:
        # T4.6: tasdiq tugmalari — company_id yopilma orqali (callback_query uchun middleware yo'q)
        await handle_approval_callback(callback, company_id)

    dp.callback_query(F.data.startswith("appr:"))(_approval_callback)
    dp.message(RegisterStates.waiting_for_phone, F.contact)(process_contact)
    dp.message(RegisterStates.waiting_for_phone)(waiting_for_phone_fallback)


async def start_bot(bot_token: str, company_id: int):
    """Bitta botni ishga tushiradi. Bekor qilinganda (cancel) Bot sessiyasi yopiladi."""
    dp = create_dispatcher()
    dp.message.middleware(CompanyIdMiddleware(company_id))
    register_handlers(dp, company_id)

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        timeout=30.0
    )
    print(f"[Admin Bot] Bot started with token: {bot_token[:20]}... for company {company_id}")
    try:
        # handle_signals=False: SIGINT/SIGTERM ni gunicorn/uvicorn boshqaradi (task cancel qilinadi)
        await dp.start_polling(bot, handle_signals=False)
    finally:
        await bot.session.close()


# ── Reconcile: bazadagi faol botlar bilan ishlayotgan polling'larni solishtirish (T3.15) ──

BOT_RECONCILE_INTERVAL = 30   # soniya: yangi/o'zgargan/o'chirilgan botlar shu oraliqda ilib olinadi
BOT_RETRY_MAX_WAIT = 600      # yaroqsiz token qayta urinish orasidagi eng uzun kutish (soniya)


def diff_bots(running: dict, desired: dict) -> tuple:
    """Toza funksiya: ishlayotgan va kerakli botlar farqi.

    running: {company_id: (token, task)}; desired: {company_id: token}.
    Qaytaradi (stop, start): stop — to'xtatiladigan company_id lar (token o'zgargan, o'chirilgan/nofaol
    yoki task.done()); start — ishga tushiriladigan (company_id, token) juftliklari (yangi, token
    almashgan yoki task to'xtab qolgan). Tartib company_id bo'yicha."""
    stop, start = [], []
    for cid in sorted(running):
        token, task = running[cid]
        if cid not in desired or desired[cid] != token or task.done():
            stop.append(cid)
    stopped = set(stop)
    for cid in sorted(desired):
        if cid not in running or cid in stopped:
            start.append((cid, desired[cid]))
    return stop, start


def _load_desired_bots() -> dict:
    """Faol admin botlar: {company_id: bot_token}."""
    db = SessionLocal()
    try:
        return {
            b.company_id: b.bot_token
            for b in db.query(CompanyBot).filter(
                CompanyBot.bot_type == "admin",
                CompanyBot.is_active == True  # noqa: E712
            ).all()
            if b.bot_token
        }
    finally:
        db.close()


async def _stop_bot_tasks(tasks: list) -> None:
    """Task'larni bekor qilib, tugashini kutadi (yangi polling eskisi to'xtagandan keyingina boshlanadi —
    'Conflict: terminated by other getUpdates request' bo'lmasligi uchun)."""
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    """Admin botlarni bazadan o'qib, har BOT_RECONCILE_INTERVAL soniyada solishtirib turadi:
    yangi bot — ishga tushadi, token almashgan — qayta ishga tushadi, o'chirilgan/nofaol — to'xtaydi."""
    create_tables()

    running: dict = {}   # company_id -> (token, task)
    failures: dict = {}  # company_id -> (token, urinishlar soni, keyingi urinish vaqti, oxirgi xato)
    loop = asyncio.get_running_loop()
    try:
        while True:
            try:
                # Sessiya darhol yopiladi — polling davomida bazada "idle in transaction" bo'lmaydi
                desired = await asyncio.to_thread(_load_desired_bots)
            except Exception as e:
                print(f"[Admin Bot] Botlar ro'yxatini o'qib bo'lmadi: {e}")
                desired = None

            if desired is not None:
                now = loop.time()
                # Yiqilgan task'lar: sababini bir marta loglaymiz va backoff bilan qayta uramiz
                for cid, (token, task) in list(running.items()):
                    if not task.done():
                        failures.pop(cid, None)  # barqaror ishlayapti
                        continue
                    err = "tugadi" if task.cancelled() else (repr(task.exception()) if task.exception() else "tugadi")
                    prev = failures.get(cid)
                    n = prev[1] + 1 if prev and prev[0] == token else 1
                    if not prev or prev[0] != token or prev[3] != err:
                        print(f"[Admin Bot] company {cid}: polling to'xtadi ({err})")
                    failures[cid] = (token, n, now + min(BOT_RECONCILE_INTERVAL * 2 ** (n - 1), BOT_RETRY_MAX_WAIT), err)
                for cid in list(failures):
                    if desired.get(cid) != failures[cid][0]:
                        failures.pop(cid)  # token o'zgargan yoki bot olib tashlangan — yangi urinish
                # Backoff muddati o'tmaguncha yiqilgan tokenni qayta ishga tushirmaymiz
                wanted = {
                    cid: tok for cid, tok in desired.items()
                    if not (cid in failures and failures[cid][0] == tok and failures[cid][2] > now)
                }
                stop, start = diff_bots(running, wanted)
                if stop:
                    await _stop_bot_tasks([running[cid][1] for cid in stop])
                    for cid in stop:
                        running.pop(cid, None)
                        print(f"[Admin Bot] company {cid}: polling to'xtatildi")
                for cid, token in start:
                    running[cid] = (token, asyncio.create_task(start_bot(token, cid)))
                if start:
                    print(f"[Admin Bot] {len(start)} ta admin bot ishga tushirilmoqda (jami {len(running)} ta)")
            await asyncio.sleep(BOT_RECONCILE_INTERVAL)
    finally:
        await _stop_bot_tasks([t for _, t in running.values()])


if __name__ == "__main__":
    asyncio.run(main())
