import os
import firebase_admin
from firebase_admin import credentials, messaging

# Firebase ulanganligini kuzatish uchun bayroq
_firebase_initialized = False

def init_firebase():
    """
    Firebase Admin SDK ni ishga tushiradi.
    Odatda bu funksiya ilova yonganida yoki xabar jo'natishdan oldin chaqiriladi.
    """
    global _firebase_initialized
    if _firebase_initialized:
        return True

    # JSON fayl nomini atrof-muhit o'zgaruvchisidan yoki standart nomdan oladi
    cert_path = os.getenv("FIREBASE_CREDENTIALS", "firebase-adminsdk.json")
    
    if not os.path.exists(cert_path):
        print(f"[FCM] Ogohlantirish: {cert_path} topilmadi. Push bildirishnomalar ishlamaydi.")
        return False

    try:
        cred = credentials.Certificate(cert_path)
        firebase_admin.initialize_app(cred)
        _firebase_initialized = True
        print("[FCM] Firebase muvaffaqiyatli ishga tushdi.")
        return True
    except Exception as e:
        print(f"[FCM] Firebase xatosi: {e}")
        return False

def send_push_notification(token: str, title: str, body: str, data: dict = None) -> bool:
    """
    Bitta qurilmaga push bildirishnoma jo'natadi.
    """
    if not init_firebase():
        return False

    if not token:
        return False

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=token,
        )
        response = messaging.send(message)
        print(f"[FCM] Xabar yuborildi: {response}")
        return True
    except Exception as e:
        print(f"[FCM] Xabar yuborishda xatolik: {e}")
        return False

def send_multicast_notification(tokens: list, title: str, body: str, data: dict = None) -> dict:
    """
    Bir nechta qurilmaga birdaniga push bildirishnoma jo'natadi.
    """
    if not init_firebase():
        return {"success": 0, "failure": len(tokens)}

    if not tokens:
        return {"success": 0, "failure": 0}

    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            tokens=tokens,
        )
        response = messaging.send_multicast(message)
        print(f"[FCM] Ko'p kishilik xabar yuborildi. Muvaffaqiyatli: {response.success_count}, Xato: {response.failure_count}")
        return {
            "success": response.success_count,
            "failure": response.failure_count,
            "failed_tokens": [
                tokens[idx] for idx, resp in enumerate(response.responses) if not resp.success
            ]
        }
    except Exception as e:
        print(f"[FCM] Ko'p kishilik xabar yuborishda xatolik: {e}")
        return {"success": 0, "failure": len(tokens)}
