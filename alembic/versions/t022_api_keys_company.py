"""T0.22 — api_keys ni korxonaga bog'lash

ACCESS-25 / REPORT-23 / ACCESS-X15: API kalitlar korxonaga bog'lanmagan edi
(ro'yxat/o'chirish cross-tenant). Endi:
  * company_id (nullable, ON DELETE CASCADE, indeks), created_by, key_prefix, last_used_at;
  * egasi aniqlanmagan eski qatorlar (company_id IS NULL) nofaol qilinadi, O'CHIRILMAYDI;
    NULL hech qachon "hamma uchun ko'rinadi" deb talqin qilinmaydi.
NOT NULL KEYINGI relizda: SELECT count(*) FROM api_keys WHERE company_id IS NULL qo'lda tozalangach.
Migratsiya idempotent (app.main._run_auto_migrations dagi SQL lar bilan bir xil).

Revision ID: t0_22
Revises: (bosqich oxirida ulanadi)
Create Date: 2026-10-14

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 't0_22'
down_revision = 't0_21'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS key_prefix VARCHAR(12)")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP")
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_company_id ON api_keys(company_id)")
    op.execute("UPDATE api_keys SET is_active = FALSE WHERE company_id IS NULL AND is_active IS DISTINCT FROM FALSE")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_keys_company_id")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS last_used_at")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS key_prefix")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS company_id")
