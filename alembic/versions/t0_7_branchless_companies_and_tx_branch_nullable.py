"""T0.7: filialsiz korxonalarga asosiy filial, transactions.branch_id nullable

1. Filialsiz korxonalarga "<nomi> (Asosiy)" filiali qo'shiladi.
2. NULL branch_id li tranzaksiyalar korxonaning eng kichik id li faol filialiga bog'lanadi.
3. NULL branch_id li OCHIQ smenalar ham shunday (yopilgan smenalar tarixi o'zgarmaydi).
4. transactions.branch_id NOT NULL cheklovi olinadi (model nullable=True; PostgreSQLda
   ustun allaqachon nullable bo'lsa ham xato bermaydi).

Migratsiya idempotent: ikki marta ishga tushsa natija o'zgarmaydi.

Revision ID: t0_7
Revises: t0_6
"""
from alembic import op


revision = 't0_7'
down_revision = 't0_6'
branch_labels = None
depends_on = None


DATA_STATEMENTS = (
    # 1. Filialsiz korxonalarga asosiy filial
    "INSERT INTO branches (name, company_id, is_active) "
    "SELECT c.name || ' (Asosiy)', c.id, true FROM companies c "
    "WHERE NOT EXISTS (SELECT 1 FROM branches b WHERE b.company_id = c.id)",
    # 2. NULL branch_id li tranzaksiyalar
    "UPDATE transactions SET branch_id = ("
    "SELECT MIN(b.id) FROM branches b WHERE b.company_id = transactions.company_id AND b.is_active) "
    "WHERE branch_id IS NULL AND company_id IS NOT NULL",
    # 3. NULL branch_id li ochiq smenalar
    "UPDATE shifts SET branch_id = ("
    "SELECT MIN(b.id) FROM branches b WHERE b.company_id = shifts.company_id AND b.is_active) "
    "WHERE branch_id IS NULL AND status = 'open' AND company_id IS NOT NULL",
)


def upgrade() -> None:
    for stmt in DATA_STATEMENTS:
        op.execute(stmt)
    # 4. NOT NULL ni olish (PostgreSQL; SQLite ALTER COLUMN ni qo'llamaydi)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE transactions ALTER COLUMN branch_id DROP NOT NULL")


def downgrade() -> None:
    # NOT NULL qaytarilmaydi (NULL qatorlar bo'lishi mumkin); qo'shilgan filiallar ham o'chirilmaydi
    pass
