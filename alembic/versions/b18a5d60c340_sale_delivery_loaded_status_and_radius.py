"""sale_delivery_loaded_status_and_radius

Revision ID: b18a5d60c340
Revises: e1f2a3b4c5d6
Create Date: 2026-10-13 18:08:44.457865

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b18a5d60c340'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    
    # 1. sale_deliveries columns
    sd_cols = [c['name'] for c in insp.get_columns('sale_deliveries')]
    if 'loaded_at' not in sd_cols:
        op.add_column('sale_deliveries', sa.Column('loaded_at', sa.DateTime(), nullable=True))
    if 'loaded_by' not in sd_cols:
        op.add_column('sale_deliveries', sa.Column('loaded_by', sa.Integer(), nullable=True))
    if 'delivery_radius_m' not in sd_cols:
        op.add_column('sale_deliveries', sa.Column('delivery_radius_m', sa.Integer(), nullable=True))
    if 'stock_deducted' not in sd_cols:
        op.add_column('sale_deliveries', sa.Column('stock_deducted', sa.Boolean(), server_default='false', nullable=False))

    # 2. companies columns
    comp_cols = [c['name'] for c in insp.get_columns('companies')]
    if 'stock_deduct_stage' not in comp_cols:
        op.add_column('companies', sa.Column('stock_deduct_stage', sa.String(length=30), server_default='order_confirmed', nullable=False))
    if 'agent_order_geo_radius_check' not in comp_cols:
        op.add_column('companies', sa.Column('agent_order_geo_radius_check', sa.Boolean(), server_default='true', nullable=False))
    if 'default_delivery_radius_m' not in comp_cols:
        op.add_column('companies', sa.Column('default_delivery_radius_m', sa.Integer(), server_default='250', nullable=False))


def downgrade() -> None:
    op.drop_column('sale_deliveries', 'stock_deducted')
    op.drop_column('sale_deliveries', 'delivery_radius_m')
    op.drop_column('sale_deliveries', 'loaded_by')
    op.drop_column('sale_deliveries', 'loaded_at')
    op.drop_column('companies', 'default_delivery_radius_m')
    op.drop_column('companies', 'agent_order_geo_radius_check')
    op.drop_column('companies', 'stock_deduct_stage')
