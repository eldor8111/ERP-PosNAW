"""add expired product notification settings

Revision ID: 438359ee7a94
Revises: 93e64f6f907e
Create Date: 2026-08-18 19:29:31.224567

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '438359ee7a94'
down_revision: Union[str, None] = '93e64f6f907e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('company_bots', sa.Column('notify_expired_products', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('company_bots', sa.Column('expired_days_before', sa.Integer(), nullable=True, server_default='7'))
    pass


def downgrade() -> None:
    op.drop_column('company_bots', 'expired_days_before')
    op.drop_column('company_bots', 'notify_expired_products')
    pass
