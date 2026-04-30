from app.database import engine
from sqlalchemy import text

def run_migrations():
    with engine.begin() as conn:
        # Create wallets table
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS wallets (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(20) NOT NULL DEFAULT 'cash',
            balance NUMERIC(14, 2) DEFAULT 0,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            branch_id INTEGER REFERENCES branches(id),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """))
        
        # Add wallet_id to transactions if not exists
        try:
            conn.execute(text("""
            ALTER TABLE transactions ADD COLUMN IF NOT EXISTS wallet_id INTEGER REFERENCES wallets(id);
            """))
        except Exception as e:
            print("Transactions table update error:", e)

        # Add wallet_id to expenses if not exists
        try:
            conn.execute(text("""
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS wallet_id INTEGER REFERENCES wallets(id);
            """))
        except Exception as e:
            print("Expenses table update error:", e)
            
        print("Database migrations applied successfully!")

if __name__ == "__main__":
    run_migrations()
