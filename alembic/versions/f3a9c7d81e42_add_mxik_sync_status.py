"""Add mxik_sync_status and mxik_synced_at to products

Revision ID: f3a9c7d81e42
Revises: 359daa3436c7
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3a9c7d81e42'
down_revision: Union[str, None] = '359daa3436c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'products',
        sa.Column('mxik_sync_status', sa.String(length=20), nullable=False, server_default='unknown'),
    )
    op.add_column(
        'products',
        sa.Column('mxik_synced_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('products', 'mxik_synced_at')
    op.drop_column('products', 'mxik_sync_status')
