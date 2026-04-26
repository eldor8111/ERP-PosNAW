"""add platform_settings table

Revision ID: g1h2i3j4k5l6
Revises: c3d4e5f6a7b8
Create Date: 2026-04-27

"""
from alembic import op
import sqlalchemy as sa

revision = 'g1h2i3j4k5l6'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'platform_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.String(length=500), nullable=True),
        sa.Column('label', sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.create_index('ix_platform_settings_id', 'platform_settings', ['id'])
    op.create_index('ix_platform_settings_key', 'platform_settings', ['key'])


def downgrade():
    op.drop_index('ix_platform_settings_key', table_name='platform_settings')
    op.drop_index('ix_platform_settings_id', table_name='platform_settings')
    op.drop_table('platform_settings')
