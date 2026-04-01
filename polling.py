import asyncio
import httpx
from sqlalchemy.orm import Session
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app.models.company import Company

async def poll_bot(company):
    token = company.tg_bot_token
    if not token: 
        return
    
    offset = 0
    print(f"[{company.name}] Bot xabarlarni kutmoqda... (Polling started)")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            try:
                # API xabarlarini uzoq muddat (Long polling) orqali kutish
                url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=50"
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    for update in data.get("result", []):
                        offset = update["update_id"] + 1
                        
                        # Kelgan xabarni o'zimizning lokal webhook url-ga yuboramiz
                        local_webhook = f"http://127.0.0.1:8000/api/telegram/webhook/{token}"
                        try:
                            await client.post(local_webhook, json=update)
                        except Exception as inner_e:
                            print(f"[XATO] Local serverga yetib bormadi (server yoniqmi?): {inner_e}")
                else:
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"[{company.name}] Polling kutishda xatolik (Internetni tekshiring):", e)
                await asyncio.sleep(5)

async def main():
    # Barcha API tokenlarini olish
    db: Session = SessionLocal()
    companies = db.query(Company).filter(Company.tg_bot_token.isnot(None), Company.tg_bot_token != "").all()
    db.close()
    
    if not companies:
        print("Tizimda birorta ham bot tokeni ulangan kompaniya topilmadi.")
        print("Avval Admin paneldan Settings > Telegram bot orqali tokenni saqlang.")
        return
        
    tasks = []
    for c in companies:
        tasks.append(poll_bot(c))
        
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Polling to'xtatildi.")
