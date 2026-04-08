"""add_tg_chat_id_to_users

Revision ID: f1a2b3c4d5e6
Revises: 0dbc9cb2bab2
Create Date: 2026-04-08 23:23:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f1a2b3c4d5e6'
down_revision = '0dbc9cb2bab2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('tg_chat_id', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'tg_chat_id')
