"""make barcode sku unique per company

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-05-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'j4k5l6m7n8o9'
down_revision = 'i3j4k5l6m7n8'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop old constraints
    op.drop_index('uq_products_barcode_active', table_name='products')
    op.drop_index('uq_products_sku_active', table_name='products')
    
    # 2. Create new constraints (with company_id)
    op.create_index('uq_products_barcode_active', 'products', ['company_id', 'barcode'], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index('uq_products_sku_active', 'products', ['company_id', 'sku'], unique=True, postgresql_where=sa.text("is_deleted = false"))


def downgrade():
    # 1. Drop new constraints
    op.drop_index('uq_products_barcode_active', table_name='products')
    op.drop_index('uq_products_sku_active', table_name='products')
    
    # 2. Re-create old constraints (global)
    op.create_index('uq_products_barcode_active', 'products', ['barcode'], unique=True, postgresql_where=sa.text("is_deleted = false"))
    op.create_index('uq_products_sku_active', 'products', ['sku'], unique=True, postgresql_where=sa.text("is_deleted = false"))
