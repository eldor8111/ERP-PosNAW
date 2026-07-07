"""add_created_at_to_stock_levels

Revision ID: 0b8b6c7b6d35
Revises: 51daf448bed1
Create Date: 2026-07-07 16:42:18.840732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0b8b6c7b6d35'
down_revision: Union[str, None] = '51daf448bed1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE stock_levels ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE")
    op.execute("UPDATE stock_levels SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("ALTER TABLE stock_levels ALTER COLUMN created_at SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE stock_levels DROP COLUMN IF EXISTS created_at")
