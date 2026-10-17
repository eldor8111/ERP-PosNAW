"""T0.16: nofaol/bloklangan foydalanuvchilarning Telegram bog'lanishini uzish

Sxema o'zgarmaydi — faqat ma'lumot: o'chirilgan yoki bloklangan rahbarlarga
admin-bot hisobot va bildirishnomalari ketmasligi uchun tg_chat_id tozalanadi.

Revision ID: t0_16
Revises: t0_7
Create Date: 2026-10-14

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 't0_16'
down_revision: Union[str, None] = 't0_7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET tg_chat_id = NULL "
        "WHERE status IN ('inactive', 'blocked') AND tg_chat_id IS NOT NULL;"
    )


def downgrade() -> None:
    # Ma'lumot migratsiyasi — tozalangan tg_chat_id qiymatlarini qaytarib bo'lmaydi
    pass
