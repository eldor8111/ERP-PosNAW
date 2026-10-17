"""T1.10 — kassani filialga bog'lash: wallets.is_personal, sales.wallet_id + backfill

1. `wallets.is_personal BOOLEAN NOT NULL DEFAULT FALSE` (kuryer/agent "qo'l kassasi" bayrog'i).
2. Mavjud shaxsiy kassalarni belgilash: mobil rollar (courier/agent/marketplace_agent) ga biriktirilgan
   yoki nomi "... — qo'l kassasi" bo'lgan kassalar `is_personal = TRUE`.
3. `sales.wallet_id INTEGER NULL REFERENCES wallets(id)` + `ix_sales_wallet_id`.
4. `sales.wallet_id` backfill: sotuvning birinchi `transactions` (reference_type='sale') kassasidan.
5. `wallets.branch_id` xavfsiz backfill: FAQAT aynan bitta faol filiali bor korxonalarda `NULL` kassalarga
   shu filial yoziladi. Ko'p filialli korxonalarda `NULL` qoladi (= umumiy kassa); avtomatik "asosiy filial"
   tayinlanmaydi.
6. Nofaol kassalarga bog'langan `user_wallets` qatorlari o'chiriladi.

Faqat additiv + ma'lumot to'ldirish. Downgrade: `sales.wallet_id` va `wallets.is_personal` ustunlari olib tashlanadi
(5 va 6-bosqich ma'lumotlari qaytarilmaydi).

Revision ID: t1_10
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't1_10'
down_revision: Union[str, None] = 't1_9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE wallets ADD COLUMN IF NOT EXISTS is_personal BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("""
        UPDATE wallets SET is_personal = TRUE
        WHERE id IN (
            SELECT uw.wallet_id FROM user_wallets uw JOIN users u ON u.id = uw.user_id
            WHERE u.role::text IN ('courier', 'agent', 'marketplace_agent')
        ) OR name LIKE '% — qo''l kassasi'
    """)
    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS wallet_id INTEGER REFERENCES wallets(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sales_wallet_id ON sales(wallet_id)")
    op.execute("""
        UPDATE sales s SET wallet_id = t.wallet_id
        FROM (
            SELECT DISTINCT ON (reference_id) reference_id, wallet_id
            FROM transactions
            WHERE reference_type = 'sale' AND wallet_id IS NOT NULL
            ORDER BY reference_id, id
        ) t
        WHERE s.id = t.reference_id AND s.wallet_id IS NULL
    """)
    # Faqat aynan bitta faol filiali bor korxonalar: filialsiz kassalar shu filialga bog'lanadi
    op.execute("""
        UPDATE wallets w SET branch_id = x.branch_id
        FROM (
            SELECT company_id, MIN(id) AS branch_id
            FROM branches WHERE is_active = TRUE
            GROUP BY company_id HAVING COUNT(*) = 1
        ) x
        WHERE w.branch_id IS NULL AND w.company_id = x.company_id AND w.is_personal = FALSE
    """)
    op.execute("""
        DELETE FROM user_wallets WHERE wallet_id IN (SELECT id FROM wallets WHERE is_active = FALSE)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sales_wallet_id")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS wallet_id")
    op.execute("ALTER TABLE wallets DROP COLUMN IF EXISTS is_personal")
