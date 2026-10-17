from pydantic_settings import BaseSettings  # type: ignore


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    # .env da qiymat berilmasa ishlatiladigan xavfsiz standart (kod darajasidagi
    # standart uzoq bo'lsa, .env noto'liq sozlangan deploy'da seanslar oyларча
    # amal qilib qolishi mumkin edi)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 soat
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7 kun
    ENV: str = "production"
    CORS_ORIGINS: str = ""
    # Telegram OTP bot
    OTP_BOT_TOKEN: str = ""
    OTP_BOT_USERNAME: str = "EcodeSmsuzbot"
    ADMIN_BOT_TOKEN: str = ""
    # Server public URL (webhook uchun, masalan: https://savdo.e-code.uz)
    SERVER_URL: str = ""
    OPENAI_API_KEY: str = ""
    # Payme Merchant API
    PAYME_MERCHANT_ID: str = ""
    PAYME_SECRET_KEY: str = ""
    PAYME_IS_TEST: bool = True
    # Tasnif / MXIK
    DEFAULT_TERMINAL_ID: str = ""
    TASNIF_BASE_URL: str = "https://tasnif.soliq.uz/api/cl-api"
    # Eskiz.uz
    ESKIZ_EMAIL: str = "supergeroy2580@gmail.com"
    ESKIZ_PASSWORD: str = "ajjg1m0DagelnulNNXk635Ek4tYOYTC5xvp39eGR"
    ESKIZ_FROM: str = "4546"
    ESKIZ_BASE_URL: str = "https://notify.eskiz.uz/api"
    # --- Hippo Communicator (fiskalizatsiya) ---
    HIPPO_COMMUNICATOR_URL: str = "http://127.0.0.1:8081"
    HIPPO_API_PREFIX: str = "/api"
    HIPPO_TIMEOUT: int = 30
    # T3.18: server tomonidagi Hippo kommunikatori (/api/hippo/* va X-Hippo-Factory-Id orqali fonda fiskallash).
    # Standart O'CHIQ: fiskallash kassir kompyuteridagi lokal ko'prik orqali bajariladi, natija PATCH /sales/{id}/fiscal
    # bilan yoziladi. Server kommunikatori prodda ishlatilsa .env da HIPPO_SERVER_ENABLED=true qiling.
    HIPPO_SERVER_ENABLED: bool = False
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "cohere/north-mini-code:free"
    # Marketplace (mir-maza.uz) — kategoriyalar manbai. API manzili .env da beriladi.
    MARKETPLACE_CATEGORIES_URL: str = "https://mir-maza.uz/api/v1/categories"
    # Mir-maza bilan umumiy maxfiy kalit (X-Integration-Key): chiquvchi so'rovlar VA kiruvchi
    # /webhook/order uchun bitta kalit. Bo'sh bo'lsa integratsiya o'chiq (so'rov yuborilmaydi, webhook 503).
    # MAJBURIY (marketplace moduli ishlashi uchun): .env da MARKETPLACE_API_TOKEN=... bering.
    # Kodda zaxira kalit YO'Q — bo'sh bo'lsa buyurtma importi (pull_mirmaza_orders) o'tkazib yuboriladi.
    MARKETPLACE_API_TOKEN: str = ""
    MARKETPLACE_CATEGORIES_TTL: int = 3600  # sekund
    # Oflayn POS sotuvi (T3.11): created_at shu soatdan eski bo'lsa rad etiladi,
    # kelajakka esa faqat shu daqiqa tolerans beriladi (soat siljishi uchun)
    POS_OFFLINE_MAX_AGE_HOURS: int = 72
    POS_FUTURE_TOLERANCE_MINUTES: int = 5

    # Ombor limiti rejimi (T3.9): "off" — tekshirilmaydi; "warn" — limit oshsa faqat log + usage'da over=true;
    # "enforce" — 403. Birinchi deployda "warn"; super admin tariflarni tekshirgach "enforce" qilinadi.
    TARIFF_WAREHOUSE_LIMIT_MODE: str = "warn"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
