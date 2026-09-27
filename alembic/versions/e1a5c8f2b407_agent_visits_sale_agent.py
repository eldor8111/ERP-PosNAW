"""agent_visits, sales.agent_id

Revision ID: e1a5c8f2b407
Revises: d4f8b2c6e731
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = 'e1a5c8f2b407'
down_revision = 'd4f8b2c6e731'
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if 'agent_id' not in {c['name'] for c in insp.get_columns('sales')}:
        op.add_column('sales', sa.Column('agent_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
        op.create_index('ix_sales_agent_id', 'sales', ['agent_id'])
    if not insp.has_table('agent_visits'):
        op.create_table(
            'agent_visits',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('agent_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
            sa.Column('planned', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('check_in_at', sa.DateTime(), nullable=False),
            sa.Column('lat', sa.Numeric(10, 7), nullable=True),
            sa.Column('lng', sa.Numeric(10, 7), nullable=True),
            sa.Column('distance_m', sa.Integer(), nullable=True),
            sa.Column('within_radius', sa.Boolean(), nullable=True),
            sa.Column('check_out_at', sa.DateTime(), nullable=True),
            sa.Column('result', sa.String(20), nullable=True),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('photo_path', sa.String(300), nullable=True),
        )
        for col in ('id', 'company_id', 'agent_id', 'customer_id', 'check_in_at'):
            op.create_index(f'ix_agent_visits_{col}', 'agent_visits', [col])


def downgrade() -> None:
    op.drop_table('agent_visits')
    op.drop_index('ix_sales_agent_id', table_name='sales')
    op.drop_column('sales', 'agent_id')
