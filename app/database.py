import os
import time

# Set default timezone to Asia/Tashkent for the Python process
os.environ['TZ'] = 'Asia/Tashkent'
try:
    time.tzset()
except AttributeError:
    # time.tzset is unix-only
    pass

from sqlalchemy import create_engine, event
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
        "sslmode": "prefer",
        "connect_timeout": 10,          # Ulanish 10 soniyada bajarilsin
        "options": "-c statement_timeout=15000",  # 15 soniyadan uzun query xato qaytarsin
    },
    execution_options={"no_parameters": False},
)

@event.listens_for(engine, "connect")
def set_timezone(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SET TIME ZONE 'Asia/Tashkent';")
        dbapi_connection.commit()
    except Exception:
        try:
            dbapi_connection.rollback()
        except Exception:
            pass
    finally:
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

