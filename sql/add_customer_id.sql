-- Add customer_id column to sales table if it doesn't exist

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'sales' AND column_name = 'customer_id'
    ) THEN
        ALTER TABLE sales ADD COLUMN customer_id INTEGER;
        ALTER TABLE sales ADD CONSTRAINT fk_sales_customer
            FOREIGN KEY (customer_id) REFERENCES customers(id);

        RAISE NOTICE 'customer_id column added to sales table';
    ELSE
        RAISE NOTICE 'customer_id column already exists';
    END IF;
END $$;
