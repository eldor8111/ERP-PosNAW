"""Merge multiple heads into one

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9, 7af6f5dacd20
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa
from typing import Union

# revision identifiers
revision = 't5u6v7w8x9y0'
down_revision: Union[str, None] = ('s4t5u6v7w8x9', '7af6f5dacd20')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
