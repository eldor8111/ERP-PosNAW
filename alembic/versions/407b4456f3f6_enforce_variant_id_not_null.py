"""enforce_variant_id_not_null

Revision ID: 407b4456f3f6
Revises: f8d0a8c76f91
Create Date: 2026-08-13 14:23:52.805930

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '407b4456f3f6'
down_revision: Union[str, None] = 'f8d0a8c76f91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enforce NOT NULL on variant_id for transactional tables
    op.alter_column('sale_items', 'variant_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('stock_movements', 'variant_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('stock_levels', 'variant_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('batches', 'variant_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('sale_item_batches', 'variant_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('po_items', 'variant_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('stock_transfer_items', 'variant_id', existing_type=sa.Integer(), nullable=False)
    op.alter_column('inventory_count_items', 'variant_id', existing_type=sa.Integer(), nullable=False)

    # 2. Drop deprecated columns 'color' and 'size' from product_variants
    op.drop_column('product_variants', 'color')
    op.drop_column('product_variants', 'size')


def downgrade() -> None:
    # Add back columns
    op.add_column('product_variants', sa.Column('color', sa.String(length=50), nullable=True))
    op.add_column('product_variants', sa.Column('size', sa.String(length=50), nullable=True))
    
    # Remove NOT NULL
    op.alter_column('inventory_count_items', 'variant_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('stock_transfer_items', 'variant_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('po_items', 'variant_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('sale_item_batches', 'variant_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('batches', 'variant_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('stock_levels', 'variant_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('stock_movements', 'variant_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column('sale_items', 'variant_id', existing_type=sa.Integer(), nullable=True)
