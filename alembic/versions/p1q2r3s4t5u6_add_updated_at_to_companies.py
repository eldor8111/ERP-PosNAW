"""add updated_at to companies

Revision ID: p1q2r3s4t5u6
Revises: o9p0q1r2s3t4
Create Date: 2026-07-07

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'p1q2r3s4t5u6'
down_revision: Union[str, None] = '44b8ebad9615'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add updated_at column to companies table
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE companies SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE companies ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to customers table
    op.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE customers SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE customers ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to wallets table
    op.execute("ALTER TABLE wallets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE wallets SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE wallets ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to branches table
    op.execute("ALTER TABLE branches ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE branches SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE branches ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to products table
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE products SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE products ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to purchase_orders table
    op.execute("ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE purchase_orders SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE purchase_orders ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to users table
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE users SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to categories table
    op.execute("ALTER TABLE categories ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE categories SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE categories ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to tariffs table
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE tariffs SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE tariffs ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to customer_prices table
    op.execute("ALTER TABLE customer_prices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE customer_prices SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE customer_prices ALTER COLUMN updated_at SET NOT NULL")
    
    # Add updated_at column to suppliers table
    op.execute("ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE suppliers SET updated_at = NOW() WHERE updated_at IS NULL")
    op.execute("ALTER TABLE suppliers ALTER COLUMN updated_at SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE suppliers DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE customer_prices DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE categories DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE purchase_orders DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE branches DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE wallets DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS updated_at")
