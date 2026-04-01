from fastapi import APIRouter, Request, BackgroundTasks, Depends  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
import httpx
import re

from app.database import get_db  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.customer import Customer  # type: ignore

router = APIRouter(prefix="/telegram", tags=["Telegram"])


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


@router.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Kompaniya o'zining telegram botiga webhook ulagan bo'lsa, xabarlar shu yerga keladi.
    Webhook URL: https://[SIZNING_DOMAININGIZ]/api/telegram/webhook/{bot_token}
    """
    try:
        data = await request.json()
        if "message" in data:
            message = data["message"]
            chat_id = str(message["chat"]["id"])
            text = message.get("text", "")

            if "text" in message and text.startswith("/start"):
                # Ask for phone number
                keyboard = {
                    "keyboard": [
                        [{"text": "📞 Raqamni yuborish", "request_contact": True}]
                    ],
                    "resize_keyboard": True,
                    "one_time_keyboard": True
                }
                msg_text = "👋 Assalomu alaykum!\n\nIltimos, tizimga ulanish (identifikatsiya) uchun pastdagi <b>Raqamni yuborish</b> tugmasini bosing."
                background_tasks.add_task(send_telegram_message, token, chat_id, msg_text, keyboard)
                
            elif "contact" in message:
                contact = message["contact"]
                phone = contact.get("phone_number", "")
                
                # Clean phone number for searching (get only numbers)
                p_clean = "".join(filter(str.isdigit, str(phone)))
                
                # Find company by token
                company = db.query(Company).filter(Company.tg_bot_token == token).first()
                if not company:
                    background_tasks.add_task(send_telegram_message, token, chat_id, "❌ Kompaniya topilmadi yoki bot xato sozlangan.", {"remove_keyboard": True})
                    return {"ok": True}
                
                # Fetch all customers of this company to match phone
                customers = db.query(Customer).filter(Customer.company_id == company.id).all()
                found_customer = None
                
                for c in customers:
                    if c.phone:
                        c_clean = "".join(filter(str.isdigit, str(c.phone)))
                        # Match last 9 digits to handle +998 vs 998 and 8 prefixes
                        if len(c_clean) >= 9 and len(p_clean) >= 9 and c_clean[-9:] == p_clean[-9:]:
                            found_customer = c
                            break
                            
                if found_customer:
                    found_customer.tg_chat_id = chat_id
                    db.commit()
                    reply_text = f"✅ Assalomu alaykum, <b>{found_customer.name}</b>!\n\nSizning profilingiz <b>{company.name}</b> do'koni tizimiga muvaffaqiyatli ulandi.\nXush kelibsiz! 🎉"
                    background_tasks.add_task(send_telegram_message, token, chat_id, reply_text, {"remove_keyboard": True})
                else:
                    msg_err = "❌ Kechirasiz, sizning raqamingiz bo'yicha mijoz topilmadi. Avval do'kondan ro'yxatdan o'tishingiz yoki xarid qilishingiz kerak!"
                    background_tasks.add_task(send_telegram_message, token, chat_id, msg_err, {"remove_keyboard": True})                    
        return {"ok": True}
    except Exception as e:
        print("Webhook Error:", str(e))
        return {"ok": False}
