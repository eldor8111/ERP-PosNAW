import traceback
from sqlalchemy import create_engine, text

DB_URL = "postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)

try:
    with engine.connect() as conn:
        print("Adding columns to customers table...")
        
        cols_to_add = [
            "tg_chat_id VARCHAR(50)",
            "discount_percent NUMERIC(5, 2) DEFAULT 0",
            "card_number VARCHAR(20)",
            "cashback_percent NUMERIC(5, 2) DEFAULT 0",
            "bonus_balance NUMERIC(14, 2) DEFAULT 0",
            "total_spent NUMERIC(14, 2) DEFAULT 0",
            "company_id INTEGER REFERENCES companies(id)"
        ]
        
        for col in cols_to_add:
            col_name = col.split(' ')[0]
            try:
                conn.execute(text(f"ALTER TABLE customers ADD COLUMN {col}"))
                print(f"Added column {col_name}")
            except Exception as e:
                print(f"Could not add {col_name}: {e}")
                
            try:
                conn.execute(text("COMMIT"))
            except:
                pass
                
        # Handle indexes
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_tg_chat_id ON customers (tg_chat_id);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_card_number ON customers (card_number);"))
            conn.execute(text("COMMIT"))
        except Exception as e:
            print("Index error:", e)
            
        print("Successfully updated customers table!")
        
except Exception as e:
    traceback.print_exc()
