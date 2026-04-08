"""add_pending_to_sale_status

Revision ID: 0dbc9cb2bab2
Revises: e6f7a8b9c0d1
Create Date: 2026-04-07 21:23:33.558807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0dbc9cb2bab2'
down_revision: Union[str, None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SaleStatus enum'ga 'pending' qiymatini qo'shish
    # PostgreSQL'da IF NOT EXISTS orqali havfsiz qo'shish
    op.execute("ALTER TYPE salestatus ADD VALUE IF NOT EXISTS 'pending'")


def downgrade() -> None:
    # PostgreSQL enum qiymatlarini o'chirib bo'lmaydi,
    # shuning uchun downgrade bo'sh
    pass
