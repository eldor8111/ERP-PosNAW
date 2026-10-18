"""T0.26: mijozni arxivlash ustunlari + moliyaviy maydonlar CHECK cheklovlari

1. customers.is_active (BOOLEAN NOT NULL DEFAULT true), deleted_at, deleted_meta (JSON) —
   tarixi bor mijoz jismonan o'chirilmaydi, arxivlanadi. Indeks (company_id, is_active).
2. CHECK dan oldin ma'lumotni tozalash (qo'llangan qatorlar soni logga chiqariladi):
   - price_type: NULL / noma'lum ('retail' va h.k.) -> 'sale' (resolve_price natijasi o'zgarmaydi);
   - cashback_percent: NULL yoki < 0 -> 0, > 100 -> 100;
   - loyalty_points: < 0 -> 0.
3. CHECK: ck_customers_price_type, ck_customers_cashback_0_100, ck_customers_loyalty_nonneg.

Revision ID: t0_26
Revises: t0_23
"""
import logging

from alembic import op
import sqlalchemy as sa

log = logging.getLogger("alembic")


revision = 't0_26'
down_revision = 't0_23'
branch_labels = None
depends_on = None


def upgrade():
    # 0. Table owner RLS to'siqlarini olib tashlash (NO FORCE)
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE customers NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE sales NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE products NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE purchase_orders NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE warehouses NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE suppliers NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE sale_items NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE stock_levels NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE stock_movements NO FORCE ROW LEVEL SECURITY;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'Skipping NO FORCE RLS: %', SQLERRM;
        END $$;
    """)

    # 1. Arxivlash ustunlari
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL")
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS deleted_meta JSON NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_company_active ON customers (company_id, is_active)")

    # 2. Ma'lumotni tozalash (CHECK dan oldin)
    op.execute("""
        UPDATE customers SET price_type = 'sale' 
        WHERE price_type IS NULL OR TRIM(LOWER(price_type::text)) NOT IN ('sale', 'wholesale', 'cost');
        
        UPDATE customers SET cashback_percent = 0 
        WHERE cashback_percent IS NULL OR cashback_percent < 0;
        
        UPDATE customers SET cashback_percent = 100 
        WHERE cashback_percent > 100;
        
        UPDATE customers SET loyalty_points = 0 
        WHERE loyalty_points IS NULL OR loyalty_points < 0;
    """)

    # 3. CHECK cheklovlari (NOT VALID bilan — eski ma'lumotlar buzilsa ham to'xtatmaydi, yangilariga amal qiladi)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_customers_price_type') THEN
                ALTER TABLE customers ADD CONSTRAINT ck_customers_price_type CHECK (price_type IN ('sale', 'wholesale', 'cost')) NOT VALID;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_customers_cashback_0_100') THEN
                ALTER TABLE customers ADD CONSTRAINT ck_customers_cashback_0_100 CHECK (cashback_percent >= 0 AND cashback_percent <= 100) NOT VALID;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_customers_loyalty_nonneg') THEN
                ALTER TABLE customers ADD CONSTRAINT ck_customers_loyalty_nonneg CHECK (loyalty_points >= 0) NOT VALID;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE customers DROP CONSTRAINT IF EXISTS ck_customers_loyalty_nonneg")
    op.execute("ALTER TABLE customers DROP CONSTRAINT IF EXISTS ck_customers_cashback_0_100")
    op.execute("ALTER TABLE customers DROP CONSTRAINT IF EXISTS ck_customers_price_type")
    op.execute("DROP INDEX IF EXISTS ix_customers_company_active")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS deleted_meta")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS is_active")
