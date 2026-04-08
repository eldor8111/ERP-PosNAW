from fastapi import APIRouter, HTTPException, BackgroundTasks, status
import httpx
import os
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["Leads"])

class LeadRequest(BaseModel):
    service: str
    name: str
    phone: str

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8572484074:AAFMbjXaquRUz4ObVMGGI1AVK_9oO5V5MeQ")
TELEGRAM_LEAD_CHAT_ID = os.environ.get("TELEGRAM_LEAD_CHAT_ID", "8756706353")

async def send_to_telegram(lead: LeadRequest):
    if not TELEGRAM_LEAD_CHAT_ID:
        logger.error("TELEGRAM_LEAD_CHAT_ID is not configured. Cannot send lead to Telegram.")
        return

    message = (
        f"📝 <b>Yangi Buyurtma (Lead) tushdi!</b>\n\n"
        f"👤 <b>Mijoz:</b> {lead.name}\n"
        f"📱 <b>Telefon:</b> {lead.phone}\n"
        f"🎯 <b>Xizmat:</b> {lead.service}\n"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_LEAD_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10.0)
            if resp.status_code != 200:
                logger.error(f"Telegram API xatosi: {resp.text}")
    except Exception as e:
        logger.error(f"Telegramga yuborishda xato: {e}")

@router.post("", status_code=status.HTTP_200_OK)
async def create_lead(lead: LeadRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(send_to_telegram, lead)
    return {"message": "So'rov muvaffaqiyatli qabul qilindi"}
