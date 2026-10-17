"""T0.1 — warehouses.company_id backfill (filial orqali) va indeks

Transfer servisi korxona izolyatsiyasi `warehouses.company_id` ustuniga tayanadi:
har tekshiruv `IN (SELECT id FROM warehouses WHERE company_id = ...)` ishlatadi.
Shuning uchun:
  1) company_id NULL bo'lgan omborlar filial (branches.company_id) orqali to'ldiriladi;
  2) warehouses(company_id) ustuniga indeks qo'yiladi.
Migratsiya idempotent (qayta ishga tushirsa ham xavfsiz) va faqat additiv.

Revision ID: t0_1
Revises: (bosqich oxirida ulanadi)
Create Date: 2026-10-14

"""
import logging

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 't0_1'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None

log = logging.getLogger('alembic.runtime.migration')


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Filiali bor, lekin company_id NULL bo'lgan omborlarni to'ldirish
    res = conn.execute(sa.text(
        "UPDATE warehouses w SET company_id = b.company_id "
        "FROM branches b "
        "WHERE w.company_id IS NULL AND w.branch_id = b.id AND b.company_id IS NOT NULL"
    ))
    log.info("T0.1: %s ta ombor company_id filial orqali to'ldirildi", res.rowcount)

    # Hali ham NULL qolgan omborlar soni (filialsiz) — log uchun, transferda 404 beradi
    left = conn.execute(sa.text("SELECT COUNT(*) FROM warehouses WHERE company_id IS NULL")).scalar()
    log.info("T0.1: company_id NULL qolgan omborlar: %s", left)

    # 2) Indeks (tekshiruv so'rovlari uchun)
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_warehouses_company_id ON warehouses (company_id)"))


def downgrade() -> None:
    # Backfill qilingan ma'lumot qaytarilmaydi; faqat indeks o'chiriladi
    op.execute(sa.text("DROP INDEX IF EXISTS ix_warehouses_company_id"))
