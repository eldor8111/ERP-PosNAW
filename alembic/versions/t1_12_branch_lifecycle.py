"""T1.12 - filial hayot sikli: closed_at / closed_by / close_reason

Faqat ADDITIV: nullable ustunlar va mavjud nofaol filiallar uchun closed_at ni to'ldirish.
Mavjud nofaol filiallarning omborlari, kassalari va xodimlariga TEGILMAYDI (qoldiq yo'qolmasligi uchun).
closed_by ataylab FK siz: users.branch_id <-> branches.closed_by aylanasi ORM da User.branch/Branch.users
relationship'larini noaniq qiladi (modelda ham FK yo'q).

Deploydan oldin faqat o'qish uchun tekshiruv:
  SELECT b.id, b.name,
   (SELECT count(*) FROM shifts s WHERE s.branch_id=b.id AND s.status='open') open_shifts,
   (SELECT count(*) FROM warehouses w WHERE w.branch_id=b.id AND w.is_active) active_wh,
   (SELECT count(*) FROM users u WHERE u.branch_id=b.id AND u.status='active') active_users
  FROM branches b WHERE b.is_active IS NOT TRUE;

Revision ID: t1_12
Revises: (zanjir bosqich oxirida ulanadi)
"""
from alembic import op

revision = 't1_12'
down_revision = 't1_11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE branches ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP")
    op.execute("ALTER TABLE branches ADD COLUMN IF NOT EXISTS closed_by INTEGER")
    op.execute("ALTER TABLE branches ADD COLUMN IF NOT EXISTS close_reason VARCHAR(255)")
    op.execute(
        "UPDATE branches SET closed_at = updated_at "
        "WHERE is_active IS NOT TRUE AND closed_at IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE branches DROP COLUMN IF EXISTS close_reason")
    op.execute("ALTER TABLE branches DROP COLUMN IF EXISTS closed_by")
    op.execute("ALTER TABLE branches DROP COLUMN IF EXISTS closed_at")
