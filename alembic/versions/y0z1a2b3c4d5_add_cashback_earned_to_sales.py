"""add cashback_earned to sales

Revision ID: y0z1a2b3c4d5
Revises: f2a4c6e8d0b1
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'y0z1a2b3c4d5'
down_revision = 'f2a4c6e8d0b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sales', sa.Column('cashback_earned', sa.Numeric(20, 4), server_default='0', nullable=True))


def downgrade() -> None:
    op.drop_column('sales', 'cashback_earned')
