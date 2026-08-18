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
    tables = [
        'sale_items', 'stock_movements', 'stock_levels', 'batches', 
        'sale_item_batches', 'po_items', 'stock_transfer_items', 'inventory_count_items'
    ]
    for table in tables:
        op.execute(f"""
        DO $$
        BEGIN
            ALTER TABLE {table} ALTER COLUMN variant_id SET NOT NULL;
        EXCEPTION
            WHEN not_null_violation THEN
                RAISE NOTICE 'Skipped {table}.variant_id NOT NULL because of existing nulls';
            WHEN undefined_column THEN
                RAISE NOTICE 'Skipped {table} because variant_id does not exist';
        END $$;
        """)

    # 2. Drop deprecated columns 'color' and 'size' from product_variants
    op.execute("ALTER TABLE product_variants DROP COLUMN IF EXISTS color")
    op.execute("ALTER TABLE product_variants DROP COLUMN IF EXISTS size")


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
