"""add_subscription_starts_at_to_companies

Revision ID: fb5a84d57e55
Revises: 1c6414365547
Create Date: 2026-06-15 15:08:13.087882

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'fb5a84d57e55'
down_revision: Union[str, None] = '1c6414365547'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import text
    conn = op.get_bind()
    exists = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name='companies' AND column_name='subscription_starts_at'"
    )).fetchone()
    if not exists:
        op.add_column('companies', sa.Column('subscription_starts_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'subscription_starts_at')
