import asyncio
import re
from os import getenv
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

from app.database import SessionLocal, engine
from app.admin_tg_bot.models import CompanyBot
from app.models.company import Company  # noqa: F401 — relationship uchun mapper registryga ro'yxatdan o'tkazish shart
from app.models.user import User, UserRole
from app.core.security import hash_password


class RegisterStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_name = State()
    waiting_for_company_name = State()
    waiting_for_password = State()


def normalize_phone(phone: str) -> str:
    """Solishtirish uchun raqamni oxirgi 9 ta raqamiga qisqartiradi (+998, bo'shliq, tire farqi muammo bo'lmasin)."""
    digits = re.sub(r"\D", "", phone or "")
    return digits[-9:] if len(digits) >= 9 else digits


def fetch_admin_by_tg_id(tg_id: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.tg_chat_id == tg_id).first()
        return user
    finally:
        db.close()


def link_admin_by_phone(phone: str, tg_id: str, tg_full_name: str | None):
    db = SessionLocal()
    try:
        normalized_phone = normalize_phone(phone)
        user = db.query(User).filter(User.phone.like(f"%{normalized_phone}")).first()

        if not user:
            return None, "not_found"

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


def create_new_user_and_company(phone: str, tg_id: str, name: str, company_name: str, password: str):
    db = SessionLocal()
    try:
        # Check if phone already exists
        normalized_phone = normalize_phone(phone)
        existing_user = db.query(User).filter(User.phone.like(f"%{normalized_phone}")).first()
        if existing_user:
            return None, "phone_exists"

        # Check if company name already exists
        existing_company = db.query(Company).filter(Company.name == company_name).first()
        if existing_company:
            return None, "company_exists"

        # Create new company
        company = Company(name=company_name)
        db.add(company)
        db.commit()
        db.refresh(company)

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

    company_name = user.company_id if user.company_id else "—"
    await message.answer(
        f"{greeting}👋 Assalomu alaykum!\n\n"
        f"🏢 <b>E-CODE Admin</b> botiga xush kelibsiz!\n"
        f"👤 Ism: <b>{user.name}</b>\n"
        f"🏬 Kompaniya: <b>{company_name}</b>",
        reply_markup=ReplyKeyboardRemove(),
    )


async def cmd_start(message: Message, state: FSMContext) -> None:
    tg_id = str(message.from_user.id)
    admin = await asyncio.to_thread(fetch_admin_by_tg_id, tg_id)

    if admin:
        await send_welcome(message, admin)
        return

    await state.set_state(RegisterStates.waiting_for_phone)
    await message.answer(
        "❌ Siz hali ro'yxatdan o'tmagansiz.\n\n"
        "Ro'yxatdan o'tish uchun telefon raqamingizni yuboring 👇",
        reply_markup=contact_keyboard(),
    )


async def process_contact(message: Message, state: FSMContext) -> None:
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("⚠️ Iltimos, faqat o'zingizning raqamingizni yuboring.")
        return

    tg_id = str(message.from_user.id)
    admin, status = await asyncio.to_thread(
        link_admin_by_phone, contact.phone_number, tg_id, message.from_user.full_name
    )

    if status == "not_found":
        # Start new registration process
        await state.update_data(phone=contact.phone_number)
        await state.set_state(RegisterStates.waiting_for_name)
        await message.answer(
            "❌ Bu raqam tizimda topilmadi.\n\n"
            "Yangi kompaniya sifatida ro'yxatdan o'tish uchun ma'lumotlaringizni kiriting.\n\n"
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


async def process_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Iltimos, to'g'ri ism kiriting.")
        return

    await state.update_data(name=name)
    await state.set_state(RegisterStates.waiting_for_company_name)
    await message.answer("🏢 Kompaniya nomini kiriting:")


async def process_company_name(message: Message, state: FSMContext) -> None:
    company_name = message.text.strip()
    if len(company_name) < 2:
        await message.answer("⚠️ Iltimos, to'g'ri kompaniya nomi kiriting.")
        return

    await state.update_data(company_name=company_name)
    await state.set_state(RegisterStates.waiting_for_password)
    await message.answer("🔐 Parolni kiriting (kamida 6 ta belgi):")


async def process_password(message: Message, state: FSMContext) -> None:
    password = message.text.strip()
    if len(password) < 6:
        await message.answer("⚠️ Parol kamida 6 ta belgidan iborat bo'lishi kerak.")
        return

    data = await state.get_data()
    tg_id = str(message.from_user.id)

    user, status = await asyncio.to_thread(
        create_new_user_and_company,
        data["phone"],
        tg_id,
        data["name"],
        data["company_name"],
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

    if status == "company_exists":
        await message.answer(
            "❌ Bu kompaniya nomi allaqachon mavjud.\n"
            "Boshqa nom kiriting.",
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


def register_handlers(dp: Dispatcher):
    """Dispatcher ga handlerlarni ro'yxatdan o'tkazadi."""
    dp.message(CommandStart())(cmd_start)
    dp.message(RegisterStates.waiting_for_phone, F.contact)(process_contact)
    dp.message(RegisterStates.waiting_for_phone)(waiting_for_phone_fallback)
    dp.message(RegisterStates.waiting_for_name)(process_name)
    dp.message(RegisterStates.waiting_for_company_name)(process_company_name)
    dp.message(RegisterStates.waiting_for_password)(process_password)


async def start_bot(bot_token: str):
    """Bitta botni ishga tushiradi."""
    dp = create_dispatcher()
    register_handlers(dp)

    bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    print(f"[Admin Bot] Bot started with token: {bot_token[:20]}...")
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
            task = asyncio.create_task(start_bot(company_bot.bot_token))
            tasks.append(task)

        await asyncio.gather(*tasks)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())