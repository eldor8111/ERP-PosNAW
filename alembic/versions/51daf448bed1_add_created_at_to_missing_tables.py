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


def upgrade() -> None:
    # Add created_at column to customers table
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE customers SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE customers ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to wallets table
    op.execute("ALTER TABLE wallets ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE wallets SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE wallets ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to branches table
    op.execute("ALTER TABLE branches ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE branches SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE branches ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to products table
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE products SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE products ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to purchase_orders table
    op.execute("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE purchase_orders SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE purchase_orders ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to users table
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE users SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to categories table
    op.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE categories SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE categories ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to tariffs table
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE tariffs SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE tariffs ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to customer_prices table
    op.execute("ALTER TABLE customer_prices ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE customer_prices SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE customer_prices ALTER COLUMN created_at SET NOT NULL")
    
    # Add created_at column to suppliers table
    op.execute("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE suppliers SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE suppliers ALTER COLUMN created_at SET NOT NULL")


def downgrade() -> None:
    op.drop_column('suppliers', 'created_at')
    op.drop_column('customer_prices', 'created_at')
    op.drop_column('tariffs', 'created_at')
    op.drop_column('categories', 'created_at')
    op.drop_column('users', 'created_at')
    op.drop_column('purchase_orders', 'created_at')
    op.drop_column('products', 'created_at')
    op.drop_column('branches', 'created_at')
    op.drop_column('wallets', 'created_at')
    op.drop_column('customers', 'created_at')
