"""Add bin_locations table and products.images column

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-03-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'bin_locations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_bin_locations_id', 'bin_locations', ['id'])
    op.create_index('ix_bin_locations_code', 'bin_locations', ['code'], unique=True)

    op.add_column('products', sa.Column('images', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'images')
    op.drop_index('ix_bin_locations_code', table_name='bin_locations')
    op.drop_index('ix_bin_locations_id', table_name='bin_locations')
    op.drop_table('bin_locations')
