"""merge_heads

Revision ID: 4d0797e31e56
Revises: 6eedca5e439f, l6m7n8o9p0q1
Create Date: 2026-06-06 14:34:42.637538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4d0797e31e56'
down_revision: Union[str, None] = ('6eedca5e439f', 'l6m7n8o9p0q1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
