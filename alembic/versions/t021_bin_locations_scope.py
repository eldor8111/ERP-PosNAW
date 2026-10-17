"""T0.21 — bin_locations ni korxona (company_id) va omborga (warehouse_id) bog'lash

ACCESS-24 / STOCK-34: saqlash joylari global edi (code global unikal, korxona
filtri yo'q). Endi:
  * company_id (nullable, keyin NOT NULL qilinadi) va ixtiyoriy warehouse_id;
  * eski global unikal ix_bin_locations_code oddiy indeksga almashtiriladi;
  * eski qatorlar uni ishlatayotgan (products.bin_location) har bir korxonaga
    alohida nusxa qilib bo'linadi, egasi aniqlangan eski NULL qatorlar o'chiriladi
    (bin_locations.id hech qayerda FK emas, Product.bin_location esa matn);
  * hech kim ishlatmagan qatorlar: bitta korxona bo'lsa unga biriktiriladi,
    aks holda nofaol qilinadi;
  * unikallik (company_id, COALESCE(warehouse_id, 0), code) bo'yicha.
NOT NULL KEYINGI relizda: SELECT count(*) FROM bin_locations WHERE company_id IS NULL = 0 bo'lgach.
Migratsiya idempotent (app.main._run_auto_migrations dagi SQL lar bilan bir xil).

Revision ID: t0_21
Revises: (bosqich oxirida ulanadi)
Create Date: 2026-10-14

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 't0_21'
down_revision = 't0_18'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE bin_locations ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)")
    op.execute("ALTER TABLE bin_locations ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bin_locations_company_id ON bin_locations(company_id)")
    # Eski global unikal indeksni oddiy indeksga almashtirish
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_indexes WHERE indexname='ix_bin_locations_code' AND indexdef ILIKE 'CREATE UNIQUE%') THEN "
        "DROP INDEX ix_bin_locations_code; "
        "CREATE INDEX ix_bin_locations_code ON bin_locations(code); "
        "END IF; END $$;"
    )
    # Backfill (a): eski qatorni uni ishlatayotgan har bir korxonaga alohida nusxalash
    op.execute(
        "INSERT INTO bin_locations (code, label, is_active, created_at, company_id) "
        "SELECT DISTINCT bl.code, bl.label, bl.is_active, bl.created_at, p.company_id "
        "FROM bin_locations bl JOIN products p ON p.bin_location = bl.code AND p.company_id IS NOT NULL "
        "WHERE bl.company_id IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM bin_locations x WHERE x.company_id = p.company_id "
        "AND x.code = bl.code AND x.warehouse_id IS NULL)"
    )
    # (b): egasi aniqlangan eski NULL qatorlarni o'chirish
    op.execute(
        "DELETE FROM bin_locations bl WHERE bl.company_id IS NULL "
        "AND EXISTS (SELECT 1 FROM products p WHERE p.bin_location = bl.code AND p.company_id IS NOT NULL)"
    )
    # (c): hech kim ishlatmagan qatorlar
    op.execute(
        "UPDATE bin_locations SET company_id = (SELECT id FROM companies LIMIT 1) "
        "WHERE company_id IS NULL AND (SELECT count(*) FROM companies) = 1"
    )
    op.execute("UPDATE bin_locations SET is_active = FALSE WHERE company_id IS NULL AND is_active IS NOT FALSE")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bin_locations_company_wh_code "
        "ON bin_locations (company_id, COALESCE(warehouse_id, 0), code)"
    )


def downgrade() -> None:
    # ix_bin_locations_code ni qayta UNIKAL qilishga urinilmaydi: korxonalar bo'yicha
    # bo'lingan dublikat kodlar bo'lishi mumkin. Backfill ham qaytarilmaydi.
    op.execute("DROP INDEX IF EXISTS uq_bin_locations_company_wh_code")
    op.execute("DROP INDEX IF EXISTS ix_bin_locations_company_id")
    op.execute("ALTER TABLE bin_locations DROP COLUMN IF EXISTS warehouse_id")
    op.execute("ALTER TABLE bin_locations DROP COLUMN IF EXISTS company_id")
