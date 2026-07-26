import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import engine

def main():
    print("Running DB migration...")
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN currency_code VARCHAR(10) DEFAULT 'UZS';"))
            print("Column currency_code added.")
        except Exception as e:
            print(f"Error (maybe already exists): {e}")

        try:
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN exchange_rate NUMERIC(14, 2) DEFAULT 1;"))
            print("Column exchange_rate added.")
        except Exception as e:
            print(f"Error (maybe already exists): {e}")

if __name__ == "__main__":
    main()
