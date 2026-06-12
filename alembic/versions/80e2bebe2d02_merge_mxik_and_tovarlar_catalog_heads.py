"""merge_mxik_and_tovarlar_catalog_heads

Revision ID: 80e2bebe2d02
Revises: 191cf33ddce8, n8o9p0q1r2s3
Create Date: 2026-06-12 18:10:38.406374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '80e2bebe2d02'
down_revision: Union[str, None] = ('191cf33ddce8', 'n8o9p0q1r2s3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
