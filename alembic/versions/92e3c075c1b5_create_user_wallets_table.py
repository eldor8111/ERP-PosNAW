"""create user_wallets table

Revision ID: 92e3c075c1b5
Revises: 077ac8034fcc
Create Date: 2026-07-24 17:52:14.721070

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '92e3c075c1b5'
down_revision: Union[str, None] = '915a5d86f7e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
