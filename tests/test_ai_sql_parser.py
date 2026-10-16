"""
Tests for AI SQL AST Parser (sqlglot based)
Verifies 40+ attack vectors, bypass tricks, and valid queries.
"""
import pytest
from app.ai.sql_parser import validate_and_sanitize_sql, SQLSecurityError


# ─── 1. ATTACK VECTORS & FORBIDDEN QUERIES (Kamida 40 ta test) ───────────────

@pytest.mark.parametrize(
    "attack_sql, expected_error_substr",
    [
        # 1. Privileged functions & state modifications
        ("SELECT set_config('app.company_id', '2', false)", "set_config"),
        ("SELECT current_setting('app.company_id')", "current_setting"),
        ("SELECT pg_sleep(5)", "pg_sleep"),
        ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
        ("SELECT pg_write_file('/tmp/hacked', 'data')", "pg_write_file"),
        ("SELECT dblink('host=evil.com', 'SELECT 1')", "dblink"),
        ("SELECT query_to_xml('SELECT * FROM users', true, false, '')", "query_to_xml"),
        ("SELECT inet_server_addr()", "inet_server_addr"),

        # 2. Role escalation & session manipulation
        ("RESET ROLE", "RESET ROLE"),
        ("SET ROLE postgres", "SET ROLE"),
        ("SET SESSION AUTHORIZATION postgres", "SET SESSION"),
        ("SET LOCAL app.company_id = '2'", "SET LOCAL"),
        ("SET work_mem = '1GB'", "Set"),

        # 3. Multiple statements & separator tricks
        ("SELECT * FROM ai_v_sales; DROP TABLE products;", "ko'p statement"),
        ("SELECT * FROM ai_v_sales; SELECT * FROM ai_v_products;", "ko'p statement"),
        ("SELECT * FROM ai_v_sales;\nDELETE FROM customers;", "ko'p statement"),
        ("SELECT * FROM ai_v_sales; --\nDROP TABLE sales;", "ko'p statement"),

        # 4. Mutating queries (DML/DDL)
        ("INSERT INTO ai_v_sales DEFAULT VALUES", "Insert"),
        ("UPDATE ai_v_products SET name = 'Hacked'", "Update"),
        ("DELETE FROM ai_v_debts WHERE 1=1", "Delete"),
        ("DROP TABLE products CASCADE", "Drop"),
        ("ALTER TABLE products ADD COLUMN hacked int", "Alter"),
        ("CREATE TABLE evil (id int)", "Create"),

        # 5. Mutating CTEs (WITH ... INSERT/DELETE/UPDATE)
        ("WITH d AS (DELETE FROM products RETURNING *) SELECT * FROM d", "Delete"),
        ("WITH u AS (UPDATE products SET name='h' RETURNING *) SELECT * FROM u", "Update"),
        ("WITH i AS (INSERT INTO users(phone) VALUES('123') RETURNING *) SELECT * FROM i", "Insert"),

        # 6. Raw tables access (Must only access ai_v_*)
        ("SELECT * FROM users", "users"),
        ("SELECT * FROM sales", "sales"),
        ("SELECT * FROM customers", "customers"),
        ("SELECT * FROM products", "products"),
        ("SELECT * FROM stock_movements", "stock_movements"),
        ("SELECT * FROM purchase_orders", "purchase_orders"),
        ("SELECT * FROM wallets", "wallets"),
        ("SELECT * FROM kassa_sessions", "kassa_sessions"),
        ("SELECT * FROM pending_actions", "pending_actions"),

        # 7. System schemas access (pg_catalog, information_schema)
        ("SELECT * FROM pg_catalog.pg_user", "pg_catalog"),
        ("SELECT * FROM pg_catalog.pg_roles", "pg_catalog"),
        ("SELECT * FROM information_schema.tables", "information_schema"),
        ("SELECT * FROM information_schema.columns", "information_schema"),
        ("SELECT * FROM \"pg_catalog\".pg_tables", "pg_catalog"),
        ("SELECT * FROM \"information_schema\".views", "information_schema"),

        # 8. Locking and writing SELECT variants
        ("SELECT * FROM ai_v_products FOR UPDATE", "for update"),
        ("SELECT * FROM ai_v_products FOR SHARE", "for share"),
        ("SELECT * FROM ai_v_products FOR NO KEY UPDATE", "update"),
        ("SELECT * INTO new_table FROM ai_v_products", "into"),

        # 9. Non-whitelisted random/dangerous functions
        ("SELECT chr(65)", "chr"),
        ("SELECT md5('test')", "md5"),
        ("SELECT version()", "version"),
        ("SELECT current_user", "current_user"),
        ("SELECT pg_backend_pid()", "pg_backend_pid"),
    ],
)
def test_sql_parser_rejects_attacks(attack_sql, expected_error_substr):
    with pytest.raises(SQLSecurityError) as exc_info:
        validate_and_sanitize_sql(attack_sql)
    assert expected_error_substr.lower() in str(exc_info.value).lower()


# ─── 2. VALID QUERIES & LIMIT ENFORCEMENT ─────────────────────────────────────

def test_sql_parser_allows_simple_select():
    sql = "SELECT id, total_amount FROM ai_v_sales WHERE total_amount > 1000"
    sanitized = validate_and_sanitize_sql(sql)
    assert "FROM ai_v_sales" in sanitized
    assert "LIMIT 200" in sanitized


def test_sql_parser_allows_aggregations_and_group_by():
    sql = """
    SELECT 
        customer_name, 
        COUNT(*) AS total_count, 
        SUM(total_amount) AS total_sales,
        AVG(total_amount) AS avg_sale,
        MIN(total_amount) AS min_sale,
        MAX(total_amount) AS max_sale
    FROM ai_v_sales
    GROUP BY customer_name
    HAVING COUNT(*) > 1
    ORDER BY total_sales DESC
    """
    sanitized = validate_and_sanitize_sql(sql)
    assert "GROUP BY" in sanitized
    assert "SUM" in sanitized
    assert "LIMIT 200" in sanitized


def test_sql_parser_allows_allowed_scalar_functions():
    sql = """
    SELECT 
        LOWER(name) AS lower_name,
        UPPER(name) AS upper_name,
        TRIM(name) AS trimmed_name,
        ROUND(selling_price, 2) AS rounded_price,
        COALESCE(category_name, 'None') AS cat,
        NULLIF(sku, '') AS safe_sku
    FROM ai_v_products
    """
    sanitized = validate_and_sanitize_sql(sql)
    assert "ai_v_products" in sanitized
    assert "LIMIT 200" in sanitized


def test_sql_parser_allows_date_functions():
    sql = """
    SELECT 
        DATE_TRUNC('month', created_at) AS sale_month,
        SUM(total_amount) AS monthly_sales
    FROM ai_v_sales
    WHERE created_at >= NOW() - INTERVAL '30 days'
    GROUP BY DATE_TRUNC('month', created_at)
    """
    sanitized = validate_and_sanitize_sql(sql)
    assert "DATE_TRUNC" in sanitized
    assert "LIMIT 200" in sanitized


def test_sql_parser_allows_pure_select_cte():
    sql = """
    WITH big_sales AS (
        SELECT * FROM ai_v_sales WHERE total_amount > 500000
    )
    SELECT customer_name, SUM(total_amount) FROM big_sales GROUP BY customer_name
    """
    sanitized = validate_and_sanitize_sql(sql)
    assert "WITH big_sales AS" in sanitized
    assert "LIMIT 200" in sanitized


def test_sql_parser_enforces_limit_clamping():
    # If user specifies LIMIT 500, it must be clamped down to max_limit (200)
    sql = "SELECT * FROM ai_v_customers LIMIT 500"
    sanitized = validate_and_sanitize_sql(sql, max_limit=200)
    assert "LIMIT 200" in sanitized

    # If user specifies LIMIT 50 (< 200), keep 50
    sql_low = "SELECT * FROM ai_v_customers LIMIT 50"
    sanitized_low = validate_and_sanitize_sql(sql_low, max_limit=200)
    assert "LIMIT 50" in sanitized_low


def test_sql_parser_rejects_empty_and_whitespace():
    with pytest.raises(SQLSecurityError):
        validate_and_sanitize_sql("")
    with pytest.raises(SQLSecurityError):
        validate_and_sanitize_sql("   \n\t  ")
