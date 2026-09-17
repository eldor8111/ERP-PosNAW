-- 1. Create wallets table
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

-- 2. Add wallet_id to transactions and expenses
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS wallet_id INTEGER REFERENCES wallets(id);
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS wallet_id INTEGER REFERENCES wallets(id);
