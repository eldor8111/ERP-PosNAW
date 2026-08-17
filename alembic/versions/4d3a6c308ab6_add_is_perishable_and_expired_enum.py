"""add_is_perishable_and_expired_enum

Revision ID: 4d3a6c308ab6
Revises: 407b4456f3f6
Create Date: 2026-08-13 10:14:04.269780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


"""add_is_perishable_and_expired_enum

Revision ID: 4d3a6c308ab6
Revises: 407b4456f3f6
Create Date: 2026-08-13 10:14:04.269780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4d3a6c308ab6'
down_revision: Union[str, None] = '407b4456f3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('categories', sa.Column('is_perishable', sa.Boolean(), nullable=True))
    op.execute("UPDATE categories SET is_perishable = false")
    
    # Enum ga qiymat qo'shish autocommit bilan bajarilishi shart
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'EXPIRED'")

def downgrade() -> None:
    op.drop_column('categories', 'is_perishable')
