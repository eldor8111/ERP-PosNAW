"""add logistics: vehicles, delivery_routes, delivery_route_stops, couriers.vehicle_id

Revision ID: d7e2f5a91c38
Revises: c41d8e9b7a52
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd7e2f5a91c38'
down_revision = 'c41d8e9b7a52'
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    # app.main ishga tushganda yetishmayotgan jadvallarni o'zi yaratadi —
    # shuning uchun mavjud bo'lsa qayta yaratmaymiz
    if not _has_table('vehicles'):
        op.create_table(
            'vehicles',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('plate_number', sa.String(20), nullable=False),
            sa.Column('model', sa.String(100), nullable=True),
            sa.Column('capacity_kg', sa.Numeric(10, 2), nullable=True),
            sa.Column('fuel_type', sa.String(20), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.UniqueConstraint('company_id', 'plate_number', name='uq_company_vehicle_plate'),
        )
        op.create_index('ix_vehicles_id', 'vehicles', ['id'])
        op.create_index('ix_vehicles_company_id', 'vehicles', ['company_id'])

    if not _has_table('delivery_routes'):
        op.create_table(
            'delivery_routes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('number', sa.String(20), nullable=False),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('route_date', sa.Date(), nullable=False),
            sa.Column('courier_id', sa.Integer(), sa.ForeignKey('couriers.id'), nullable=False),
            sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='planned'),
            sa.Column('note', sa.Text(), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=True),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
        )
        for col in ('id', 'number', 'company_id', 'route_date', 'courier_id'):
            op.create_index(f'ix_delivery_routes_{col}', 'delivery_routes', [col])

    if not _has_table('delivery_route_stops'):
        op.create_table(
            'delivery_route_stops',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('route_id', sa.Integer(), sa.ForeignKey('delivery_routes.id', ondelete='CASCADE'), nullable=False),
            sa.Column('group_key', sa.String(50), nullable=False),
            sa.Column('sequence', sa.Integer(), nullable=False),
            sa.UniqueConstraint('route_id', 'group_key', name='uq_route_stop_group'),
        )
        for col in ('id', 'route_id', 'group_key'):
            op.create_index(f'ix_delivery_route_stops_{col}', 'delivery_route_stops', [col])

    cols = [c['name'] for c in sa.inspect(op.get_bind()).get_columns('couriers')]
    if 'vehicle_id' not in cols:
        op.add_column('couriers', sa.Column('vehicle_id', sa.Integer(), sa.ForeignKey('vehicles.id'), nullable=True))


def downgrade() -> None:
    op.drop_column('couriers', 'vehicle_id')
    op.drop_table('delivery_route_stops')
    op.drop_table('delivery_routes')
    op.drop_table('vehicles')
