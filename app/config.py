from pydantic_settings import BaseSettings  # type: ignore


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 kun
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90  # 90 kun
    ENV: str = "production"
    CORS_ORIGINS: str = ""
    # Telegram OTP bot
    OTP_BOT_TOKEN: str = ""
    OTP_BOT_USERNAME: str = "EcodeSmsuzbot"
    ADMIN_BOT_TOKEN: str = ""
    # Server public URL (webhook uchun, masalan: https://savdo.e-code.uz)
    SERVER_URL: str = ""
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
    # --- Hippo Communicator (fiskalizatsiya) ---
    HIPPO_COMMUNICATOR_URL: str = "http://127.0.0.1:8081"
    HIPPO_API_PREFIX: str = "/api"
    HIPPO_TIMEOUT: int = 30
    # Gemini API Key
    GEMINI_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
