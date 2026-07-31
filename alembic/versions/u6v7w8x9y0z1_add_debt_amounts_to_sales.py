"""add debt_amounts to sales

Revision ID: u6v7w8x9y0z1
Revises: t5u6v7w8x9y0
Create Date: 2026-07-31

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'u6v7w8x9y0z1'
down_revision = 't5u6v7w8x9y0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add column debt_amounts
    op.add_column('sales', sa.Column('debt_amounts', sa.JSON(), server_default='{}', nullable=True))


def downgrade() -> None:
    op.drop_column('sales', 'debt_amounts')
