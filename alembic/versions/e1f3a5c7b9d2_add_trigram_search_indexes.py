"""add pg_trgm GIN indexes for product search (name, sku, barcode)

Revision ID: e1f3a5c7b9d2
Revises: d8e2f4a6b1c3
Create Date: 2026-09-20 01:25:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'e1f3a5c7b9d2'
down_revision = 'd8e2f4a6b1c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # POS/mahsulot qidiruvi ILIKE '%...%' (leading wildcard) ishlatadi —
    # oddiy btree indeks bunga yordam bermaydi, sequential scan bo'ladi.
    # pg_trgm GIN indeks bunday qidiruvlarni sezilarli tezlashtiradi.
    #
    # DB foydalanuvchisida CREATE EXTENSION huquqi bo'lmasligi mumkin
    # (masalan managed Postgres'da) — shunday holatda bu migratsiya
    # deploy'ni to'xtatib qo'ymasin deb, xatoni yutib, indekssiz davom etamiz.
    # SAVEPOINT (begin_nested) ishlatamiz — agar CREATE EXTENSION xato bersa
    # (masalan managed Postgres'da CREATE huquqi yo'q), faqat shu savepoint
    # rollback bo'ladi, butun migratsiya transaction'i buzilmaydi.
    conn = op.get_bind()
    try:
        with conn.begin_nested():
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    except Exception as ex:
        print(f"[migration] pg_trgm extension yaratib bo'lmadi (huquq yetishmasligi mumkin), trigram indekslar o'tkazib yuborildi: {ex}")
        return

    try:
        with conn.begin_nested():
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_products_name_trgm ON products USING gin (name gin_trgm_ops)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_products_sku_trgm ON products USING gin (sku gin_trgm_ops)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_products_barcode_trgm ON products USING gin (barcode gin_trgm_ops)"
            )
    except Exception as ex:
        print(f"[migration] trigram indekslar yaratilmadi: {ex}")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_barcode_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_sku_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_name_trgm")
