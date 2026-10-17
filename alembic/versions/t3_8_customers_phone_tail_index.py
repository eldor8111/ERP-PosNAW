"""T3.8 — mijozlar: telefonning oxirgi 9 raqami bo'yicha funksional indeks (Telegram kontakt qidiruvi uchun)

Majburiy bo'lmagan optimallashtirish (faqat indeks; ustun/ma'lumot o'zgarmaydi).

Revision ID: t3_8
Revises:
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't3_8'
down_revision: Union[str, None] = 't3_7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY tranzaksiyadan tashqarida bajarilishi shart
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_customers_phone_tail "
            r"ON customers (company_id, right(regexp_replace(phone, '\D', '', 'g'), 9))"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_customers_phone_tail")
