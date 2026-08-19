"""fix_kassa_sessions_created_at_default

Revision ID: e7f8a9b0c1d2
Revises: 438359ee7a94
Create Date: 2026-08-19 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = '438359ee7a94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure created_at and updated_at have defaults and nullable fix if needed
    op.execute("ALTER TABLE kassa_sessions ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE kassa_sessions ALTER COLUMN updated_at SET DEFAULT now()")


def downgrade() -> None:
    op.execute("ALTER TABLE kassa_sessions ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE kassa_sessions ALTER COLUMN updated_at DROP DEFAULT")
