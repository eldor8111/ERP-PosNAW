"""merge_heads_before_mxik

Revision ID: 2e4c73ca0e32
Revises: a1d57e714b04, fa56aaa5e6f4
Create Date: 2026-06-11 11:46:21.162297

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2e4c73ca0e32'
down_revision: Union[str, None] = ('a1d57e714b04', 'fa56aaa5e6f4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
