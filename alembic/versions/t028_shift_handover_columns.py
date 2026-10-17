"""T0.28 — smena yopilishi: kutilgan naqd, farq va inkassatsiya ustunlari

shifts jadvaliga faqat NULL ruxsat etilgan ustunlar qo'shiladi; eski yopilgan
smenalar uchun qiymatlar NULL qoladi (qayta hisoblanmaydi). Mavjud
Transaction(reference_type='shift') qatorlari O'CHIRILMAYDI — hisobotlardan
INTERNAL_TX_REFS filtri bilan chiqariladi.

Revision ID: t028
Revises: t0_26
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't028'
down_revision: Union[str, None] = 't0_26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS expected_cash NUMERIC(14,2)")
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS cash_difference NUMERIC(14,2)")
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS handover_cash_amount NUMERIC(14,2)")
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS handover_wallet_id INTEGER REFERENCES wallets(id)")
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS handover_card_wallet_id INTEGER REFERENCES wallets(id)")


def downgrade() -> None:
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS handover_card_wallet_id")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS handover_wallet_id")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS handover_cash_amount")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS cash_difference")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS expected_cash")
