import httpx
import time
from app.config import settings
from app.database import SessionLocal
from app.models.user import User, UserStatus

token = settings.OTP_BOT_TOKEN
BASE = f"https://api.telegram.org/bot{token}"

TARGET = "938399939"  # target phone last 9 digits

print("Polling boshlanmoqda (30 soniya)...")
print("Iltimos, HOZIROQ Telegram botga boring va /start bosib, raqamingizni yuboring!\n")

# Avval offset ni max ga o'tkazish (eski updatelarni o'tkazib yuborish)
r = httpx.get(f"{BASE}/getUpdates", params={"limit": 1, "offset": -1}, timeout=10)
updates = r.json().get("result", [])
offset = 0
if updates:
    offset = updates[-1]["update_id"] + 1
    print(f"Boshlang'ich offset: {offset}")
else:
    print("Hech qanday eski update yo'q, 0 dan boshlaymiz")

found_chat_id = None
deadline = time.time() + 60  # 60 soniya kutish

while time.time() < deadline:
    remaining = int(deadline - time.time())
    print(f"Kutilmoqda... ({remaining}s qoldi)", end="\r")
    
    try:
        r = httpx.get(
            f"{BASE}/getUpdates",
            params={"offset": offset, "timeout": 10, "limit": 10},
            timeout=15
        )
        data = r.json()
        for u in data.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message", {})
            
            # Kontakt kelganda
            contact = msg.get("contact", {})
            if contact:
                phone_raw = contact.get("phone_number", "")
                digits = "".join(filter(str.isdigit, phone_raw))
                chat_id = str(msg.get("chat", {}).get("id", ""))
                print(f"\nKontakt keldi: +{digits} -> chat_id={chat_id}")
                
                if digits.endswith(TARGET):
                    found_chat_id = chat_id
                    print(f"*** TOPILDI: chat_id={found_chat_id} ***")
                    break
    except Exception as e:
        print(f"\nXato: {e}")
        time.sleep(2)
    
    if found_chat_id:
        break

print()

if found_chat_id:
    db = SessionLocal()
    try:
        user = db.query(User).filter(
            User.phone == "998938399939",
            User.status == UserStatus.active
        ).first()
        if user:
            user.tg_chat_id = found_chat_id
            db.commit()
            print(f"DB yangilandi! {user.name} ({user.phone}) -> tg_chat_id={found_chat_id}")
        else:
            print("Foydalanuvchi topilmadi!")
    finally:
        db.close()
else:
    print("Vaqt tugadi. Kontakt topilmadi.")
    print("Iltimos, botga boring va /start bosing, keyin skriptni qayta ishga tushiring.")
