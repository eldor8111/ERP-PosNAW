from app.database import engine
from sqlalchemy import text

def apply_migrations():
    with engine.begin() as conn:
        print("Adding columns for tg_bot_token and debt_due_date...")
        try:
            conn.execute(text("ALTER TABLE companies ADD COLUMN tg_bot_token VARCHAR(100);"))
        except Exception as e:
            print("tg_bot_token:", e)
        try:
            conn.execute(text("ALTER TABLE companies ADD COLUMN tg_bot_username VARCHAR(100);"))
        except Exception as e:
            print("tg_bot_username:", e)
            
        try:
            conn.execute(text("ALTER TABLE customers ADD COLUMN tg_chat_id VARCHAR(50) UNIQUE;"))
        except Exception as e:
            print("tg_chat_id:", e)
            
        try:
            conn.execute(text("ALTER TABLE sales ADD COLUMN debt_due_date DATE;"))
        except Exception as e:
            print("debt_due_date:", e)
        
        print("Done!")

if __name__ == "__main__":
    apply_migrations()
