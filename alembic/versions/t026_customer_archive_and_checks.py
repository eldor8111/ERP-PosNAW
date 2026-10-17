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
    conn = op.get_bind()

    # 1. Arxivlash ustunlari
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL")
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS deleted_meta JSON NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_company_active ON customers (company_id, is_active)")

    # 2. Ma'lumotni tozalash (CHECK dan oldin)
    r = conn.execute(sa.text(
        "UPDATE customers SET price_type = 'sale' "
        "WHERE price_type IS NULL OR price_type NOT IN ('sale', 'wholesale', 'cost')"
    ))
    log.info(f"[t0_26] price_type 'sale' ga o'tkazildi: {r.rowcount} ta mijoz")
    r = conn.execute(sa.text(
        "UPDATE customers SET cashback_percent = 0 WHERE cashback_percent IS NULL OR cashback_percent < 0"
    ))
    log.info(f"[t0_26] cashback_percent 0 ga tushirildi: {r.rowcount} ta mijoz")
    r = conn.execute(sa.text("UPDATE customers SET cashback_percent = 100 WHERE cashback_percent > 100"))
    log.info(f"[t0_26] cashback_percent 100 ga tushirildi: {r.rowcount} ta mijoz")
    r = conn.execute(sa.text("UPDATE customers SET loyalty_points = 0 WHERE loyalty_points < 0"))
    log.info(f"[t0_26] loyalty_points 0 ga tushirildi: {r.rowcount} ta mijoz")

    # 3. CHECK cheklovlari
    op.create_check_constraint(
        'ck_customers_price_type', 'customers', "price_type IN ('sale', 'wholesale', 'cost')")
    op.create_check_constraint(
        'ck_customers_cashback_0_100', 'customers', "cashback_percent >= 0 AND cashback_percent <= 100")
    op.create_check_constraint(
        'ck_customers_loyalty_nonneg', 'customers', "loyalty_points >= 0")


def downgrade():
    op.drop_constraint('ck_customers_loyalty_nonneg', 'customers', type_='check')
    op.drop_constraint('ck_customers_cashback_0_100', 'customers', type_='check')
    op.drop_constraint('ck_customers_price_type', 'customers', type_='check')
    op.execute("DROP INDEX IF EXISTS ix_customers_company_active")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS deleted_meta")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS is_active")
