from app.database import engine
from sqlalchemy import text

def apply_migrations():
    with engine.begin() as conn:
        print("Adding columns to customers...")
        try:
            conn.execute(text("ALTER TABLE customers ADD COLUMN card_number VARCHAR(20) UNIQUE;"))
        except Exception as e:
            print("card_number:", e)
        try:
            conn.execute(text("ALTER TABLE customers ADD COLUMN cashback_percent NUMERIC(5, 2) DEFAULT 0;"))
        except Exception as e:
            print("cashback_percent:", e)
        try:
            conn.execute(text("ALTER TABLE customers ADD COLUMN bonus_balance NUMERIC(14, 2) DEFAULT 0;"))
        except Exception as e:
            print("bonus_balance:", e)
        try:
            conn.execute(text("ALTER TABLE customers ADD COLUMN total_spent NUMERIC(14, 2) DEFAULT 0;"))
        except Exception as e:
            print("total_spent:", e)
        
        print("Done!")

if __name__ == "__main__":
    apply_migrations()
