"""bosqich4_ai_sql_ro_and_views_hardening

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-16 19:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    # 1. ai_sql_ro LOGIN rolini yaratish va xavfsizlik sozlamalari (agar huquq bo'lsa)
    conn.execute(sa.text("""
        DO $$
        BEGIN
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_sql_ro') THEN
                    CREATE ROLE ai_sql_ro WITH LOGIN PASSWORD 'ai_sql_ro_pass' NOSUPERUSER NOBYPASSRLS NOINHERIT;
                ELSE
                    ALTER ROLE ai_sql_ro WITH LOGIN PASSWORD 'ai_sql_ro_pass' NOSUPERUSER NOBYPASSRLS NOINHERIT;
                END IF;

                ALTER ROLE ai_sql_ro SET default_transaction_read_only = on;
                ALTER ROLE ai_sql_ro SET statement_timeout = '10s';
                ALTER ROLE ai_sql_ro SET idle_in_transaction_session_timeout = '10s';

                REVOKE ALL ON SCHEMA public FROM ai_sql_ro;
                GRANT USAGE ON SCHEMA public TO ai_sql_ro;
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ai_sql_ro;
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'Skipping ai_sql_ro role setup: %', SQLERRM;
            END;
        END $$;
    """))

    # 2. set_config EXECUTE huquqini PUBLIC'dan bekor qilish
    conn.execute(sa.text("""
        DO $$
        BEGIN
            BEGIN
                REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ecode_app') THEN
                    GRANT EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) TO ecode_app;
                END IF;
                IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_readonly') THEN
                    GRANT EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) TO ai_readonly;
                END IF;
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'Skipping set_config revoke/grant: %', SQLERRM;
            END;
        END $$;
    """))

    # 3. ecode_app roli uchun qolgan 5 ta jadvalda RLS transit siyosatlari
    conn.execute(sa.text("""
        DROP POLICY IF EXISTS rls_app_warehouses ON warehouses;
        CREATE POLICY rls_app_warehouses ON warehouses TO ecode_app
            USING (NULLIF(current_setting('app.company_id', true), '') IS NULL OR company_id = NULLIF(current_setting('app.company_id', true), '')::integer)
            WITH CHECK (NULLIF(current_setting('app.company_id', true), '') IS NULL OR company_id = NULLIF(current_setting('app.company_id', true), '')::integer);

        DROP POLICY IF EXISTS rls_app_suppliers ON suppliers;
        CREATE POLICY rls_app_suppliers ON suppliers TO ecode_app
            USING (NULLIF(current_setting('app.company_id', true), '') IS NULL OR company_id = NULLIF(current_setting('app.company_id', true), '')::integer)
            WITH CHECK (NULLIF(current_setting('app.company_id', true), '') IS NULL OR company_id = NULLIF(current_setting('app.company_id', true), '')::integer);

        DROP POLICY IF EXISTS rls_app_sale_items ON sale_items;
        CREATE POLICY rls_app_sale_items ON sale_items TO ecode_app
            USING (NULLIF(current_setting('app.company_id', true), '') IS NULL OR EXISTS (SELECT 1 FROM sales WHERE sales.id = sale_items.sale_id AND sales.company_id = NULLIF(current_setting('app.company_id', true), '')::integer))
            WITH CHECK (NULLIF(current_setting('app.company_id', true), '') IS NULL OR EXISTS (SELECT 1 FROM sales WHERE sales.id = sale_items.sale_id AND sales.company_id = NULLIF(current_setting('app.company_id', true), '')::integer));

        DROP POLICY IF EXISTS rls_app_stock_levels ON stock_levels;
        CREATE POLICY rls_app_stock_levels ON stock_levels TO ecode_app
            USING (NULLIF(current_setting('app.company_id', true), '') IS NULL OR EXISTS (SELECT 1 FROM products WHERE products.id = stock_levels.product_id AND products.company_id = NULLIF(current_setting('app.company_id', true), '')::integer))
            WITH CHECK (NULLIF(current_setting('app.company_id', true), '') IS NULL OR EXISTS (SELECT 1 FROM products WHERE products.id = stock_levels.product_id AND products.company_id = NULLIF(current_setting('app.company_id', true), '')::integer));

        DROP POLICY IF EXISTS rls_app_stock_movements ON stock_movements;
        CREATE POLICY rls_app_stock_movements ON stock_movements TO ecode_app
            USING (NULLIF(current_setting('app.company_id', true), '') IS NULL OR EXISTS (SELECT 1 FROM products WHERE products.id = stock_movements.product_id AND products.company_id = NULLIF(current_setting('app.company_id', true), '')::integer))
            WITH CHECK (NULLIF(current_setting('app.company_id', true), '') IS NULL OR EXISTS (SELECT 1 FROM products WHERE products.id = stock_movements.product_id AND products.company_id = NULLIF(current_setting('app.company_id', true), '')::integer));
    """))

    # 4. ai_v_debts ko'rinishini ko'p valyutali qilib yangilash
    conn.execute(sa.text("""
        DROP VIEW IF EXISTS ai_v_debts;
        CREATE VIEW ai_v_debts AS
        SELECT 
            c.id AS customer_id,
            c.company_id,
            c.name AS customer_name,
            c.phone,
            UPPER(j.key) AS currency,
            ROUND(j.value::numeric, 2) AS debt_amount,
            ROUND(j.value::numeric, 2) AS debt_balance
        FROM customers c,
        LATERAL jsonb_each_text(
            CASE 
                WHEN c.debt_balances IS NOT NULL AND c.debt_balances::text NOT IN ('{}', 'null', '') 
                THEN c.debt_balances::jsonb
                ELSE jsonb_build_object(COALESCE(NULLIF(TRIM(c.debt_currency), ''), 'UZS'), COALESCE(c.debt_balance, 0))
            END
        ) AS j(key, value)
        WHERE (c.company_id = NULLIF(current_setting('app.company_id', true), '')::integer)
          AND (j.value::numeric > 0.009);

        ALTER VIEW ai_v_debts OWNER TO ai_view_owner;
    """))

    # 5. ai_v_returns ko'rinishini aniq qoidalar bilan yangilash
    conn.execute(sa.text("""
        DROP VIEW IF EXISTS ai_v_returns;
        CREATE VIEW ai_v_returns AS
        SELECT 
            s.id AS return_id,
            s.company_id,
            s.number AS return_number,
            s.created_at,
            s.warehouse_id,
            w.name AS warehouse_name,
            s.customer_id,
            c.name AS customer_name,
            s.total_amount,
            s.payment_type,
            s.status,
            s.note
        FROM sales s
        LEFT JOIN warehouses w ON s.warehouse_id = w.id
        LEFT JOIN customers c ON s.customer_id = c.id
        WHERE (s.number LIKE 'R%' AND s.status = 'refunded' AND s.status != 'cancelled')
          AND (s.company_id = NULLIF(current_setting('app.company_id', true), '')::integer);

        ALTER VIEW ai_v_returns OWNER TO ai_view_owner;
    """))

    # 6. Unumdorlik indekslari (stock_movements)
    conn.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_stock_movements_prod_wh_created 
            ON stock_movements (product_id, warehouse_id, created_at, id);
        CREATE INDEX IF NOT EXISTS ix_stock_movements_product_id 
            ON stock_movements (product_id);
    """))

    # 7. ai_v_* ko'rinishlariga huquqlarni berish
    conn.execute(sa.text("""
        GRANT SELECT ON ai_v_sales TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_sale_items TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_stock_balance TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_stock_movements TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_debts TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_customers TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_products TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_purchases TO ai_sql_ro, ai_readonly;
        GRANT SELECT ON ai_v_returns TO ai_sql_ro, ai_readonly;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        return

    conn.execute(sa.text("""
        DROP INDEX IF EXISTS ix_stock_movements_prod_wh_created;
        DROP INDEX IF EXISTS ix_stock_movements_product_id;
        REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM ai_sql_ro;
        DROP ROLE IF EXISTS ai_sql_ro;
    """))
