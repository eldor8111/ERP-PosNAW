"""T1.13 — branches yaxlitligi: is_active/created_at NOT NULL, faol nom unikalligi, bir kassirda bitta ochiq smena

Revision ID: t1_13
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_13'
down_revision: Union[str, None] = 't1_12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # is_active: NULL larni TRUE qilib, DEFAULT va NOT NULL qo'yamiz
    op.execute("UPDATE branches SET is_active = TRUE WHERE is_active IS NULL")
    op.execute("ALTER TABLE branches ALTER COLUMN is_active SET DEFAULT TRUE")
    op.execute("ALTER TABLE branches ALTER COLUMN is_active SET NOT NULL")

    # created_at: tarixda 51daf448bed1 qo'shgan, b31c2062044d o'chirgan (ma'lumot hech qachon saqlanmagan)
    op.execute("ALTER TABLE branches ADD COLUMN IF NOT EXISTS created_at TIMESTAMP")
    op.execute("UPDATE branches SET created_at = COALESCE(updated_at, NOW()) WHERE created_at IS NULL")
    op.execute("ALTER TABLE branches ALTER COLUMN created_at SET DEFAULT NOW()")
    op.execute("ALTER TABLE branches ALTER COLUMN created_at SET NOT NULL")

    # Faol, bir korxonadagi dublikat nomlarni avval qayta nomlaymiz, aks holda unikal indeks yiqiladi
    op.execute("""
        WITH d AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY company_id, lower(btrim(name)) ORDER BY id) rn
            FROM branches WHERE is_active IS TRUE
        )
        UPDATE branches b SET name = left(b.name, 92) || ' (' || d.rn || ')'
        FROM d WHERE b.id = d.id AND d.rn > 1
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_branches_company_name_active "
        "ON branches (company_id, lower(btrim(name))) WHERE is_active IS TRUE"
    )

    # company_id NOT NULL — faqat yetim filial bo'lmasa (aks holda qo'lda tozalash kerak)
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM branches WHERE company_id IS NULL) THEN
            ALTER TABLE branches ALTER COLUMN company_id SET NOT NULL;
          ELSE
            RAISE NOTICE 'branches.company_id NULL qatorlar bor, NOT NULL qo''yilmadi';
          END IF;
        END $$
    """)

    # audit_logs korxona/filial o'lchami (T1.19 ham qo'shadi — IF NOT EXISTS idempotent)
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)")
    op.execute("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS branch_id INTEGER REFERENCES branches(id)")

    # Bir kassirda bitta ochiq smena: indeksdan oldin dublikatlarni yopamiz (eng yangisi qoladi)
    op.execute("""
        WITH r AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY cashier_id ORDER BY opened_at DESC, id DESC) rn
            FROM shifts WHERE status = 'open'
        )
        UPDATE shifts s SET status = 'closed', closed_at = NOW()
        FROM r WHERE s.id = r.id AND r.rn > 1
    """)

    # payme_* ustunlari: b31c2062044d o'chirgan, app/main.py startup'da qayta qo'shadi — zanjir egaligi uchun
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS payme_merchant_id VARCHAR(50)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS payme_secret_key VARCHAR(128)")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS payme_is_test BOOLEAN DEFAULT TRUE")


def downgrade() -> None:
    # Ma'lumot yo'qolmasligi uchun faqat cheklovlar olib tashlanadi (created_at, audit ustunlari, payme_* qoladi;
    # qayta nomlangan dublikat nomlar va avto-yopilgan smenalar tiklanmaydi).
    op.execute("DROP INDEX IF EXISTS uq_branches_company_name_active")
    op.execute("ALTER TABLE branches ALTER COLUMN company_id DROP NOT NULL")
    op.execute("ALTER TABLE branches ALTER COLUMN created_at DROP NOT NULL")
    op.execute("ALTER TABLE branches ALTER COLUMN created_at DROP DEFAULT")
    op.execute("ALTER TABLE branches ALTER COLUMN is_active DROP NOT NULL")
    op.execute("ALTER TABLE branches ALTER COLUMN is_active DROP DEFAULT")
