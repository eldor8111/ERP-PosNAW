"""Add wholesale_price to products

Revision ID: a1b2c3d4e5f6
Revises: 3417c59a5ce9
Create Date: 2026-03-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '3417c59a5ce9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('wholesale_price', sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'wholesale_price')
