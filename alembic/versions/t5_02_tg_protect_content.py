"""Telegram bot uchun protect_content (forward/saqlashni cheklash) ustuni

Revision ID: t5_02_protect_content
Revises: t5_01_receipt_format
Create Date: 2026-10-19 00:08:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 't5_02_protect_content'
down_revision: Union[str, Sequence[str], None] = 't5_01_receipt_format'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'companies' AND column_name = 'tg_protect_content'
            ) THEN
                ALTER TABLE companies ADD COLUMN tg_protect_content BOOLEAN DEFAULT FALSE;
            END IF;
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        ALTER TABLE companies DROP COLUMN IF EXISTS tg_protect_content;
    """))
