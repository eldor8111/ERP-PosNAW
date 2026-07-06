"""merge multiple heads for suppliers and sms logs

Revision ID: b55e026ed7b1
Revises: 616350f873fd, o9p0q1r2s3t4
Create Date: 2026-07-04 09:44:10.850010

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b55e026ed7b1'
down_revision: Union[str, None] = ('616350f873fd', 'o9p0q1r2s3t4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
