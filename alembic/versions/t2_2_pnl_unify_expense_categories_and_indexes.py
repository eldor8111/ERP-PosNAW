"""T2.2 — yagona P&L: xarajat kategoriyalarini tozalash, filial/korxona tuzatishlari, indekslar

1. Jurnal jadvallari: `expense_category_merge_log` (old_id, new_id, company_id, merged_at) va
   `expense_branch_fix_log` (expense_id, old_branch_id, new_branch_id, fixed_at).
2. `expenses.company_id` / `transactions.company_id` NULL qatorlarni to'ldirish: xarajat — kassa, xodim,
   filial bo'yicha; xarajat tranzaksiyasi — bog'liq xarajat bo'yicha, qolganlari — filial bo'yicha.
3. `company_id IS NULL` (umumiy) kategoriyalarni ishlatgan har korxona uchun kategoriya nusxasi yaratiladi
   va `expenses.category_id` shu nusxaga ko'chiriladi (jurnalga yoziladi). Nusxasi bo'lmagan umumiy qatorlar qoladi.
4. Dublikat nomlar `(company_id, lower(btrim(name)))` bo'yicha birlashtiriladi: eng kichik `id` qoladi,
   `expenses.category_id` unga ko'chiriladi, qolganlari o'chiriladi (jurnalga yoziladi).
5. Qisman unikal indekslar (Postgres'da NULL lar oddiy UNIQUE da takrorlanmaydi):
   `uq_expense_cat_company_name` (company_id IS NOT NULL) va `uq_expense_cat_global_name` (company_id IS NULL).
6. Boshqa korxona filialiga yozilgan xarajatlar (Finance.jsx ning `branch_id: 1` natijasi): kassa filiali
   (o'z korxonasiniki bo'lsa), aks holda korxonaning eng kichik id li faol filiali; har o'zgarish
   `expense_branch_fix_log` ga yoziladi, tegishli `transactions` (reference_type='expense') ham moslanadi.
7. Indekslar: `ix_expenses_company_branch_created`, `ix_transactions_company_type_created`,
   `ix_transactions_company_branch_created` (T1.13 da bo'lsa — qayta yaratilmaydi).

Hammasi idempotent (IF NOT EXISTS / shartli UPDATE): ikkinchi marta ishga tushsa hech narsa o'zgarmaydi.
`Transaction.branch_id` tarixini ommaviy qayta atributsiya qilish bu yerga kirmaydi: `scripts/pnl_branch_audit.py`.
Birlashtirilgan kategoriyalar va tuzatilgan filiallar jurnal orqali qo'lda qaytariladi.

Revision ID: t2_2
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't2_2'
down_revision: Union[str, None] = 't1_19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ─── 1. Jurnal jadvallari ────────────────────────────────────────────────────
SQL_CREATE_LOGS = [
    """
    CREATE TABLE IF NOT EXISTS expense_category_merge_log (
        id SERIAL PRIMARY KEY,
        old_id INTEGER NOT NULL,
        new_id INTEGER NOT NULL,
        company_id INTEGER,
        merged_at TIMESTAMP NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS expense_branch_fix_log (
        id SERIAL PRIMARY KEY,
        expense_id INTEGER NOT NULL,
        old_branch_id INTEGER,
        new_branch_id INTEGER,
        fixed_at TIMESTAMP NOT NULL DEFAULT now()
    )
    """,
]

# ─── 2. company_id backfill ──────────────────────────────────────────────────
SQL_BACKFILL_COMPANY = [
    # xarajat: kassa -> tasdiqlagan xodim -> filial (eng ishonchlidan boshlab)
    """
    UPDATE expenses e SET company_id = w.company_id
    FROM wallets w
    WHERE e.company_id IS NULL AND e.wallet_id = w.id AND w.company_id IS NOT NULL
    """,
    """
    UPDATE expenses e SET company_id = u.company_id
    FROM users u
    WHERE e.company_id IS NULL AND e.approved_by = u.id AND u.company_id IS NOT NULL
    """,
    """
    UPDATE expenses e SET company_id = b.company_id
    FROM branches b
    WHERE e.company_id IS NULL AND e.branch_id = b.id
    """,
    # xarajat tranzaksiyasi: avval bog'liq xarajat korxonasi (branch_id begona bo'lishi mumkin)
    """
    UPDATE transactions t SET company_id = e.company_id
    FROM expenses e
    WHERE t.company_id IS NULL AND t.reference_type = 'expense' AND t.reference_id = e.id
      AND e.company_id IS NOT NULL
    """,
]
SQL_BACKFILL_TX_COMPANY_FROM_BRANCH = """
    UPDATE transactions t SET company_id = b.company_id
    FROM branches b
    WHERE t.company_id IS NULL AND t.branch_id = b.id
"""

# ─── 3. Umumiy (company_id IS NULL) kategoriyalarni korxonalarga ko'chirish ──
SQL_GLOBAL_COPY_CREATE = """
    INSERT INTO expense_categories (name, description, company_id)
    SELECT DISTINCT ON (e.company_id, lower(btrim(g.name))) g.name, g.description, e.company_id
    FROM expenses e
    JOIN expense_categories g ON g.id = e.category_id
    WHERE g.company_id IS NULL AND e.company_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM expense_categories c
          WHERE c.company_id = e.company_id AND lower(btrim(c.name)) = lower(btrim(g.name))
      )
    ORDER BY e.company_id, lower(btrim(g.name)), g.id
"""
SQL_GLOBAL_COPY_LOG = """
    INSERT INTO expense_category_merge_log (old_id, new_id, company_id)
    SELECT DISTINCT g.id,
           (SELECT MIN(c.id) FROM expense_categories c
            WHERE c.company_id = e.company_id AND lower(btrim(c.name)) = lower(btrim(g.name))),
           e.company_id
    FROM expenses e
    JOIN expense_categories g ON g.id = e.category_id
    WHERE g.company_id IS NULL AND e.company_id IS NOT NULL
"""
SQL_GLOBAL_COPY_UPDATE = """
    UPDATE expenses e SET category_id = (
        SELECT MIN(c.id) FROM expense_categories c
        WHERE c.company_id = e.company_id AND lower(btrim(c.name)) = lower(btrim(g.name))
    )
    FROM expense_categories g
    WHERE g.id = e.category_id AND g.company_id IS NULL AND e.company_id IS NOT NULL
"""


# ─── 4. Dublikat nomlarni birlashtirish ──────────────────────────────────────
def _dedup_sql(scope: str):
    """scope: 'c.company_id IS NOT NULL' yoki 'c.company_id IS NULL'. Guruh: (company_id, lower(btrim(name)))."""
    keep = f"""
        (SELECT company_id, lower(btrim(name)) AS n, MIN(id) AS keep_id
         FROM expense_categories c
         WHERE {scope}
         GROUP BY company_id, lower(btrim(name))
         HAVING COUNT(*) > 1) k
    """
    on = "k.company_id IS NOT DISTINCT FROM c.company_id AND k.n = lower(btrim(c.name)) AND c.id <> k.keep_id"
    log = f"""
        INSERT INTO expense_category_merge_log (old_id, new_id, company_id)
        SELECT c.id, k.keep_id, c.company_id
        FROM expense_categories c JOIN {keep} ON {on}
        WHERE {scope}
    """
    upd = f"""
        UPDATE expenses e SET category_id = k.keep_id
        FROM expense_categories c JOIN {keep} ON {on}
        WHERE e.category_id = c.id AND {scope}
    """
    dele = f"""
        DELETE FROM expense_categories d USING (
            SELECT c.id FROM expense_categories c JOIN {keep} ON {on} WHERE {scope}
        ) x
        WHERE d.id = x.id
          AND NOT EXISTS (SELECT 1 FROM expenses e WHERE e.category_id = d.id)
    """
    return [log, upd, dele]


# ─── 5. Unikal indekslar ─────────────────────────────────────────────────────
SQL_UNIQUE_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_expense_cat_company_name "
    "ON expense_categories (company_id, lower(btrim(name))) WHERE company_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_expense_cat_global_name "
    "ON expense_categories (lower(btrim(name))) WHERE company_id IS NULL",
]

# ─── 6. Begona korxona filialiga yozilgan xarajatlar ─────────────────────────
SQL_FIX_FOREIGN_BRANCH = """
    WITH fix AS (
        SELECT e.id,
               e.branch_id AS old_b,
               COALESCE(
                   (SELECT wb.id FROM wallets w JOIN branches wb ON wb.id = w.branch_id
                    WHERE w.id = e.wallet_id AND wb.company_id = e.company_id),
                   (SELECT MIN(b2.id) FROM branches b2 WHERE b2.company_id = e.company_id AND b2.is_active),
                   (SELECT MIN(b3.id) FROM branches b3 WHERE b3.company_id = e.company_id)
               ) AS new_b
        FROM expenses e
        JOIN branches b ON b.id = e.branch_id
        WHERE e.company_id IS NOT NULL AND b.company_id IS DISTINCT FROM e.company_id
    ),
    upd AS (
        UPDATE expenses e SET branch_id = fix.new_b
        FROM fix
        WHERE e.id = fix.id AND fix.new_b IS NOT NULL
        RETURNING e.id AS id, fix.old_b AS old_b, fix.new_b AS new_b
    ),
    tx AS (
        UPDATE transactions t SET branch_id = upd.new_b
        FROM upd
        WHERE t.reference_type = 'expense' AND t.reference_id = upd.id AND t.type = 'expense'
        RETURNING t.id
    )
    INSERT INTO expense_branch_fix_log (expense_id, old_branch_id, new_branch_id)
    SELECT id, old_b, new_b FROM upd
"""

# ─── 7. Indekslar ────────────────────────────────────────────────────────────
SQL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_expenses_company_branch_created ON expenses (company_id, branch_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_transactions_company_type_created ON transactions (company_id, type, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_transactions_company_branch_created "
    "ON transactions (company_id, branch_id, created_at)",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # Qisman indeks va CTE sintaksisi faqat Postgres uchun

    for sql in SQL_CREATE_LOGS:
        op.execute(sql)
    for sql in SQL_BACKFILL_COMPANY:
        op.execute(sql)

    # Umumiy kategoriyalar -> korxona nusxalari
    op.execute(SQL_GLOBAL_COPY_CREATE)
    op.execute(SQL_GLOBAL_COPY_LOG)
    op.execute(SQL_GLOBAL_COPY_UPDATE)

    # Dublikat nomlar (korxona ichida, so'ng umumiy qatorlar ichida)
    for sql in _dedup_sql("c.company_id IS NOT NULL") + _dedup_sql("c.company_id IS NULL"):
        op.execute(sql)
    for sql in SQL_UNIQUE_INDEXES:
        op.execute(sql)

    # Begona filialga yozilgan xarajatlar, so'ng qolgan tranzaksiyalar korxonasi (filial bo'yicha)
    op.execute(SQL_FIX_FOREIGN_BRANCH)
    op.execute(SQL_BACKFILL_TX_COMPANY_FROM_BRANCH)

    for sql in SQL_INDEXES:
        op.execute(sql)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # ix_transactions_company_branch_created T1.13 ga ham tegishli — uni o'sha migratsiya o'chiradi
    for name in ("ix_transactions_company_type_created", "ix_expenses_company_branch_created",
                 "uq_expense_cat_global_name", "uq_expense_cat_company_name"):
        op.execute(f"DROP INDEX IF EXISTS {name}")
    op.execute("DROP TABLE IF EXISTS expense_branch_fix_log")
    op.execute("DROP TABLE IF EXISTS expense_category_merge_log")
