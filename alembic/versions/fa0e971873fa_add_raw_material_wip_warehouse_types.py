"""add raw_material and wip values to warehousetype enum

Revision ID: fa0e971873fa
Revises: e7a8b9c0d1f2
Create Date: 2026-09-27

Ishlab chiqarish moduli uchun poydevor (1-bosqich): xom ashyo ombori va
jarayondagi (WIP) ombor turlarini qo'shadi. Mavjud main/transit/returns/shop
qiymatlariga tegilmaydi.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'fa0e971873fa'
down_revision = 'e7a8b9c0d1f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres'da ALTER TYPE ... ADD VALUE tranzaksiya ichida darhol
    # ishlatib bo'lmaydi, shuning uchun avtokommit rejimida bajaramiz.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE warehousetype ADD VALUE IF NOT EXISTS 'raw_material'")
        op.execute("ALTER TYPE warehousetype ADD VALUE IF NOT EXISTS 'wip'")


def downgrade() -> None:
    # Postgres enum qiymatini olib tashlab bo'lmaydi (faqat butun turni
    # qayta yaratish orqali) — downgrade qo'llab-quvvatlanmaydi.
    pass
