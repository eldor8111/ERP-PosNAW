"""T0.4 — user_wallets ga korxona o'lchami (company_id) va bitta default kafolati

Foydalanuvchi-kassa biriktirmasi (user_wallets) da korxona ustuni yo'q edi: ko'p korxonali
foydalanuvchining B korxonadagi sotuvi A kassasiga tushishi mumkin edi, bir foydalanuvchida
bir nechta is_default=true qator yig'ilib qolardi. Bu migratsiya:
  1) company_id INTEGER (nullable, FK companies) ustunini qo'shadi;
  2) uni wallets.company_id dan to'ldiradi;
  3) mavjud bo'lmagan kassaga ko'rsatuvchi yetim qatorlarni o'chiradi;
  4) bir foydalanuvchi + korxonada bittadan ortiq default bo'lsa, eng katta wallet_id ni qoldiradi;
  5) partial unique indeks (user_id, company_id) WHERE is_default va company_id indeksini qo'yadi.
Hamma qadam idempotent (IF NOT EXISTS / shartli UPDATE), faqat additiv. NOT NULL keyingi relizda.

Jadval shakli versiyalarda farq qiladi (ba'zida `id` PK + UNIQUE(user_id, wallet_id), ORM da
(user_id, wallet_id) composite PK) — shuning uchun ustun mavjudligi inspector bilan tekshiriladi.

Revision ID: t0_4
Revises: t0_3
Create Date: 2026-10-14

"""
import logging

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 't0_4'
down_revision = 't0_3'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')

# 1) Ustun (Postgres: IF NOT EXISTS; boshqa dialektlar uchun inspector bilan tekshiriladi)
SQL_ADD_COLUMN_PG = (
    "ALTER TABLE user_wallets ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"
)
# 2) Korxonani kassa orqali to'ldirish
SQL_BACKFILL_COMPANY = (
    "UPDATE user_wallets SET company_id = w.company_id FROM wallets AS w "
    "WHERE w.id = user_wallets.wallet_id AND user_wallets.company_id IS NULL"
)
# 3) Yetim qatorlar (kassa o'chirilgan)
SQL_DELETE_ORPHANS = (
    "DELETE FROM user_wallets WHERE NOT EXISTS "
    "(SELECT 1 FROM wallets AS w WHERE w.id = user_wallets.wallet_id)"
)
# 4) Bir foydalanuvchi + korxonada bittadan ortiq default bo'lsa, eng katta wallet_id qoladi
SQL_DEDUPE_DEFAULTS = (
    "UPDATE user_wallets SET is_default = false FROM ("
    "  SELECT user_id, wallet_id, "
    "         ROW_NUMBER() OVER (PARTITION BY user_id, company_id ORDER BY wallet_id DESC) AS rn "
    "  FROM user_wallets WHERE is_default"
    ") AS d "
    "WHERE user_wallets.user_id = d.user_id AND user_wallets.wallet_id = d.wallet_id AND d.rn > 1"
)
# 5) Indekslar
SQL_UNIQUE_DEFAULT_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_wallets_default_per_company "
    "ON user_wallets (user_id, company_id) WHERE is_default"
)
SQL_COMPANY_INDEX = "CREATE INDEX IF NOT EXISTS ix_user_wallets_company ON user_wallets (company_id)"

# Ustun qo'shilgandan keyingi qadamlar (tartib muhim: avval to'ldirish, keyin dedupe, keyin indeks)
UPGRADE_SQL = (
    SQL_BACKFILL_COMPANY,
    SQL_DELETE_ORPHANS,
    SQL_DEDUPE_DEFAULTS,
    SQL_UNIQUE_DEFAULT_INDEX,
    SQL_COMPANY_INDEX,
)


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute(sa.text(SQL_ADD_COLUMN_PG))
    elif not _has_column(bind, "user_wallets", "company_id"):
        op.add_column(
            "user_wallets",
            sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        )

    for stmt in UPGRADE_SQL:
        res = bind.execute(sa.text(stmt))
        if stmt in (SQL_BACKFILL_COMPANY, SQL_DELETE_ORPHANS, SQL_DEDUPE_DEFAULTS):
            log.info("T0.4: %s ta qator: %s", res.rowcount, stmt[:60])

    left = bind.execute(sa.text("SELECT COUNT(*) FROM user_wallets WHERE company_id IS NULL")).scalar()
    log.info("T0.4: user_wallets.company_id NULL qolgan qatorlar: %s", left)


def downgrade() -> None:
    # Ma'lumot to'ldirish/dedupe qaytarilmaydi; indekslar va ustun olib tashlanadi
    op.execute(sa.text("DROP INDEX IF EXISTS uq_user_wallets_default_per_company"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_user_wallets_company"))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE user_wallets DROP COLUMN IF EXISTS company_id"))
    elif _has_column(bind, "user_wallets", "company_id"):
        with op.batch_alter_table("user_wallets") as batch:
            batch.drop_column("company_id")
