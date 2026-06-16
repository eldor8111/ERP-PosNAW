"""add_wholesale_currency_to_products

Revision ID: c083c0e9272d
Revises: a1b2c3d5e6f7
Create Date: 2026-06-16 11:13:10.163573

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c083c0e9272d'
down_revision: Union[str, None] = 'a1b2c3d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('wholesale_currency', sa.String(length=3), server_default='UZS', nullable=False))


def downgrade() -> None:
    op.drop_column('products', 'wholesale_currency')
