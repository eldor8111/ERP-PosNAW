import asyncio
import logging
import threading
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.database import SessionLocal
from app.admin_tg_bot.models import CompanyBot
from app.admin_tg_bot.message_utils import describe_location
from app.admin_tg_bot.recipients import resolve_recipients
from app.utils.telegram_text import esc, split_html_message, strip_tags

logger = logging.getLogger(__name__)

# Telegram so'rovi uchun umumiy timeout (soniya): sekin javob chekni uzoq ushlab turmasin
BOT_REQUEST_TIMEOUT = 10


def _prepare_send(company_id: int, notif_type: str, branch_id=None):
    """DB qismi (sinxron, `asyncio.to_thread` ichida): (bot_token, [chat_id]) yoki None."""
    db = SessionLocal()
    try:
        admin_bot = db.query(CompanyBot).filter(
            CompanyBot.company_id == company_id,
            CompanyBot.bot_type == "admin",
            CompanyBot.is_active == True
        ).first()

        if not admin_bot:
            return None

        # Check settings (T4.6: 'approval' — tasdiq so'rovi har doim yuboriladi, sozlama talab qilinmaydi;
        # D4.2: 'recall' — dori seriyasini qaytarib olish xabari ham har doim yuboriladi)
        if notif_type == 'sale' and not admin_bot.notify_instant_sales:
            return None
        if notif_type == 'finance' and not admin_bot.notify_instant_finance:
            return None

        # Admin/direktorlar + (yoqilgan bo'lsa) shu filial menejerlari; faqat faol a'zolar (T0.16, T3.16)
        # T4.6: tasdiq so'rovi — admin/director va so'rov filiali menejeri ("finance" qabul qiluvchilari qoidasi)
        recipients = resolve_recipients(db, company_id, branch_id=branch_id,
                                        kind="finance" if notif_type in ("approval", "recall") else notif_type)
        chat_ids = [u.tg_chat_id for u in recipients]
        if not chat_ids:
            return None
        return admin_bot.bot_token, chat_ids
    finally:
        db.close()


def approval_keyboard(request_id: int) -> InlineKeyboardMarkup:
    """T4.6: tasdiq so'rovi tugmalari: `appr:ok:<id>` va `appr:no:<id>` (bot_manager.handle_approval_callback)."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"appr:ok:{request_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"appr:no:{request_id}"),
    ]])


async def _send_to_chat(bot: Bot, chat_id: str, chunks: list, reply_markup=None) -> None:
    for i, chunk in enumerate(chunks):
        # Tugmalar faqat oxirgi bo'lakda
        extra = {"reply_markup": reply_markup} if (reply_markup is not None and i == len(chunks) - 1) else {}
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, **extra)
        except TelegramBadRequest as e:
            # "can't parse entities" — teglarsiz bir marta qayta urinamiz
            if "can't parse entities" in str(e).lower():
                try:
                    await bot.send_message(chat_id=chat_id, text=strip_tags(chunk), parse_mode=None, **extra)
                    continue
                except Exception as e2:
                    e = e2
            logger.error("Telegram xabari yuborilmadi (chat %s): %s", chat_id, e)
        except Exception as e:
            logger.error("Telegram xabari yuborilmadi (chat %s): %s", chat_id, e)


async def send_instant_notification(company_id: int, message_text: str, notif_type: str, branch_id=None,
                                    reply_markup=None):
    """
    notif_type: 'sale', 'finance', 'approval' (T4.6: tasdiq so'rovi) yoki 'recall' (D4.2: seriyani qaytarib olish) —
    oxirgi ikkisi sozlamadan qat'i nazar yuboriladi
    branch_id: xabar filiali — shu filial menejerlari ham oladi (notify_branch_managers yoqilgan bo'lsa).
    reply_markup: inline tugmalar (masalan `approval_keyboard`).
    """
    # Sinxron DB so'rovlari event loop'ni bloklamasin
    try:
        prepared = await asyncio.to_thread(_prepare_send, company_id, notif_type, branch_id)
    except Exception as e:
        # fon vazifasi: bazadagi xato javobga/ishga ta'sir qilmasin
        logger.error("Telegram xabari tayyorlanmadi (korxona %s): %s", company_id, e)
        return
    if not prepared:
        return
    token, chat_ids = prepared

    bot = Bot(
        token=token,
        session=AiohttpSession(timeout=BOT_REQUEST_TIMEOUT),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    try:
        # 4096 belgidan uzun xabar qator chegaralarida bo'laklanadi (T2.10)
        chunks = split_html_message(message_text) or [message_text]
        # Oluvchilarga parallel (bitta sekin chat boshqalarni kutdirmasin)
        await asyncio.gather(
            *(_send_to_chat(bot, cid, chunks, *((reply_markup,) if reply_markup is not None else ())) for cid in chat_ids),
            return_exceptions=True,
        )
    finally:
        await bot.session.close()


def _build_sale_notification(sale_id: int):
    """DB qismi (sinxron): (company_id, branch_id, matn) yoki None. O'z sessiyasida ishlaydi."""
    from app.models.customer import Customer
    from app.models.sale import Sale
    from app.models.user import User

    db = SessionLocal()
    try:
        sale = db.get(Sale, sale_id)
        if sale is None or not sale.company_id:
            return None
        cashier = db.get(User, sale.cashier_id) if sale.cashier_id else None
        cust_name = None
        if sale.customer_id:
            cust_name = db.query(Customer.name).filter(
                Customer.id == sale.customer_id, Customer.company_id == sale.company_id,
            ).scalar()
        location = describe_location(db, warehouse_id=sale.warehouse_id, branch_id=sale.branch_id)

        msg = "🛒 <b>Yangi Sotuv!</b>\n"
        if location:
            msg += f"{location}\n"
        msg += f"🧾 Chek: #{esc(sale.number)}\n👤 Kassir: {esc(cashier.name if cashier else '—')}\n"
        if cust_name:
            msg += f"🤝 Mijoz: {esc(cust_name)}\n"
        msg += f"💰 Summa: {float(sale.total_amount or 0):,.0f} UZS"
        return sale.company_id, sale.branch_id, msg
    finally:
        db.close()


async def notify_new_sale(sale_id: int):
    """Yangi sotuv xabari: sotuv, ombor, filial, kassir va mijozni O'Z sessiyasida yuklab yuboradi.

    `background_tasks.add_task(notify_new_sale, sale.id)` — javob qaytgandan keyin event loop'da ishlaydi.
    Xatolar yutiladi (sotuv allaqachon saqlangan)."""
    try:
        built = await asyncio.to_thread(_build_sale_notification, sale_id)
        if not built:
            return
        company_id, branch_id, msg = built
        await send_instant_notification(company_id, msg, "sale", branch_id)
    except Exception as e:
        logger.error("Yangi sotuv xabarini yuborib bo'lmadi (sotuv %s): %s", sale_id, e)


def trigger_instant_notification(company_id: int, message_text: str, notif_type: str, branch_id=None,
                                 reply_markup=None):
    """
    Helper to run the async send_instant_notification from sync code.
    If already in an event loop, create a task. Otherwise (threadpool) — alohida daemon thread'da
    ishga tushiradi: chaqiruvchi Telegram javobini KUTMAYDI.
    """
    coro = send_instant_notification(company_id, message_text, notif_type, branch_id,
                                     *((reply_markup,) if reply_markup is not None else ()))
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        threading.Thread(target=asyncio.run, args=(coro,), daemon=True).start()


def build_recall_message(lot: str, product_names, reason: str, user_name: str, batches_count: int,
                         remaining_qty, customers_count: int, sales_count: int) -> str:
    """D4.2: dori seriyasi qaytarib olingani haqida xabar matni. Barcha dinamik qiymatlar HTML-escape qilinadi."""
    names = [str(n) for n in (product_names or []) if n]
    shown = ", ".join(esc(n) for n in names[:5]) + (f" va yana {len(names) - 5} ta" if len(names) > 5 else "")
    qty = float(remaining_qty or 0)
    msg = "⚠️ <b>Dori seriyasi qaytarib olindi</b>\n"
    msg += f"🔖 Seriya: <b>{esc(lot)}</b>\n"
    if shown:
        msg += f"💊 Mahsulot: {shown}\n"
    msg += f"📦 Bloklangan partiyalar: {int(batches_count)} ta, qoldiq: {qty:g}\n"
    msg += f"👥 Sotilgan: {int(sales_count)} ta sotuv, {int(customers_count)} ta mijoz\n"
    msg += f"📝 Sabab: {esc(reason)}\n"
    msg += f"👤 Bloklagan: {esc(user_name)}"
    return msg


def trigger_batch_recalled(company_id: int, *, lot: str, product_names, reason: str, user_name: str,
                           batches_count: int, remaining_qty, customers_count: int, sales_count: int) -> None:
    """D4.2: seriya bloklangani haqida admin/direktorlarga Telegram xabari (fon rejimida, kutmaydi)."""
    msg = build_recall_message(lot, product_names, reason, user_name, batches_count,
                               remaining_qty, customers_count, sales_count)
    trigger_instant_notification(company_id, msg, "recall")
