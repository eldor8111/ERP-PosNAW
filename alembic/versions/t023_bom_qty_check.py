"""T0.23 — bom_items.quantity_per_unit > 0 CHECK (NOT VALID)

Retseptura sarf me'yori faqat musbat bo'lishi kerak (STOCK-16). Cheklov
NOT VALID bilan qo'yiladi: yangi/o'zgargan qatorlarga ta'sir qiladi, mavjud
noto'g'ri qatorlarga tegmaydi (migratsiya xatosiz o'tadi). Ifloslangan BOM lar
inson tomonidan tekshirilib tuzatilgach:
    ALTER TABLE bom_items VALIDATE CONSTRAINT ck_bom_items_qty_positive;
Ma'lumotni nofaol qilish (UPDATE boms ...) bu migratsiyaga KIRITILMAGAN.
Migratsiya idempotent va faqat additiv.

Revision ID: t0_23
Revises: (bosqich oxirida ulanadi)
Create Date: 2026-10-14

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 't0_23'
down_revision = 't0_22'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_bom_items_qty_positive') THEN "
        "ALTER TABLE bom_items ADD CONSTRAINT ck_bom_items_qty_positive "
        "CHECK (quantity_per_unit > 0) NOT VALID; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bom_items DROP CONSTRAINT IF EXISTS ck_bom_items_qty_positive")
