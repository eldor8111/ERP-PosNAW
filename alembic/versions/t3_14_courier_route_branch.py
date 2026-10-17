"""T3.14 — couriers.branch_id va delivery_routes.origin_branch_id (nullable)

NULL = "barcha filial" / belgilanmagan; mavjud kuryer va marshrutlar NULL qoladi,
ma'lumot ko'chirish kerak emas.

Revision ID: t3_14
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't3_14'
down_revision: Union[str, None] = 't3_13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE couriers ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES branches(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_couriers_branch_id ON couriers(branch_id)")
    op.execute("ALTER TABLE delivery_routes ADD COLUMN IF NOT EXISTS origin_branch_id INTEGER REFERENCES branches(id)")


def downgrade() -> None:
    op.execute("ALTER TABLE delivery_routes DROP COLUMN IF EXISTS origin_branch_id")
    op.execute("DROP INDEX IF EXISTS ix_couriers_branch_id")
    op.execute("ALTER TABLE couriers DROP COLUMN IF EXISTS branch_id")
