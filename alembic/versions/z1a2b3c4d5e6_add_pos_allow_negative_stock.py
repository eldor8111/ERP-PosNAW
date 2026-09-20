"""add pos_allow_negative_stock to companies

Revision ID: z1a2b3c4d5e6
Revises: y0z1a2b3c4d5
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'z1a2b3c4d5e6'
down_revision = 'y0z1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('pos_allow_negative_stock', sa.Boolean(), server_default='true', nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'pos_allow_negative_stock')
