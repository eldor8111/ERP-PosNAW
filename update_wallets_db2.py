import asyncio
from sqlalchemy import text
from app.database import engine

def run_migration():
    with engine.connect() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS wallet_balances (
            id SERIAL PRIMARY KEY,
            wallet_id INTEGER NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
            payment_type VARCHAR(50) NOT NULL,
            balance NUMERIC(14, 2) DEFAULT 0,
            UNIQUE(wallet_id, payment_type)
        );
        """))
        
        conn.execute(text("""
        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_type VARCHAR(50);
        """))
        
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sale_payments (
            id SERIAL PRIMARY KEY,
            sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
            payment_type VARCHAR(50) NOT NULL,
            amount NUMERIC(14, 2) NOT NULL
        );
        """))
        conn.commit()
        print("Migration successful")

if __name__ == "__main__":
    run_migration()
