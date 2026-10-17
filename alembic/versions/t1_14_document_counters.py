"""T1.14 — hujjat raqamlari hisoblagichi (document_counters) va number ustunlarini kengaytirish

Revision ID: t1_14
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_14'
down_revision: Union[str, None] = 't1_13b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Startup'dagi _create_missing_tables jadvalni oldin yaratgan bo'lishi mumkin — IF NOT EXISTS
    op.execute("""
        CREATE TABLE IF NOT EXISTS document_counters (
            company_id INTEGER NOT NULL REFERENCES companies(id),
            branch_id  INTEGER NOT NULL DEFAULT 0,
            doc_type   VARCHAR(8) NOT NULL,
            period     VARCHAR(8) NOT NULL,
            last_value INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (company_id, branch_id, doc_type, period)
        )
    """)
    # VARCHAR(20/30) -> VARCHAR(40): PostgreSQL'da jadvalni qayta yozmaydi.
    # Mavjud raqamlar O'ZGARTIRILMAYDI (eski formatdagi raqamlar qoladi).
    for table in ("sales", "stock_transfers", "inventory_counts", "production_orders", "purchase_orders"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN number TYPE VARCHAR(40)")


def downgrade() -> None:
    # Ataylab bo'sh: raqamlarni qisqartirish yangi formatdagi hujjatlarni buzadi,
    # hisoblagich jadvalini o'chirish esa raqamlarning takrorlanishiga olib keladi.
    pass
