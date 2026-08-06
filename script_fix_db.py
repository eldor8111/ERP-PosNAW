"""
Bu script company_bots jadvaliga yangi ustunlarni qo'shadi
va alembic_version ni to'g'irlaydi.
"""
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.DATABASE_URL)

with engine.begin() as conn:
    print("1. Alembic version tekshirilmoqda...")
    result = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
    print(f"   Joriy versiya(lar): {result}")

    print("\n2. company_bots jadvaliga yangi ustunlar qo'shilmoqda...")
    
    # notify_instant_sales
    try:
        conn.execute(text("ALTER TABLE company_bots ADD COLUMN IF NOT EXISTS notify_instant_sales BOOLEAN DEFAULT TRUE"))
        print("   + notify_instant_sales qo'shildi")
    except Exception as e:
        print(f"   - notify_instant_sales: {e}")

    # notify_instant_finance
    try:
        conn.execute(text("ALTER TABLE company_bots ADD COLUMN IF NOT EXISTS notify_instant_finance BOOLEAN DEFAULT TRUE"))
        print("   + notify_instant_finance qo'shildi")
    except Exception as e:
        print(f"   - notify_instant_finance: {e}")

    # notify_scheduled
    try:
        conn.execute(text("ALTER TABLE company_bots ADD COLUMN IF NOT EXISTS notify_scheduled BOOLEAN DEFAULT TRUE"))
        print("   + notify_scheduled qo'shildi")
    except Exception as e:
        print(f"   - notify_scheduled: {e}")

    # scheduled_time
    try:
        conn.execute(text("ALTER TABLE company_bots ADD COLUMN IF NOT EXISTS scheduled_time VARCHAR(5) DEFAULT '20:00'"))
        print("   + scheduled_time qo'shildi")
    except Exception as e:
        print(f"   - scheduled_time: {e}")

    # unique constraint
    try:
        conn.execute(text("ALTER TABLE company_bots DROP CONSTRAINT IF EXISTS company_bots_company_id_key"))
        print("   + Eski unique constraint o'chirildi")
    except Exception as e:
        print(f"   - eski constraint: {e}")

    try:
        conn.execute(text("ALTER TABLE company_bots ADD CONSTRAINT uq_company_bot_type UNIQUE (company_id, bot_type)"))
        print("   + Yangi unique constraint qo'shildi")
    except Exception as e:
        print(f"   - yangi constraint (mavjud bo'lishi mumkin): {e}")

    print("\n3. Alembic version yangilanmoqda...")
    conn.execute(text("DELETE FROM alembic_version"))
    conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('v7w8x9y0z1a2')"))
    print("   + Versiya 'v7w8x9y0z1a2' ga o'rnatildi")

    print("\n=== Hammasi muvaffaqiyatli bajarildi! ===")
