"""add pending to userstatus enum

Revision ID: 7e1a2b3c4d5e
Revises: 5f42fc9c4e27
Create Date: 2026-10-10 13:07:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7e1a2b3c4d5e'
down_revision: Union[str, None] = '5f42fc9c4e27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userstatus ADD VALUE IF NOT EXISTS 'pending'")


def downgrade() -> None:
    pass
