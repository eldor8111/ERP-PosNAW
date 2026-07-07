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
    op.add_column('companies', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE companies SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('companies', 'updated_at', nullable=False)
    
    # Add updated_at column to customers table
    op.add_column('customers', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE customers SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('customers', 'updated_at', nullable=False)
    
    # Add updated_at column to wallets table
    op.add_column('wallets', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE wallets SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('wallets', 'updated_at', nullable=False)
    
    # Add updated_at column to inventory table
    op.add_column('inventory', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE inventory SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('inventory', 'updated_at', nullable=False)
    
    # Add updated_at column to branches table
    op.add_column('branches', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE branches SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('branches', 'updated_at', nullable=False)
    
    # Add updated_at column to products table
    op.add_column('products', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE products SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('products', 'updated_at', nullable=False)
    
    # Add updated_at column to purchase_orders table
    op.add_column('purchase_orders', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE purchase_orders SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('purchase_orders', 'updated_at', nullable=False)
    
    # Add updated_at column to users table
    op.add_column('users', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('users', 'updated_at', nullable=False)
    
    # Add updated_at column to categories table
    op.add_column('categories', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE categories SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('categories', 'updated_at', nullable=False)
    
    # Add updated_at column to tariffs table
    op.add_column('tariffs', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE tariffs SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('tariffs', 'updated_at', nullable=False)
    
    # Add updated_at column to company_subscriptions table
    op.add_column('company_subscriptions', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE company_subscriptions SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('company_subscriptions', 'updated_at', nullable=False)
    
    # Add updated_at column to customer_prices table
    op.add_column('customer_prices', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE customer_prices SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('customer_prices', 'updated_at', nullable=False)
    
    # Add updated_at column to suppliers table
    op.add_column('suppliers', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE suppliers SET updated_at = created_at WHERE updated_at IS NULL")
    op.alter_column('suppliers', 'updated_at', nullable=False)


def downgrade() -> None:
    op.drop_column('suppliers', 'updated_at')
    op.drop_column('customer_prices', 'updated_at')
    op.drop_column('company_subscriptions', 'updated_at')
    op.drop_column('tariffs', 'updated_at')
    op.drop_column('categories', 'updated_at')
    op.drop_column('users', 'updated_at')
    op.drop_column('purchase_orders', 'updated_at')
    op.drop_column('products', 'updated_at')
    op.drop_column('branches', 'updated_at')
    op.drop_column('inventory', 'updated_at')
    op.drop_column('wallets', 'updated_at')
    op.drop_column('customers', 'updated_at')
    op.drop_column('companies', 'updated_at')
