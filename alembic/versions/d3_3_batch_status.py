"""Partiya holati: batches.status, status_reason, status_changed_at, status_changed_by (D3.3)

Additiv: faqat nullable ustunlar; mavjud qatorlar NULL (= faol) qoladi.

Revision ID: d3_3
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd3_3'
down_revision: Union[str, Sequence[str], None] = 'd3_2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS status VARCHAR(20)")
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS status_reason VARCHAR(500)")
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP")
    op.execute("ALTER TABLE batches ADD COLUMN IF NOT EXISTS status_changed_by INTEGER REFERENCES users(id)")


def downgrade() -> None:
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS status_changed_by")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS status_changed_at")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS status_reason")
    op.execute("ALTER TABLE batches DROP COLUMN IF EXISTS status")
