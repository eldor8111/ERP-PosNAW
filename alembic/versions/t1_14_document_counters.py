"""T1.14 — hujjat raqamlari hisoblagichi (document_counters) va number ustunlarini kengaytirish

Revision ID: t1_14
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_14'
down_revision: Union[str, None] = 't1_13b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Startup'dagi _create_missing_tables jadvalni oldin yaratgan bo'lishi mumkin — IF NOT EXISTS
    op.execute("""
        CREATE TABLE IF NOT EXISTS document_counters (
            company_id INTEGER NOT NULL REFERENCES companies(id),
            branch_id  INTEGER NOT NULL DEFAULT 0,
            doc_type   VARCHAR(8) NOT NULL,
            period     VARCHAR(8) NOT NULL,
            last_value INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (company_id, branch_id, doc_type, period)
        );

        -- PostgreSQL da number ustuniga bog'langan ai_v_sales, ai_v_returns, ai_v_purchases
        -- ko'rinishlari DROP qilinmasa ALTER COLUMN TYPE xato beradi.
        DROP VIEW IF EXISTS ai_v_sales CASCADE;
        DROP VIEW IF EXISTS ai_v_returns CASCADE;
        DROP VIEW IF EXISTS ai_v_purchases CASCADE;

        ALTER TABLE sales ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE stock_transfers ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE inventory_counts ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE production_orders ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE purchase_orders ALTER COLUMN number TYPE VARCHAR(40);

        CREATE OR REPLACE VIEW ai_v_sales AS
        SELECT
            s.id,
            s.company_id,
            s.number,
            s.status,
            s.payment_type,
            s.total_amount,
            s.discount_amount,
            s.paid_cash,
            s.paid_card,
            COALESCE(cur.code, 'UZS') AS currency,
            s.customer_id,
            c.name AS customer_name,
            s.created_at
        FROM sales s
        LEFT JOIN customers c ON s.customer_id = c.id
        LEFT JOIN currencies cur ON s.currency_id = cur.id
        WHERE (s.number NOT LIKE 'R%' AND s.status != 'cancelled' AND s.status != 'refunded')
          AND s.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        CREATE OR REPLACE VIEW ai_v_returns AS
        SELECT
            s.id,
            s.company_id,
            s.number,
            s.total_amount,
            COALESCE(cur.code, 'UZS') AS currency,
            s.status,
            s.customer_id,
            c.name AS customer_name,
            s.created_at
        FROM sales s
        LEFT JOIN customers c ON s.customer_id = c.id
        LEFT JOIN currencies cur ON s.currency_id = cur.id
        WHERE (s.number LIKE 'R%' OR s.status = 'refunded')
          AND s.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        CREATE OR REPLACE VIEW ai_v_purchases AS
        SELECT
            po.id,
            po.company_id,
            po.number AS po_number,
            po.supplier_id,
            s.name AS supplier_name,
            po.status,
            po.total_amount,
            po.paid_amount,
            po.supplier_debt,
            COALESCE(po.currency, 'UZS') AS currency,
            po.created_at
        FROM purchase_orders po
        LEFT JOIN suppliers s ON po.supplier_id = s.id
        WHERE po.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_view_owner') THEN
                ALTER VIEW ai_v_sales OWNER TO ai_view_owner;
                ALTER VIEW ai_v_returns OWNER TO ai_view_owner;
                ALTER VIEW ai_v_purchases OWNER TO ai_view_owner;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_readonly') THEN
                GRANT SELECT ON ai_v_sales TO ai_readonly;
                GRANT SELECT ON ai_v_returns TO ai_readonly;
                GRANT SELECT ON ai_v_purchases TO ai_readonly;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)


def downgrade() -> None:
    # Ataylab bo'sh: raqamlarni qisqartirish yangi formatdagi hujjatlarni buzadi,
    # hisoblagich jadvalini o'chirish esa raqamlarning takrorlanishiga olib keladi.
    pass
