"""mobile_idempotency, delivery_proofs

Revision ID: d4f8b2c6e731
Revises: c2e7a9d4f168
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'd4f8b2c6e731'
down_revision = 'c2e7a9d4f168'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table('mobile_idempotency'):
        op.create_table(
            'mobile_idempotency',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('key', sa.String(64), nullable=False),
            sa.Column('endpoint', sa.String(100), nullable=False),
            sa.Column('response', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('user_id', 'key', name='uq_mobile_idem_user_key'),
        )
        op.create_index('ix_mobile_idempotency_user_id', 'mobile_idempotency', ['user_id'])
    if not insp.has_table('delivery_proofs'):
        op.create_table(
            'delivery_proofs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('stop_key', sa.String(50), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('photo_path', sa.String(300), nullable=True),
            sa.Column('lat', sa.Numeric(10, 7), nullable=True),
            sa.Column('lng', sa.Numeric(10, 7), nullable=True),
            sa.Column('distance_m', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        for col in ('id', 'company_id', 'stop_key'):
            op.create_index(f'ix_delivery_proofs_{col}', 'delivery_proofs', [col])


def downgrade() -> None:
    op.drop_table('delivery_proofs')
    op.drop_table('mobile_idempotency')
