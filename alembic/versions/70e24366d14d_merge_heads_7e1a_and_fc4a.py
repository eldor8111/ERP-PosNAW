"""merge heads 7e1a and fc4a

Revision ID: 70e24366d14d
Revises: 7e1a2b3c4d5e, fc4ac3ab5d14
Create Date: 2026-10-11 21:14:33.378419

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '70e24366d14d'
down_revision: Union[str, None] = ('7e1a2b3c4d5e', 'fc4ac3ab5d14')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
