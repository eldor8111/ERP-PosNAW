"""Add requires_marking to products and marking_codes to sale_items

Revision ID: c7d4e8f21a90
Revises: f3a9c7d81e42
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c7d4e8f21a90'
down_revision: Union[str, None] = 'f3a9c7d81e42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'products',
        sa.Column('requires_marking', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'sale_items',
        sa.Column('marking_codes', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('sale_items', 'marking_codes')
    op.drop_column('products', 'requires_marking')
