import asyncio
import re
from datetime import date, datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram import BaseMiddleware

from app.database import SessionLocal, engine
from app.admin_tg_bot.models import CompanyBot
from app.models.company import Company  # noqa: F401 — relationship uchun mapper registryga ro'yxatdan o'tkazish shart
from app.models.user import User, UserRole
from app.models.sale import Sale, SaleStatus
from app.core.security import hash_password


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
    waiting_for_name = State()
    waiting_for_password = State()


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


def fetch_admin_by_tg_id(tg_id: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.tg_chat_id == tg_id).first()
        return user
    finally:
        db.close()


def link_admin_by_phone(phone: str, tg_id: str, tg_full_name: str | None, company_id: int):
    db = SessionLocal()
    try:
        normalized_phone = normalize_phone(phone)
        user = db.query(User).filter(User.phone.like(f"%{normalized_phone}"), User.company_id == company_id).first()

        if not user:
            return None, "not_found"

        if user.role != UserRole.director:
            return None, "not_allowed"

        if user.tg_chat_id and user.tg_chat_id != tg_id:
            return None, "already_linked"

        user.tg_chat_id = tg_id
        if tg_full_name:
            user.name = tg_full_name
        db.commit()
        db.refresh(user)
        return user, "success"
    finally:
        db.close()


def create_new_user(phone: str, tg_id: str, name: str, company_id: int, password: str):
    db = SessionLocal()
    try:
        # Check if phone already exists
        normalized_phone = normalize_phone(phone)
        existing_user = db.query(User).filter(User.phone.like(f"%{normalized_phone}")).first()
        if existing_user:
            return None, "phone_exists"

        # Check if company exists
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return None, "company_not_found"

        # Check if company already has a director
        existing_director = db.query(User).filter(User.company_id == company_id, User.role == UserRole.director).first()
        if existing_director:
            return None, "director_exists"

        # Create new user with director role
        user = User(
            name=name,
            phone=phone,
            hashed_password=hash_password(password),
            role=UserRole.director,
            company_id=company.id,
            tg_chat_id=tg_id,
            status="active"
        )
        db.add(user)
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


def get_daily_sales_report(company_id: int, report_date: date = None) -> dict:
    """Kunlik sotuv hisoboti"""
    if report_date is None:
        report_date = date.today()

    db = SessionLocal()
    try:
        start = datetime.combine(report_date, datetime.min.time())
        end = datetime.combine(report_date + timedelta(days=1), datetime.min.time())

        sales = db.query(Sale).filter(
            Sale.company_id == company_id,
            Sale.created_at >= start,
            Sale.created_at < end,
            Sale.status == SaleStatus.completed
        ).all()

        total_amount = sum(float(s.total_amount) for s in sales)
        total_discount = sum(float(s.discount_amount) for s in sales)
        sales_count = len(sales)
        avg_check = total_amount / sales_count if sales_count > 0 else 0

        return {
            "date": report_date.strftime("%d.%m.%Y"),
            "sales_count": sales_count,
            "total_amount": round(total_amount, 2),
            "total_discount": round(total_discount, 2),
            "avg_check": round(avg_check, 2),
        }
    finally:
        db.close()


def get_monthly_sales_report(company_id: int, year: int = None, month: int = None) -> dict:
    """Oylik sotuv hisoboti"""
    if year is None:
        year = date.today().year
    if month is None:
        month = date.today().month

    db = SessionLocal()
    try:
        start = datetime(year, month, 1)
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)

        sales = db.query(Sale).filter(
            Sale.company_id == company_id,
            Sale.created_at >= start,
            Sale.created_at < end,
            Sale.status == SaleStatus.completed
        ).all()

        total_amount = sum(float(s.total_amount) for s in sales)
        total_discount = sum(float(s.discount_amount) for s in sales)
        sales_count = len(sales)
        avg_check = total_amount / sales_count if sales_count > 0 else 0

        # Kunlik bo'yicha guruhlash
        from sqlalchemy import func
        daily_data = db.query(
            func.date(Sale.created_at).label("day"),
            func.count(Sale.id).label("count"),
            func.sum(Sale.total_amount).label("amount")
        ).filter(
            Sale.company_id == company_id,
            Sale.created_at >= start,
            Sale.created_at < end,
            Sale.status == SaleStatus.completed
        ).group_by(func.date(Sale.created_at)).all()

        daily_summary = [
            {
                "date": d.day.strftime("%d.%m.%Y"),
                "count": d.count,
                "amount": float(d.amount or 0)
            }
            for d in daily_data
        ]

        return {
            "month": f"{year}-{month:02d}",
            "sales_count": sales_count,
            "total_amount": round(total_amount, 2),
            "total_discount": round(total_discount, 2),
            "avg_check": round(avg_check, 2),
            "daily_data": daily_summary
        }
    finally:
        db.close()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Kunlik hisobot")],
            [KeyboardButton(text="📈 Oylik hisobot")],
        ],
        resize_keyboard=True,
    )


async def send_welcome(message: Message, user: User | None, greeting: str = "") -> None:
    if not user:
        await message.answer(
            f"{greeting}👋 Assalomu alaykum!\n\n"
            f"🏢 <b>E-CODE Admin</b> botiga xush kelibsiz!\n"
            f"👤 Ism: <b>—</b>\n"
            f"🏬 Kompaniya: <b>—</b>",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Fetch company name
    company_name = "—"
    if user.company_id:
        db = SessionLocal()
        try:
            company = db.query(Company).filter(Company.id == user.company_id).first()
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
    }.get(user.role, str(user.role))

    await message.answer(
        f"{greeting}👋 Assalomu alaykum!\n\n"
        f"🏢 <b>E-CODE Admin</b> botiga xush kelibsiz!\n"
        f"👤 Ism: <b>{user.name}</b>\n"
        f"🏬 Kompaniya: <b>{company_name}</b>\n"
        f"🔑 Rol: <b>{role_display}</b>",
        reply_markup=main_menu_keyboard(),
    )


async def cmd_start(message: Message, state: FSMContext, company_id: int) -> None:
    tg_id = str(message.from_user.id)
    admin = await asyncio.to_thread(fetch_admin_by_tg_id, tg_id)

    if admin:
        await send_welcome(message, admin)
        await state.clear()
        return

    await state.set_state(RegisterStates.waiting_for_phone)
    await message.answer(
        "❌ Siz hali ro'yxatdan o'tmagansiz.\n\n"
        "Ro'yxatdan o'tish uchun telefon raqamingizni yuboring 👇",
        reply_markup=contact_keyboard(),
    )


async def handle_daily_report(message: Message, company_id: int) -> None:
    """Kunlik hisobot tugmasi"""
    tg_id = str(message.from_user.id)
    admin = await asyncio.to_thread(fetch_admin_by_tg_id, tg_id)

    if not admin:
        await message.answer("❌ Iltimos, avval ro'yxatdan o'ting.")
        return

    if admin.role != UserRole.director:
        await message.answer("❌ Kechirasiz, hisobotlarni faqat direktorlar ko'ra oladi.")
        return

    report = await asyncio.to_thread(get_daily_sales_report, company_id)

    await message.answer(
        f"📊 <b>Kunlik Sotuv Hisoboti</b>\n\n"
        f"📅 Sana: <b>{report['date']}</b>\n"
        f"🛒 Sotuvlar soni: <b>{report['sales_count']}</b>\n"
        f"💰 Jami summa: <b>{report['total_amount']:,} UZS</b>\n"
        f"🎁 Chegirma: <b>{report['total_discount']:,} UZS</b>\n"
        f"📊 O'rtacha chek: <b>{report['avg_check']:,} UZS</b>",
        reply_markup=main_menu_keyboard(),
    )


async def handle_monthly_report(message: Message, company_id: int) -> None:
    """Oylik hisobot tugmasi"""
    tg_id = str(message.from_user.id)
    admin = await asyncio.to_thread(fetch_admin_by_tg_id, tg_id)

    if not admin:
        await message.answer("❌ Iltimos, avval ro'yxatdan o'ting.")
        return

    if admin.role != UserRole.director:
        await message.answer("❌ Kechirasiz, hisobotlarni faqat direktorlar ko'ra oladi.")
        return

    report = await asyncio.to_thread(get_monthly_sales_report, company_id)

    daily_text = "\n".join(
        f"  {d['date']}: {d['count']} ta, {d['amount']:,} UZS"
        for d in report['daily_data'][-7:]  # Oxirgi 7 kun
    )

    await message.answer(
        f"📈 <b>Oylik Sotuv Hisoboti</b>\n\n"
        f"📅 Oy: <b>{report['month']}</b>\n"
        f"🛒 Sotuvlar soni: <b>{report['sales_count']}</b>\n"
        f"💰 Jami summa: <b>{report['total_amount']:,} UZS</b>\n"
        f"🎁 Chegirma: <b>{report['total_discount']:,} UZS</b>\n"
        f"📊 O'rtacha chek: <b>{report['avg_check']:,} UZS</b>\n\n"
        f"📊 <b>Oxirgi 7 kun:</b>\n{daily_text if daily_text else ''}",
        reply_markup=main_menu_keyboard(),
    )


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
            "❌ Kechirasiz, ushbu botdan faqat kompaniya direktori foydalana oladi.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    if status == "not_found":
        # Check if director already exists before starting new registration
        db = SessionLocal()
        try:
            director_exists = db.query(User).filter(User.company_id == company_id,
                                                    User.role == UserRole.director).first()
        finally:
            db.close()

        if director_exists:
            await message.answer(
                "❌ Kechirasiz, ushbu botdan faqat kompaniya direktori foydalana oladi va kompaniyada allaqachon direktor ro'yxatdan o'tgan.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await state.clear()
            return

        # Start new registration process
        await state.update_data(phone=contact.phone_number)
        await state.set_state(RegisterStates.waiting_for_name)
        await message.answer(
            "❌ Bu raqam tizimda topilmadi.\n\n"
            "Yangi foydalanuvchi sifatida ro'yxatdan o'tish uchun ma'lumotlaringizni kiriting.\n\n"
            "👤 Ismingizni kiriting:",
            reply_markup=ReplyKeyboardRemove(),
        )
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
    await send_welcome(message, admin, greeting="✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n")


async def waiting_for_phone_fallback(message: Message) -> None:
    await message.answer(
        "Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring 👇",
        reply_markup=contact_keyboard(),
    )


async def process_name(message: Message, state: FSMContext, company_id: int) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Iltimos, to'g'ri ism kiriting.")
        return

    await state.update_data(name=name)
    await state.set_state(RegisterStates.waiting_for_password)
    await message.answer("🔐 Parolni kiriting (kamida 6 ta belgi):")


async def process_password(message: Message, state: FSMContext, company_id: int) -> None:
    password = message.text.strip()
    if len(password) < 6:
        await message.answer("⚠️ Parol kamida 6 ta belgidan iborat bo'lishi kerak.")
        return

    data = await state.get_data()
    tg_id = str(message.from_user.id)

    user, status = await asyncio.to_thread(
        create_new_user,
        data["phone"],
        tg_id,
        data["name"],
        company_id,
        password
    )

    if status == "phone_exists":
        await message.answer(
            "❌ Bu telefon raqami allaqachon ro'yxatdan o'tgan.\n"
            "Administrator bilan bog'laning.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    if status == "company_not_found":
        await message.answer(
            "❌ Kompaniya topilmadi.\n"
            "Administrator bilan bog'laning.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    if status == "director_exists":
        await message.answer(
            "❌ Kompaniyada allaqachon direktor mavjud. Siz yangi direktor bo'lib ro'yxatdan o'ta olmaysiz.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()
        return

    await state.clear()
    await send_welcome(message, user, greeting="✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n")


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
    dp.message(RegisterStates.waiting_for_phone, F.contact)(process_contact)
    dp.message(RegisterStates.waiting_for_phone)(waiting_for_phone_fallback)
    dp.message(RegisterStates.waiting_for_name)(process_name)
    dp.message(RegisterStates.waiting_for_password)(process_password)


async def start_bot(bot_token: str, company_id: int):
    """Bitta botni ishga tushiradi."""
    dp = create_dispatcher()
    dp.message.middleware(CompanyIdMiddleware(company_id))
    register_handlers(dp, company_id)

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        timeout=30.0
    )
    print(f"[Admin Bot] Bot started with token: {bot_token[:20]}... for company {company_id}")
    await dp.start_polling(bot)


async def main() -> None:
    """Barcha admin botlarni bazadan olib ishga tushirida."""
    # Jadvalni yaratish
    create_tables()

    db = SessionLocal()
    try:
        admin_bots = db.query(CompanyBot).filter(
            CompanyBot.bot_type == "admin",
            CompanyBot.is_active == True
        ).all()

        if not admin_bots:
            print("[Admin Bot] Faol admin botlar topilmadi.")
            return

        print(f"[Admin Bot] {len(admin_bots)} ta admin bot topildi. Ishga tushirilmoqda...")

        tasks = []
        for company_bot in admin_bots:
            task = asyncio.create_task(start_bot(company_bot.bot_token, company_bot.company_id))
            tasks.append(task)

        await asyncio.gather(*tasks)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
