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
    MARKETPLACE_API_TOKEN: str = ""
    MARKETPLACE_CATEGORIES_TTL: int = 3600  # sekund

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
