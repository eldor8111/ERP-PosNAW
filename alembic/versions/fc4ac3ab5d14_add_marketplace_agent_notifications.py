"""Add marketplace agent notifications

Revision ID: fc4ac3ab5d14
Revises: fc4ac3ab5d13
Create Date: 2026-10-10 15:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'fc4ac3ab5d14'
down_revision: Union[str, None] = 'fc4ac3ab5d13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'marketplace_agent_notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.String(length=1000), nullable=False),
        sa.Column('notif_type', sa.String(length=50), nullable=True, server_default='general'),
        sa.Column('data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['agent_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_marketplace_agent_notifications_agent_id'), 'marketplace_agent_notifications', ['agent_id'], unique=False)
    op.create_index(op.f('ix_marketplace_agent_notifications_id'), 'marketplace_agent_notifications', ['id'], unique=False)
    op.create_index(op.f('ix_marketplace_agent_notifications_is_read'), 'marketplace_agent_notifications', ['is_read'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_marketplace_agent_notifications_is_read'), table_name='marketplace_agent_notifications')
    op.drop_index(op.f('ix_marketplace_agent_notifications_id'), table_name='marketplace_agent_notifications')
    op.drop_index(op.f('ix_marketplace_agent_notifications_agent_id'), table_name='marketplace_agent_notifications')
    op.drop_table('marketplace_agent_notifications')
