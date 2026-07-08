"""add_created_at_to_missing_tables

Revision ID: 51daf448bed1
Revises: 7af6f5dacd20
Create Date: 2026-07-07 12:00:52.276747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '51daf448bed1'
down_revision: Union[str, None] = '7af6f5dacd20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES_CREATED_AT = [
    'customers', 'wallets', 'branches', 'products', 'purchase_orders',
    'users', 'categories', 'tariffs', 'customer_prices', 'suppliers',
    'balance_logs', 'stock_levels', 'stock_movements', 'inventory_counts',
    'kassa_sessions', 'expenses', 'incomes', 'wallet_movements',
    'bot_sessions', 'sales', 'bin_locations', 'api_keys',
]

TABLES_UPDATED_AT = ['balance_logs', 'stock_levels', 'kassa_sessions']


def upgrade() -> None:
    conn = op.get_bind()

    for table in TABLES_CREATED_AT:
        exists = conn.execute(sa.text(f"SELECT to_regclass('{table}')")).scalar()
        if not exists:
            continue
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
        op.execute(f"UPDATE {table} SET created_at = NOW() WHERE created_at IS NULL")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN created_at SET NOT NULL")

    for table in TABLES_UPDATED_AT:
        exists = conn.execute(sa.text(f"SELECT to_regclass('{table}')")).scalar()
        if not exists:
            continue
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
        op.execute(f"UPDATE {table} SET updated_at = NOW() WHERE updated_at IS NULL")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN updated_at SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE bin_locations DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE bot_sessions DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE wallet_movements DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE incomes DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE kassa_sessions DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE kassa_sessions DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE inventory_counts DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE stock_movements DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE stock_levels DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE stock_levels DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE balance_logs DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE balance_logs DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE suppliers DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE customer_prices DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE categories DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE purchase_orders DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE branches DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE wallets DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS created_at")
