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

        -- PostgreSQL da number ustuniga bog'langan barcha semantik ko'rinishlarni
        -- vaqtincha DROP qilib, ustunlar kengaytirilgach to'liq qayta yaratamiz.
        DROP VIEW IF EXISTS ai_v_returns CASCADE;
        DROP VIEW IF EXISTS ai_v_purchases CASCADE;
        DROP VIEW IF EXISTS ai_v_stock_movements CASCADE;
        DROP VIEW IF EXISTS ai_v_stock_balance CASCADE;
        DROP VIEW IF EXISTS ai_v_debts CASCADE;
        DROP VIEW IF EXISTS ai_v_customers CASCADE;
        DROP VIEW IF EXISTS ai_v_products CASCADE;
        DROP VIEW IF EXISTS ai_v_sale_items CASCADE;
        DROP VIEW IF EXISTS ai_v_sales CASCADE;

        ALTER TABLE sales ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE stock_transfers ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE inventory_counts ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE production_orders ALTER COLUMN number TYPE VARCHAR(40);
        ALTER TABLE purchase_orders ALTER COLUMN number TYPE VARCHAR(40);

        -- 1. ai_v_sales
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

        -- 2. ai_v_sale_items
        CREATE OR REPLACE VIEW ai_v_sale_items AS
        SELECT
            si.id,
            s.company_id,
            si.sale_id,
            s.number AS sale_number,
            si.product_id,
            p.name AS product_name,
            p.sku,
            p.barcode,
            si.quantity,
            si.unit_price,
            si.cost_price,
            si.subtotal AS total_price,
            COALESCE(cur.code, 'UZS') AS currency,
            s.created_at
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        LEFT JOIN products p ON si.product_id = p.id
        LEFT JOIN currencies cur ON s.currency_id = cur.id
        WHERE s.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        -- 3. ai_v_products
        CREATE OR REPLACE VIEW ai_v_products AS
        SELECT
            p.id,
            p.company_id,
            p.name,
            p.sku,
            p.barcode,
            p.unit,
            p.sale_price,
            p.sale_currency,
            p.cost_price,
            p.cost_currency,
            p.wholesale_price,
            p.wholesale_currency,
            p.status,
            p.created_at
        FROM products p
        WHERE p.is_deleted = false
          AND p.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        -- 4. ai_v_customers
        CREATE OR REPLACE VIEW ai_v_customers AS
        SELECT
            c.id,
            c.company_id,
            c.name,
            c.phone,
            c.debt_balance,
            c.debt_balances,
            c.created_at
        FROM customers c
        WHERE c.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        -- 5. ai_v_debts
        CREATE OR REPLACE VIEW ai_v_debts AS
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

        -- 6. ai_v_stock_balance
        CREATE OR REPLACE VIEW ai_v_stock_balance AS
        SELECT
            sl.id,
            p.company_id,
            sl.product_id,
            p.name AS product_name,
            p.sku,
            p.barcode,
            p.unit,
            sl.warehouse_id,
            w.name AS warehouse_name,
            sl.quantity,
            SUM(sl.quantity) OVER (PARTITION BY p.company_id, sl.product_id) AS total_quantity,
            p.sale_price,
            p.sale_currency,
            p.cost_price,
            p.cost_currency,
            (sl.quantity * p.cost_price) AS total_cost_value
        FROM stock_levels sl
        JOIN products p ON sl.product_id = p.id
        LEFT JOIN warehouses w ON sl.warehouse_id = w.id
        WHERE p.is_deleted = false
          AND p.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        -- 7. ai_v_stock_movements
        CREATE OR REPLACE VIEW ai_v_stock_movements AS
        SELECT
            sm.id,
            p.company_id,
            sm.product_id,
            p.name AS product_name,
            p.barcode,
            p.sku,
            sm.warehouse_id,
            w.name AS warehouse_name,
            sm.type AS movement_type,
            CASE
                WHEN sm.reference_type = 'sale' AND s.number LIKE 'R%' THEN 'qaytarish'
                WHEN sm.reference_type = 'sale' THEN 'sotuv'
                WHEN sm.reference_type IN ('purchase', 'purchase_order') THEN 'xarid'
                WHEN sm.reference_type = 'transfer' THEN 'ko''chirish'
                WHEN sm.reference_type IN ('inventory', 'inventory_count') THEN 'inventarizatsiya'
                WHEN sm.type = 'RETURN' THEN 'qaytarish'
                ELSE COALESCE(sm.reference_type, sm.type::text)
            END AS document_type,
            COALESCE(s.number, po.number, tr.number, inv.number, sm.reference_id::text) AS document_number,
            COALESCE(c.name, sup.name, '') AS counterparty,
            sm.qty_before,
            sm.qty_after,
            sm.quantity,
            CASE 
                WHEN sm.type IN ('OUT', 'TRANSFER_OUT') THEN -ABS(sm.quantity)
                ELSE ABS(sm.quantity)
            END AS signed_quantity,
            SUM(
                CASE 
                    WHEN sm.type IN ('OUT', 'TRANSFER_OUT') THEN -ABS(sm.quantity)
                    ELSE ABS(sm.quantity)
                END
            ) OVER (
                PARTITION BY p.company_id, sm.product_id, sm.warehouse_id 
                ORDER BY sm.created_at ASC, sm.id ASC
            ) AS running_balance,
            sm.reference_type,
            sm.reference_id,
            sm.reason,
            sm.created_at
        FROM stock_movements sm
        JOIN products p ON sm.product_id = p.id
        LEFT JOIN warehouses w ON sm.warehouse_id = w.id
        LEFT JOIN sales s ON sm.reference_type = 'sale' AND sm.reference_id = s.id
        LEFT JOIN customers c ON s.customer_id = c.id
        LEFT JOIN purchase_orders po ON sm.reference_type IN ('purchase', 'purchase_order') AND sm.reference_id = po.id
        LEFT JOIN suppliers sup ON po.supplier_id = sup.id
        LEFT JOIN stock_transfers tr ON sm.reference_type = 'transfer' AND sm.reference_id = tr.id
        LEFT JOIN inventory_counts inv ON sm.reference_type IN ('inventory', 'inventory_count') AND sm.reference_id = inv.id
        WHERE p.is_deleted = false
          AND p.company_id = NULLIF(current_setting('app.company_id', true), '')::integer;

        -- 8. ai_v_purchases
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

        -- 9. ai_v_returns
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

        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_view_owner') THEN
                ALTER VIEW ai_v_sales OWNER TO ai_view_owner;
                ALTER VIEW ai_v_sale_items OWNER TO ai_view_owner;
                ALTER VIEW ai_v_products OWNER TO ai_view_owner;
                ALTER VIEW ai_v_customers OWNER TO ai_view_owner;
                ALTER VIEW ai_v_debts OWNER TO ai_view_owner;
                ALTER VIEW ai_v_stock_balance OWNER TO ai_view_owner;
                ALTER VIEW ai_v_stock_movements OWNER TO ai_view_owner;
                ALTER VIEW ai_v_purchases OWNER TO ai_view_owner;
                ALTER VIEW ai_v_returns OWNER TO ai_view_owner;
            END IF;
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_readonly') THEN
                GRANT SELECT ON ai_v_sales TO ai_readonly;
                GRANT SELECT ON ai_v_sale_items TO ai_readonly;
                GRANT SELECT ON ai_v_products TO ai_readonly;
                GRANT SELECT ON ai_v_customers TO ai_readonly;
                GRANT SELECT ON ai_v_debts TO ai_readonly;
                GRANT SELECT ON ai_v_stock_balance TO ai_readonly;
                GRANT SELECT ON ai_v_stock_movements TO ai_readonly;
                GRANT SELECT ON ai_v_purchases TO ai_readonly;
                GRANT SELECT ON ai_v_returns TO ai_readonly;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END $$;
    """)


def downgrade() -> None:
    # Ataylab bo'sh: raqamlarni qisqartirish yangi formatdagi hujjatlarni buzadi,
    # hisoblagich jadvalini o'chirish esa raqamlarning takrorlanishiga olib keladi.
    pass
