import sys
import os

# To allow importing from app
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import engine
from sqlalchemy import text

def fix_constraints():
    with engine.connect() as conn:
        try:
            # PostgreSQL da unique constraint larni olib tashlash
            conn.execute(text("ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_phone_key;"))
            conn.execute(text("ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_tg_chat_id_key;"))
            conn.execute(text("ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_card_number_key;"))
            
            # Agar constraint nomi boshqacha bo'lsa (masalan index orqali unique qilingan bo'lsa)
            conn.execute(text("DROP INDEX IF EXISTS ix_customers_phone;"))
            conn.execute(text("DROP INDEX IF EXISTS ix_customers_tg_chat_id;"))
            conn.execute(text("DROP INDEX IF EXISTS ix_customers_card_number;"))
            
            # Oddiy indexlarni yaratamiz (Unique bo'lmagan)
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_phone ON customers(phone);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_tg_chat_id ON customers(tg_chat_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_card_number ON customers(card_number);"))
            
            # Composite unique constraintlarni qo'shamiz
            conn.execute(text("ALTER TABLE customers ADD CONSTRAINT uq_company_customer_phone UNIQUE (company_id, phone);"))
            conn.execute(text("ALTER TABLE customers ADD CONSTRAINT uq_company_customer_tg_chat_id UNIQUE (company_id, tg_chat_id);"))
            conn.execute(text("ALTER TABLE customers ADD CONSTRAINT uq_company_customer_card_number UNIQUE (company_id, card_number);"))
            
            conn.commit()
            print("Customer constraintlari muvaffaqiyatli yangilandi!")
        except Exception as e:
            print("Xatolik:", e)
            conn.rollback()

if __name__ == "__main__":
    fix_constraints()
