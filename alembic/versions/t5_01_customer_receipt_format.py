"""Mijoz uchun receipt_format (chek formati: text, pdf, image) ustunini qo'shish

Revision ID: t5_01_receipt_format
Revises: m_merge_filial_ai
Create Date: 2026-10-18 22:38:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 't5_01_receipt_format'
down_revision: Union[str, Sequence[str], None] = 'm_merge_filial_ai'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'customers' AND column_name = 'receipt_format'
            ) THEN
                ALTER TABLE customers ADD COLUMN receipt_format VARCHAR(20) DEFAULT NULL;
            ELSE
                ALTER TABLE customers ALTER COLUMN receipt_format DROP DEFAULT;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'companies' AND column_name = 'receipt_format'
            ) THEN
                ALTER TABLE companies ADD COLUMN receipt_format VARCHAR(20) DEFAULT 'text';
            END IF;

            -- Mijozlar uchun eski default 'text' qiymatini tozalash (kompaniya sozlamasi ustuvor bo'lishi uchun)
            UPDATE customers SET receipt_format = NULL WHERE receipt_format = 'text';
        END $$;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        ALTER TABLE customers DROP COLUMN IF EXISTS receipt_format;
        ALTER TABLE companies DROP COLUMN IF EXISTS receipt_format;
    """))
