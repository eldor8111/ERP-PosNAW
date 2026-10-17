"""T1.11 - smena: kassa/yopgan xodim/izohlar, kassa sessiyasi filiali, pos_require_shift

Faqat ADDITIV: nullable ustunlar, DEFAULT FALSE ustun, indeks va mavjud qatorlarni to'ldirish.
Eski yopilgan smenalarda expected_cash/cash_difference (T0.28) NULL qoladi - qayta hisoblanmaydi.

Revision ID: t1_11
Revises: (zanjir bosqich oxirida ulanadi)
"""
from alembic import op

revision = 't1_11'
down_revision = 't1_10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS wallet_id INTEGER REFERENCES wallets(id)")
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS closed_by INTEGER REFERENCES users(id)")
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS note_open TEXT")
    op.execute("ALTER TABLE shifts ADD COLUMN IF NOT EXISTS note_close TEXT")
    # Filialsiz eski smenalar: kassir filialidan to'ldiriladi
    op.execute(
        "UPDATE shifts s SET branch_id = u.branch_id FROM users u "
        "WHERE s.cashier_id = u.id AND s.branch_id IS NULL AND u.branch_id IS NOT NULL"
    )
    op.execute("ALTER TABLE kassa_sessions ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES branches(id)")
    op.execute(
        "UPDATE kassa_sessions ks SET branch_id = w.branch_id FROM wallets w "
        "WHERE w.id = ks.wallet_id AND ks.branch_id IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kassa_sessions_company_branch_opened "
        "ON kassa_sessions (company_id, branch_id, opened_at)"
    )
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS pos_require_shift BOOLEAN NOT NULL DEFAULT FALSE")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS pos_require_shift")
    op.execute("DROP INDEX IF EXISTS ix_kassa_sessions_company_branch_opened")
    op.execute("ALTER TABLE kassa_sessions DROP COLUMN IF EXISTS branch_id")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS note_close")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS note_open")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS closed_by")
    op.execute("ALTER TABLE shifts DROP COLUMN IF EXISTS wallet_id")
