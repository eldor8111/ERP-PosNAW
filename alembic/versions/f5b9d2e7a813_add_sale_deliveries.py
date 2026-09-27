"""add sale_deliveries (delivery from wholesale sale screen)

Revision ID: f5b9d2e7a813
Revises: e8a3c6f14b27
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f5b9d2e7a813'
down_revision = 'e8a3c6f14b27'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('sale_deliveries'):
        return
    op.create_table(
        'sale_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('address', sa.String(500), nullable=True),
        sa.Column('lat', sa.Numeric(10, 7), nullable=True),
        sa.Column('lng', sa.Numeric(10, 7), nullable=True),
        sa.Column('contact_phone', sa.String(32), nullable=True),
        sa.Column('delivery_fee', sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('planned_date', sa.Date(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('courier_id', sa.Integer(), sa.ForeignKey('couriers.id'), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('on_way_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('cancel_reason', sa.String(300), nullable=True),
        sa.Column('fee_recorded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('sale_id', name='uq_sale_deliveries_sale_id'),
    )
    for col in ('id', 'sale_id', 'company_id', 'status', 'courier_id'):
        op.create_index(f'ix_sale_deliveries_{col}', 'sale_deliveries', [col])


def downgrade() -> None:
    op.drop_table('sale_deliveries')
