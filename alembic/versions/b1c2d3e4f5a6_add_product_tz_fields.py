"""Add product TZ fields: bin_location, image_url, weight, dimensions

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('bin_location', sa.String(100), nullable=True))
    op.add_column('products', sa.Column('image_url', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('weight', sa.Numeric(10, 3), nullable=True))
    op.add_column('products', sa.Column('dimensions', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'dimensions')
    op.drop_column('products', 'weight')
    op.drop_column('products', 'image_url')
    op.drop_column('products', 'bin_location')
