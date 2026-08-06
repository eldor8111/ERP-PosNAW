import asyncio
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from app.database import SessionLocal
from app.admin_tg_bot.models import CompanyBot
from app.models.user import User, UserRole

async def send_instant_notification(company_id: int, message_text: str, notif_type: str):
    """
    notif_type: 'sale' or 'finance'
    """
    db = SessionLocal()
    try:
        admin_bot = db.query(CompanyBot).filter(
            CompanyBot.company_id == company_id,
            CompanyBot.bot_type == "admin",
            CompanyBot.is_active == True
        ).first()
        
        if not admin_bot:
            return
            
        # Check settings
        if notif_type == 'sale' and not admin_bot.notify_instant_sales:
            return
        if notif_type == 'finance' and not admin_bot.notify_instant_finance:
            return
            
        admin = db.query(User).filter(
            User.company_id == company_id,
            User.tg_chat_id.isnot(None),
            User.role == UserRole.director
        ).first()
        
        if not admin or not admin.tg_chat_id:
            return
            
        bot = Bot(
            token=admin_bot.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        try:
            await bot.send_message(chat_id=admin.tg_chat_id, text=message_text)
        except Exception as e:
            print(f"Error sending instant notification: {e}")
        finally:
            await bot.session.close()
            
    finally:
        db.close()

def trigger_instant_notification(company_id: int, message_text: str, notif_type: str):
    """
    Helper to run the async send_instant_notification from sync code.
    If already in an event loop, create a task. Otherwise run it.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send_instant_notification(company_id, message_text, notif_type))
    except RuntimeError:
        asyncio.run(send_instant_notification(company_id, message_text, notif_type))

