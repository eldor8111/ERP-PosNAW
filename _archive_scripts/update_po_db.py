import os
import sys

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import engine

def run_migration():
    with engine.begin() as conn:
        print("Adding paid_amount and discount_amount to purchase_orders...")
        conn.execute(text("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(14,2) DEFAULT 0;"))
        conn.execute(text("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(14,2) DEFAULT 0;"))
        print("Done!")

if __name__ == '__main__':
    run_migration()
