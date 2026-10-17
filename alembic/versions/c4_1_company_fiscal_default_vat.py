"""C4.1 — companies.fiscal_default_vat (QQS turi belgilanmagan mahsulot uchun standart foiz)

Additiv: nullable ustun. NULL bo'lsa hippo_fiscalize._vat_percent avvalgidek 12% ishlatadi.

Revision ID: c4_1
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'c4_1'
down_revision: Union[str, None] = 't4_7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS fiscal_default_vat INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS fiscal_default_vat")
