"""add subscription and trial columns to users

Revision ID: dd7268ae19c3
Revises: 70e24366d14d
Create Date: 2026-10-11 21:23:06.869820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'dd7268ae19c3'
down_revision: Union[str, None] = '70e24366d14d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_ends_at TIMESTAMP;")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_trial BOOLEAN DEFAULT FALSE;")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(18, 2) DEFAULT 0;")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS subscription_ends_at;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_trial;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS paid_amount;")
