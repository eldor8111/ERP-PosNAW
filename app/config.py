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
    # Uzum Bank Merchant API
    UZUM_USERNAME: str = "123123"
    UZUM_PASSWORD: str = "123123"
    UZUM_SERVICE_ID: str = "123123"
    UZUM_IS_TEST: bool = True
    # Tasnif / MXIK
    DEFAULT_TERMINAL_ID: str = ""
    TASNIF_BASE_URL: str = "https://tasnif.soliq.uz/api/cl-api"
    # Eskiz.uz
    ESKIZ_EMAIL: str = ""
    ESKIZ_PASSWORD: str = ""
    ESKIZ_FROM: str = "4546"
    ESKIZ_BASE_URL: str = "https://notify.eskiz.uz/api"
    # AI Pending actions TTL (daqiqalarda)
    AI_PENDING_ACTION_TTL_MIN: int = 10
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
    # Zaxira modellar, vergul bilan (masalan: "modelA,modelB"). Bo'sh bo'lsa faqat OPENROUTER_MODEL ishlatiladi.
    OPENROUTER_FALLBACK_MODELS: str = ""
    # --- LLM Provider Abstraction (Bosqich 1) ---
    LLM_PROVIDER: str = "openrouter"  # openrouter, anthropic, openai, mock
    LLM_MODEL_MAIN: str = "cohere/north-mini-code:free"
    LLM_MODEL_FAST: str = "cohere/north-mini-code:free"
    LLM_FALLBACK_CHAIN: str = "openrouter"  # masalan: "anthropic,openrouter,mock"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com/v1"
    ANTHROPIC_PROMPT_CACHING: bool = False
    LLM_TIMEOUT_SEC: int = 30
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BACKOFF_FACTOR: float = 1.5
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

    # AI SQL Readonly pool and limits (Bosqich 4)
    AI_DB_URL_READONLY: str = ""
    AI_SQL_MAX_ROWS: int = 200
    AI_SQL_TIMEOUT_SEC: int = 10
    STRICT_RLS_CHECK: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
