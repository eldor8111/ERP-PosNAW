"""
Database migration script — v3
Creates: wallet_balances, sale_payments tables
Adds:    payment_type column to transactions table

Run: python migrate_v3.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import engine

SQL = """
-- 1. transactions jadvaliga payment_type ustuni qo'shish
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_type VARCHAR(50);

-- 2. wallet_balances jadvali (har bir hamyon uchun to'lov turi bo'yicha qoldiq)
CREATE TABLE IF NOT EXISTS wallet_balances (
    id SERIAL PRIMARY KEY,
    wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
    payment_type VARCHAR(50) NOT NULL,
    balance NUMERIC(14, 2) DEFAULT 0,
    UNIQUE(wallet_id, payment_type)
);

-- 3. sale_payments jadvali (har bir sotuv uchun to'lov turlarini saqlash)
CREATE TABLE IF NOT EXISTS sale_payments (
    id SERIAL PRIMARY KEY,
    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    payment_type VARCHAR(50) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_sale_payments_sale_id ON sale_payments(sale_id);
"""

def run():
    print("Starting migration v3...")
    with engine.connect() as conn:
        conn.execute(text(SQL))
        conn.commit()
    print("✅ Migration v3 complete!")
    print("   - transactions.payment_type column added")
    print("   - wallet_balances table created")
    print("   - sale_payments table created")

if __name__ == "__main__":
    run()
