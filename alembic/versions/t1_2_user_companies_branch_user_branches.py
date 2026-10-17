"""T1.2 — foydalanuvchi-filial modeli: user_companies.branch_id va user_branches jadvali

1. user_companies.branch_id (nullable, FK branches ON DELETE SET NULL) + indeks.
2. user_branches jadvali (bir foydalanuvchiga korxona ichida bir nechta filial).
3. Backfill:
   a) users.branch_id → user_companies.branch_id (faqat filial shu korxonaniki bo'lsa;
      boshqa korxona filiali o'tkazilmaydi);
   b) 1 ta faol filialli korxonalarda cashier/warehouse a'zoligiga o'sha filial;
   c) users.branch_id bo'sh bo'lsa asosiy korxona a'zoligidan ko'zgu;
   d) shifts.company_id bo'sh bo'lsa kassirning korxonasi (smena filtri korxona bo'yicha).

Migratsiya idempotent (IF NOT EXISTS / shartli UPDATE). users.branch_id o'chirilmaydi —
u asosiy korxona uchun ko'zgu (legacy fallback) bo'lib qoladi.

Revision ID: t1_2
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_2'
down_revision: Union[str, None] = 't0_36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SCHEMA_STATEMENTS = (
    "ALTER TABLE user_companies ADD COLUMN IF NOT EXISTS branch_id INTEGER "
    "REFERENCES branches(id) ON DELETE SET NULL",
    "CREATE INDEX IF NOT EXISTS ix_user_companies_branch_id ON user_companies(branch_id)",
    "CREATE TABLE IF NOT EXISTS user_branches ("
    "id SERIAL PRIMARY KEY, "
    "user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
    "company_id INT NOT NULL REFERENCES companies(id) ON DELETE CASCADE, "
    "branch_id INT NOT NULL REFERENCES branches(id) ON DELETE CASCADE, "
    "created_at TIMESTAMP DEFAULT now(), "
    "CONSTRAINT uq_user_branch UNIQUE (user_id, branch_id))",
    "CREATE INDEX IF NOT EXISTS ix_user_branches_user_company ON user_branches(user_id, company_id)",
)

DATA_STATEMENTS = (
    # a) users.branch_id → user_companies.branch_id (faqat shu korxona filiali)
    "UPDATE user_companies uc SET branch_id = u.branch_id "
    "FROM users u JOIN branches b ON b.id = u.branch_id "
    "WHERE uc.user_id = u.id AND uc.branch_id IS NULL AND b.company_id = uc.company_id",
    # b) 1 faol filialli korxonalarda cashier/warehouse → o'sha filial
    "UPDATE user_companies uc SET branch_id = x.bid "
    "FROM (SELECT company_id, MIN(id) AS bid FROM branches WHERE is_active "
    "GROUP BY company_id HAVING COUNT(*) = 1) x "
    "WHERE uc.company_id = x.company_id AND uc.branch_id IS NULL "
    "AND uc.role::text IN ('cashier', 'warehouse')",
    # c) users.branch_id ko'zgusi (asosiy korxona a'zoligidan)
    "UPDATE users u SET branch_id = uc.branch_id "
    "FROM user_companies uc "
    "WHERE uc.user_id = u.id AND uc.company_id = u.company_id "
    "AND u.branch_id IS NULL AND uc.branch_id IS NOT NULL",
    # d) shifts.company_id bo'sh bo'lsa — kassirning korxonasi
    "UPDATE shifts s SET company_id = u.company_id "
    "FROM users u WHERE s.company_id IS NULL AND s.cashier_id = u.id AND u.company_id IS NOT NULL",
)


def upgrade() -> None:
    for stmt in SCHEMA_STATEMENTS:
        op.execute(stmt)
    for stmt in DATA_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # Ma'lumot backfill'i qaytarilmaydi; users.branch_id saqlanadi (ko'zgu)
    op.execute("DROP TABLE IF EXISTS user_branches")
    op.execute("DROP INDEX IF EXISTS ix_user_companies_branch_id")
    op.execute("ALTER TABLE user_companies DROP COLUMN IF EXISTS branch_id")
