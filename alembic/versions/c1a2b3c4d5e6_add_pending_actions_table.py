"""add_pending_actions_table

Revision ID: c1a2b3c4d5e6
Revises: b18a5d60c340
Create Date: 2026-10-16 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3c4d5e6'
down_revision: Union[str, None] = 'b18a5d60c340'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = insp.get_table_names()

    if 'pending_actions' not in tables:
        op.create_table(
            'pending_actions',
            sa.Column('id', sa.String(length=50), primary_key=True, nullable=False),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('tool_name', sa.String(length=100), nullable=False),
            sa.Column('tool_arguments', sa.JSON(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('executed_at', sa.DateTime(), nullable=True),
            sa.Column('result_summary', sa.Text(), nullable=True),
        )
        op.create_index('ix_pending_actions_id', 'pending_actions', ['id'])
        op.create_index('ix_pending_actions_company_id', 'pending_actions', ['company_id'])
        op.create_index('ix_pending_actions_user_id', 'pending_actions', ['user_id'])
        op.create_index('ix_pending_actions_tool_name', 'pending_actions', ['tool_name'])
        op.create_index('ix_pending_actions_status', 'pending_actions', ['status'])
        op.create_index('ix_pending_actions_expires_at', 'pending_actions', ['expires_at'])


def downgrade() -> None:
    op.drop_table('pending_actions')
