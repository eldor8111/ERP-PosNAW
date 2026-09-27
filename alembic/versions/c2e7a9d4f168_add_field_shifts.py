"""add field_shifts (mobile work shift)

Revision ID: c2e7a9d4f168
Revises: b8d1f3a6c925
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'c2e7a9d4f168'
down_revision = 'b8d1f3a6c925'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('field_shifts'):
        return
    op.create_table(
        'field_shifts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('start_lat', sa.Numeric(10, 7), nullable=True),
        sa.Column('start_lng', sa.Numeric(10, 7), nullable=True),
        sa.Column('end_lat', sa.Numeric(10, 7), nullable=True),
        sa.Column('end_lng', sa.Numeric(10, 7), nullable=True),
    )
    for col in ('id', 'user_id', 'company_id'):
        op.create_index(f'ix_field_shifts_{col}', 'field_shifts', [col])


def downgrade() -> None:
    op.drop_table('field_shifts')
