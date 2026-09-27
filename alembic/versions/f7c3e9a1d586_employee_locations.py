"""employee_locations (GPS tracking during shift)

Revision ID: f7c3e9a1d586
Revises: e1a5c8f2b407
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'f7c3e9a1d586'
down_revision = 'e1a5c8f2b407'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('employee_locations'):
        return
    op.create_table(
        'employee_locations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('lat', sa.Numeric(10, 7), nullable=False),
        sa.Column('lng', sa.Numeric(10, 7), nullable=False),
        sa.Column('accuracy', sa.Integer(), nullable=True),
        sa.Column('speed', sa.Numeric(6, 2), nullable=True),
        sa.Column('battery', sa.Integer(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('received_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_employee_locations_user_time', 'employee_locations', ['user_id', 'recorded_at'])
    op.create_index('ix_employee_locations_company_time', 'employee_locations', ['company_id', 'recorded_at'])


def downgrade() -> None:
    op.drop_table('employee_locations')
