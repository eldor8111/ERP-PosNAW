"""add courier bot token/username to companies

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-20

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('courier_bot_token', sa.String(100), nullable=True))
    op.add_column('companies', sa.Column('courier_bot_username', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'courier_bot_username')
    op.drop_column('companies', 'courier_bot_token')
