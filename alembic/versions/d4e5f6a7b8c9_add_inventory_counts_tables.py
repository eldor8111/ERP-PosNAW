"""add_inventory_counts_tables

Revision ID: d4e5f6a7b8c9
Revises: aec747063e38
Create Date: 2026-03-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'aec747063e38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'inventory_counts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=30), nullable=False),
        sa.Column('warehouse_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('draft', 'in_progress', 'completed', 'cancelled', name='countstatus'), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['warehouse_id'], ['warehouses.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('number'),
    )
    op.create_index(op.f('ix_inventory_counts_id'), 'inventory_counts', ['id'], unique=False)
    op.create_index(op.f('ix_inventory_counts_number'), 'inventory_counts', ['number'], unique=False)

    op.create_table(
        'inventory_count_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('count_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('system_qty', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('counted_qty', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column('variance', sa.Numeric(precision=12, scale=3), nullable=True),
        sa.ForeignKeyConstraint(['count_id'], ['inventory_counts.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_inventory_count_items_id'), 'inventory_count_items', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_inventory_count_items_id'), table_name='inventory_count_items')
    op.drop_table('inventory_count_items')
    op.drop_index(op.f('ix_inventory_counts_number'), table_name='inventory_counts')
    op.drop_index(op.f('ix_inventory_counts_id'), table_name='inventory_counts')
    op.drop_table('inventory_counts')
    op.execute("DROP TYPE IF EXISTS countstatus")
