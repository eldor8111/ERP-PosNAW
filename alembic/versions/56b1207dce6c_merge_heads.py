"""merge heads

Revision ID: 56b1207dce6c
Revises: b2c3d4e5f6a7, c083c0e9272d
Create Date: 2026-07-01 17:38:34.003127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '56b1207dce6c'
down_revision: Union[str, None] = ('b2c3d4e5f6a7', 'c083c0e9272d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
