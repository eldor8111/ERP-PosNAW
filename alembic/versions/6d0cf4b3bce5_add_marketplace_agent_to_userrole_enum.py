"""add marketplace_agent to userrole enum

Revision ID: 6d0cf4b3bce5
Revises: fc4ac3ab5d13
Create Date: 2026-10-10 11:15:04.321563

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6d0cf4b3bce5'
down_revision: Union[str, None] = 'fc4ac3ab5d13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL to add enum value to userrole if it doesn't exist
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'marketplace_agent'")

def downgrade() -> None:
    # PostgreSQL doesn't support dropping enum values easily, so we usually leave them
    pass
