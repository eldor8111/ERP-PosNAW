"""mobile app: courier/agent roles, mobile_devices, couriers.user_id

Revision ID: b8d1f3a6c925
Revises: a6c4e1d8b390
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b8d1f3a6c925'
down_revision = 'a6c4e1d8b390'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres enum'ga qiymat tranzaksiya ichida qo'shilmaydi
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'courier'")
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'agent'")

    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'user_id' not in {c['name'] for c in insp.get_columns('couriers')}:
        op.add_column('couriers', sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
        op.create_index('ix_couriers_user_id', 'couriers', ['user_id'])

    if not insp.has_table('mobile_devices'):
        op.create_table(
            'mobile_devices',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=True),
            sa.Column('device_id', sa.String(100), nullable=False),
            sa.Column('platform', sa.String(20), nullable=True),
            sa.Column('model', sa.String(100), nullable=True),
            sa.Column('app_version', sa.String(20), nullable=True),
            sa.Column('fcm_token', sa.String(300), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('last_seen_at', sa.DateTime(), nullable=True),
            sa.Column('revoked_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('user_id', 'device_id', name='uq_mobile_device_user_device'),
        )
        for col in ('id', 'user_id', 'company_id'):
            op.create_index(f'ix_mobile_devices_{col}', 'mobile_devices', [col])


def downgrade() -> None:
    op.drop_table('mobile_devices')
    op.drop_index('ix_couriers_user_id', table_name='couriers')
    op.drop_column('couriers', 'user_id')
    # Enum qiymatlarini Postgres'da olib tashlab bo'lmaydi — qoldiriladi
