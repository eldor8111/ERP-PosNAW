from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,          # Ko'proq parallel ulanish
    max_overflow=10,       # Ortiqcha ulanishlar
    pool_pre_ping=True,    # Ulanish tirikligini tekshiradi
    pool_recycle=900,      # 15 daqiqada yangilash (Supabase idle timeout oldini olish)
    pool_timeout=20,       # 20 soniya kutadi
    connect_args={
        "sslmode": "require",
        "connect_timeout": 10,          # Ulanish 10 soniyada bajarilsin
        "options": "-c statement_timeout=15000",  # 15 soniyadan uzun query xato qaytarsin
    },
    execution_options={"no_parameters": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
