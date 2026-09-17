-- ==============================================
-- IMPORTANT: Run this SQL in your PostgreSQL database
-- Database: erppos
-- User: postgres
-- ==============================================

-- Step 1: Add customer_id column to sales table
ALTER TABLE sales ADD COLUMN IF NOT EXISTS customer_id INTEGER;

-- Step 2: Add foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_sales_customer'
    ) THEN
        ALTER TABLE sales ADD CONSTRAINT fk_sales_customer
            FOREIGN KEY (customer_id) REFERENCES customers(id);
    END IF;
END $$;

-- Step 3: Update alembic version
UPDATE alembic_version SET version_num = '94e706f35485'
WHERE version_num = '93e705f35484';

-- Check the result
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'sales' AND column_name = 'customer_id';

SELECT * FROM alembic_version;
