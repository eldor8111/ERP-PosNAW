"""add admin bot settings

Revision ID: v7w8x9y0z1a2
Revises: u6v7w8x9y0z1
Create Date: 2026-08-07 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'v7w8x9y0z1a2'
down_revision = 'u6v7w8x9y0z1'
branch_labels = None
depends_on = None


def upgrade():
    # Drop unique constraint on company_id
    try:
        op.drop_constraint('company_bots_company_id_key', 'company_bots', type_='unique')
    except Exception:
        pass
        
    try:
        op.drop_constraint('uq_company_bots_company_id', 'company_bots', type_='unique')
    except Exception:
        pass
        
    # Add new columns
    op.add_column('company_bots', sa.Column('notify_instant_sales', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('company_bots', sa.Column('notify_instant_finance', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('company_bots', sa.Column('notify_scheduled', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('company_bots', sa.Column('scheduled_time', sa.String(length=5), server_default='20:00', nullable=True))
    
    # Add unique constraint for company_id and bot_type
    op.create_unique_constraint('uq_company_bot_type', 'company_bots', ['company_id', 'bot_type'])


def downgrade():
    op.drop_constraint('uq_company_bot_type', 'company_bots', type_='unique')
    
    op.drop_column('company_bots', 'scheduled_time')
    op.drop_column('company_bots', 'notify_scheduled')
    op.drop_column('company_bots', 'notify_instant_finance')
    op.drop_column('company_bots', 'notify_instant_sales')
    
    op.create_unique_constraint('company_bots_company_id_key', 'company_bots', ['company_id'])
