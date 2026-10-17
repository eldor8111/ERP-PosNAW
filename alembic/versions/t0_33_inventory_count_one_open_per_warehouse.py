"""T0.33 — inventarizatsiya: counted_at ustuni va bir omborda bitta ochiq revizya indeksi

Revision ID: t0_33
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't0_33'
down_revision: Union[str, None] = 't0_32'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE inventory_count_items ADD COLUMN IF NOT EXISTS counted_at TIMESTAMP")

    # Mavjud takroriy ochiq revizyalarni yopamiz (indeksdan oldin): har omborda eng yangisi qoladi
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY warehouse_id ORDER BY id DESC) rn
            FROM inventory_counts WHERE status IN ('draft','in_progress')
        )
        UPDATE inventory_counts AS ic SET status = 'cancelled',
            note = COALESCE(ic.note, '') || ' [avto-bekor: parallel revizya, migratsiya]'
        FROM ranked WHERE ic.id = ranked.id AND ranked.rn > 1
    """)

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_counts_one_open_per_wh "
        "ON inventory_counts (warehouse_id) WHERE status IN ('draft','in_progress')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_inventory_counts_one_open_per_wh")
    op.execute("ALTER TABLE inventory_count_items DROP COLUMN IF EXISTS counted_at")
