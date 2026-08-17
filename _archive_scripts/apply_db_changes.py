import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL topilmadi")
    exit(1)

engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        print("Database ga ulandi. O'zgarishlar qo'llanilmoqda...")
        
        # 1. sales jadvaliga before_debt_balances ustunini qo'shish
        try:
            conn.execute(text("ALTER TABLE sales ADD COLUMN before_debt_balances JSON;"))
            print("=> before_debt_balances ustuni sales jadvaliga qo'shildi.")
        except Exception as e:
            print(f"=> before_debt_balances allaqachon mavjud yoki xatolik: {e}")
            
        # 2. sale_items jadvaliga returned_quantity ustunini qo'shish
        try:
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN returned_quantity NUMERIC(12, 3) DEFAULT 0;"))
            print("=> returned_quantity ustuni sale_items jadvaliga qo'shildi.")
        except Exception as e:
            print(f"=> returned_quantity allaqachon mavjud yoki xatolik: {e}")

        conn.commit()
        print("Barcha o'zgarishlar muvaffaqiyatli saqlandi!")
except Exception as e:
    print(f"Xatolik yuz berdi: {e}")
