from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,          # Har doim 10 ta ulanish tayyor
    max_overflow=20,       # Zarur bo'lsa 20 ta qo'shimcha
    pool_pre_ping=True,    # Ulanish hali tirik ekanini tekshiradi
    pool_recycle=1800,     # 30 daqiqada yangi ulanish (PostgreSQL timeout oldini olish)
    pool_timeout=30,       # 30 soniya kutadi, keyin xato qaytaradi
    connect_args={"sslmode": "require"},  # SSL majburiy (Supabase va production uchun)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
