"""add_purchased_at_to_companies

Revision ID: 1c6414365547
Revises: 3ca49e4cb8a5
Create Date: 2026-06-15 14:21:16.379768

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = '1c6414365547'
down_revision: Union[str, None] = '3ca49e4cb8a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='companies' AND column_name='purchased_at'"
    )).fetchone()
    if not exists:
        op.add_column('companies', sa.Column('purchased_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'purchased_at')
