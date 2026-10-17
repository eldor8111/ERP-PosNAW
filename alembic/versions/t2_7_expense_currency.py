"""T2.7 — xarajat valyutasi: expenses.currency / exchange_rate / amount_uzs

1. `expenses` ga: `currency VARCHAR(3) NOT NULL DEFAULT 'UZS'`, `exchange_rate NUMERIC(14,4)`, `amount_uzs NUMERIC(18,2)`.
2. Ko'chirish (idempotent, ketma-ketlik muhim):
   a) valyutali eski xarajatlar `kassa_movements` (reference_type='expense', currency<>'UZS') dan aniqlanadi;
   b) UZS xarajatlarda `exchange_rate=1`, `amount_uzs=amount`;
   c) valyutali xarajatlarda kurs `currencies` dan (avval `company_id = e.company_id`, bo'lmasa `company_id IS NULL`);
      kurs topilmasa `exchange_rate`/`amount_uzs` NULL qoladi (hisobotlar `coalesce(amount_uzs, amount)`);
   d) xarajat tranzaksiyalarining (`expense`, `expense_void`) `currency_code` si xarajat valyutasiga tenglanadi.
3. Ixtiyoriy: `uq_currencies_company_code` — `(company_id, upper(code))` unikal indeksi. Takror qatorlar bo'lsa
   indeks YARATILMAYDI (ogohlantirish chiqadi) — qo'lda tozalash kerak.

Migratsiyadan keyin: `python deploy/recalc_wallet_balances.py` (dry-run) -> `--apply`
(faqat T2.8 dagi "KassaMovement yo'q yozuvlar" tekshiruvi toza bo'lgach).

Revision ID: t2_7
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't2_7'
down_revision: Union[str, None] = 't2_6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SQL_ADD_COLUMNS = [
    "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NOT NULL DEFAULT 'UZS'",
    "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS exchange_rate NUMERIC(14,4)",
    "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS amount_uzs NUMERIC(18,2)",
]

# Portativ SQL (Postgres va SQLite): testda ham shu ro'yxat ishga tushiriladi.
SQL_BACKFILL = [
    # a) valyutali eski xarajatlar kassa harakatidan aniqlanadi
    """
    UPDATE expenses SET currency = (
        SELECT upper(km.currency) FROM kassa_movements km
        WHERE km.reference_type = 'expense' AND km.reference_id = expenses.id
          AND km.currency IS NOT NULL AND upper(km.currency) <> 'UZS'
        ORDER BY km.id LIMIT 1
    )
    WHERE currency = 'UZS' AND EXISTS (
        SELECT 1 FROM kassa_movements km
        WHERE km.reference_type = 'expense' AND km.reference_id = expenses.id
          AND km.currency IS NOT NULL AND upper(km.currency) <> 'UZS'
    )
    """,
    # b) UZS xarajatlar
    """
    UPDATE expenses SET exchange_rate = 1, amount_uzs = amount
    WHERE currency = 'UZS' AND amount_uzs IS NULL
    """,
    # c) valyutali xarajatlar: korxona kursi, bo'lmasa global (NULL) kurs
    """
    UPDATE expenses SET exchange_rate = (
        SELECT c.rate FROM currencies c
        WHERE upper(c.code) = expenses.currency AND c.rate > 0
          AND (c.company_id = expenses.company_id OR c.company_id IS NULL)
        ORDER BY CASE WHEN c.company_id IS NULL THEN 1 ELSE 0 END, c.id
        LIMIT 1
    )
    WHERE currency <> 'UZS' AND amount_uzs IS NULL AND exchange_rate IS NULL
    """,
    """
    UPDATE expenses SET amount_uzs = round(amount * exchange_rate, 2)
    WHERE currency <> 'UZS' AND amount_uzs IS NULL AND exchange_rate IS NOT NULL
    """,
    # d) xarajat tranzaksiyalari valyutasi
    """
    UPDATE transactions SET currency_code = (
        SELECT e.currency FROM expenses e WHERE e.id = transactions.reference_id
    )
    WHERE reference_type IN ('expense', 'expense_void')
      AND reference_id IS NOT NULL
      AND EXISTS (
        SELECT 1 FROM expenses e
        WHERE e.id = transactions.reference_id AND e.currency <> 'UZS'
          AND (transactions.currency_code IS NULL OR transactions.currency_code <> e.currency)
      )
    """,
]

SQL_UNIQUE_INDEX = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM currencies GROUP BY company_id, upper(code) HAVING count(*) > 1
    ) THEN
        RAISE WARNING 'T2.7: currencies da takror (company_id, code) qatorlar bor — uq_currencies_company_code yaratilmadi, qo''lda tozalang';
    ELSE
        CREATE UNIQUE INDEX IF NOT EXISTS uq_currencies_company_code ON currencies (company_id, upper(code));
    END IF;
END $$;
"""


def upgrade() -> None:
    for sql in SQL_ADD_COLUMNS:
        op.execute(sql)
    for sql in SQL_BACKFILL:
        op.execute(sql)
    op.execute(SQL_UNIQUE_INDEX)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_currencies_company_code")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS amount_uzs")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS exchange_rate")
    op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS currency")
