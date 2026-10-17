"""T1.8 — chiqim hujjat raqami uchun sequence (parallel so'rovlarda noyob reference_id)

Revision ID: t1_8
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_8'
down_revision: Union[str, None] = 't1_7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS stock_chiqim_ref_seq")
    # Mavjud chiqim raqamlaridan keyingisidan boshlanadi (max()+1 davridagi hujjatlar bilan to'qnashmaydi)
    op.execute(
        "SELECT setval('stock_chiqim_ref_seq', "
        "COALESCE((SELECT MAX(reference_id) FROM stock_movements WHERE reference_type = 'chiqim'), 0) + 1, false)"
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS stock_chiqim_ref_seq")
