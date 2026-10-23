"""Dorixona moduli: companies.pharmacy_enabled va pharmacy_settings (D1.1)

Additiv: oddiy do'konlar uchun pharmacy_enabled=false, xatti-harakat o'zgarmaydi.

Revision ID: t6_01_pharmacy_module
Revises: t5_02_protect_content
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't6_01_pharmacy_module'
down_revision: Union[str, Sequence[str], None] = 't5_02_protect_content'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS pharmacy_enabled BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS pharmacy_settings JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS pharmacy_settings")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS pharmacy_enabled")
