"""T0.3 — transactions.company_id ni to'ldirish (xarajat tranzaksiyalari company_id siz yozilgan)

Sxema o'zgarmaydi: faqat ma'lumot to'g'rilash. `create_expense` yaratgan Transaction
yozuvlari company_id siz edi, shuning uchun /finance/cash-balance va dashboard
(Transaction.company_id bo'yicha filtr) ularni ko'rmasdi. Hamyon (wallets) yoki
filial (branches) orqali korxona aniqlanadi. Ikkala UPDATE idempotent.

Revision ID: t0_3
Revises: t0_1
Create Date: 2026-10-14

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 't0_3'
down_revision = 't0_1'
branch_labels = None
depends_on = None

# 1) Hamyon orqali korxona
SQL_BACKFILL_BY_WALLET = (
    "UPDATE transactions AS t SET company_id = w.company_id FROM wallets AS w "
    "WHERE t.company_id IS NULL AND t.wallet_id = w.id"
)
# 2) Filial orqali korxona (hamyonsiz tranzaksiyalar)
SQL_BACKFILL_BY_BRANCH = (
    "UPDATE transactions AS t SET company_id = b.company_id FROM branches AS b "
    "WHERE t.company_id IS NULL AND t.branch_id = b.id AND b.company_id IS NOT NULL"
)
SQL_COUNT_REMAINING = "SELECT count(*) FROM transactions WHERE company_id IS NULL"


def upgrade() -> None:
    bind = op.get_bind()

    op.execute(sa.text(SQL_BACKFILL_BY_WALLET))
    op.execute(sa.text(SQL_BACKFILL_BY_BRANCH))

    # Qolgan (korxonasi aniqlanmagan) qatorlar soni — log
    remaining = bind.execute(sa.text(SQL_COUNT_REMAINING)).scalar()
    print(f"[t0_3] transactions.company_id IS NULL qolgan qatorlar: {remaining}")
    if bind.dialect.name == "postgresql":
        op.execute(sa.text(
            "DO $$ BEGIN RAISE NOTICE '[t0_3] transactions.company_id IS NULL qolgan qatorlar: "
            f"{int(remaining or 0)}'; END $$"
        ))


def downgrade() -> None:
    # Ma'lumot to'ldirish — orqaga qaytarilmaydi (no-op)
    pass
