"""Merge heads

Revision ID: ea80a7fba213
Revises: a1c2u3w4x5y6, change_loyalty_points_to_bigint, v7w8x9y0z1a2
Create Date: 2026-08-09 17:43:16.483145

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ea80a7fba213'
down_revision: Union[str, None] = ('a1c2u3w4x5y6', 'change_loyalty_points_to_bigint', 'v7w8x9y0z1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
