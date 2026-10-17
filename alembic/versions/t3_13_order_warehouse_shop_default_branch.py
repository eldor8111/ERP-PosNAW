"""T3.13: orders.warehouse_id + companies.shop_default_branch_id

Telegram Mini App: mijoz olib ketish filialini tanlaydi, buyurtma aniq omborga bog'lanadi.
1. orders.warehouse_id — nullable (eski buyurtmalar NULL qoladi; sotuvga aylantirishda buyurtma
   filialining shop ombori tanlanadi), FK warehouses.id + indeks.
2. companies.shop_default_branch_id — Mini App / bot uchun standart filial
   (FK branches.id, ondelete SET NULL).

Migratsiya faqat additiv; ma'lumot ko'chirilmaydi.

Revision ID: t3_13
Revises: (zanjir bosqich oxirida ulanadi)
"""
from alembic import op


revision = 't3_13'
down_revision = 't3_12'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER REFERENCES warehouses(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_orders_warehouse_id ON orders(warehouse_id)")
    op.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS shop_default_branch_id INTEGER "
        "REFERENCES branches(id) ON DELETE SET NULL"
    )


def downgrade():
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS shop_default_branch_id")
    op.execute("DROP INDEX IF EXISTS ix_orders_warehouse_id")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS warehouse_id")
