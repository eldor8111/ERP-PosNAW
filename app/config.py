from pydantic_settings import BaseSettings  # type: ignore


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENV: str = "production"
    CORS_ORIGINS: str = ""
    # Telegram OTP bot
    OTP_BOT_TOKEN: str = ""
    OTP_BOT_USERNAME: str = "EcodeSmsuzbot"
    # Server public URL (webhook uchun, masalan: https://savdo.e-code.uz)
    SERVER_URL: str = ""
    # Payme Merchant API
    PAYME_MERCHANT_ID: str = ""
    PAYME_SECRET_KEY: str = ""
    PAYME_IS_TEST: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
