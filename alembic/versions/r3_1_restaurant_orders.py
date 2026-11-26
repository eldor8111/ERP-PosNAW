"""R3: restoran cheklari — restaurant_orders, restaurant_order_items, kitchen_tickets, users.pin_hash.

Additiv va takroriy xavfsiz.

Revision ID: r3_1
Revises: r1_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r3_1'
down_revision: Union[str, Sequence[str], None] = 'r1_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp():
    from alembic import context
    if context.is_offline_mode():
        return None
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    insp = _insp()
    tables = set(insp.get_table_names()) if insp is not None else set()

    if insp is None or 'pin_hash' not in {c['name'] for c in insp.get_columns('users')}:
        op.add_column('users', sa.Column('pin_hash', sa.String(200), nullable=True))

    if 'restaurant_orders' not in tables:
        op.create_table(
            'restaurant_orders',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
            sa.Column('number', sa.String(40), nullable=False),
            sa.Column('daily_no', sa.Integer(), nullable=False),
            sa.Column('order_type', sa.String(20), nullable=False, server_default='dine_in'),
            sa.Column('table_id', sa.Integer(), sa.ForeignKey('restaurant_tables.id', ondelete='SET NULL'), nullable=True),
            sa.Column('hall_id', sa.Integer(), sa.ForeignKey('halls.id', ondelete='SET NULL'), nullable=True),
            sa.Column('guests', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('waiter_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='open'),
            sa.Column('subtotal', sa.Numeric(16, 2), nullable=False, server_default='0'),
            sa.Column('discount_pct', sa.Numeric(5, 2), nullable=True),
            sa.Column('discount_amount', sa.Numeric(16, 2), nullable=False, server_default='0'),
            sa.Column('discount_reason', sa.String(200), nullable=True),
            sa.Column('service_pct', sa.Numeric(5, 2), nullable=False, server_default='0'),
            sa.Column('service_amount', sa.Numeric(16, 2), nullable=False, server_default='0'),
            sa.Column('total', sa.Numeric(16, 2), nullable=False, server_default='0'),
            sa.Column('comment', sa.String(500), nullable=True),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('sale_id', sa.Integer(), sa.ForeignKey('sales.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('opened_at', sa.DateTime(), nullable=True),
            sa.Column('prechecked_at', sa.DateTime(), nullable=True),
            sa.Column('closed_at', sa.DateTime(), nullable=True),
            sa.Column('cancelled_at', sa.DateTime(), nullable=True),
            sa.Column('cancel_reason', sa.String(300), nullable=True),
            sa.Column('merged_into_id', sa.Integer(), sa.ForeignKey('restaurant_orders.id', ondelete='SET NULL'),
                      nullable=True),
            sa.CheckConstraint("order_type IN ('dine_in','takeaway','delivery')", name='ck_rest_orders_type'),
            sa.CheckConstraint("status IN ('open','prechecked','paid','cancelled')", name='ck_rest_orders_status'),
        )
        op.create_index('ix_restaurant_orders_id', 'restaurant_orders', ['id'])
        op.create_index('ix_restaurant_orders_company_id', 'restaurant_orders', ['company_id'])
        op.create_index('ix_restaurant_orders_branch_id', 'restaurant_orders', ['branch_id'])
        op.create_index('ix_restaurant_orders_table_id', 'restaurant_orders', ['table_id'])
        op.create_index('ix_restaurant_orders_waiter_id', 'restaurant_orders', ['waiter_id'])
        op.create_index('ix_rest_orders_branch_status', 'restaurant_orders', ['company_id', 'branch_id', 'status'])

    if 'restaurant_order_items' not in tables:
        op.create_table(
            'restaurant_order_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('order_id', sa.Integer(), sa.ForeignKey('restaurant_orders.id', ondelete='CASCADE'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('bom_id', sa.Integer(), sa.ForeignKey('boms.id', ondelete='SET NULL'), nullable=True),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
            sa.Column('unit_price', sa.Numeric(16, 2), nullable=False),
            sa.Column('modifiers', sa.JSON(), nullable=True),
            sa.Column('modifiers_total', sa.Numeric(16, 2), nullable=False, server_default='0'),
            sa.Column('course', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('guest_no', sa.Integer(), nullable=True),
            sa.Column('station_id', sa.Integer(), sa.ForeignKey('kitchen_stations.id', ondelete='SET NULL'), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
            sa.Column('comment', sa.String(300), nullable=True),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('sent_at', sa.DateTime(), nullable=True),
            sa.Column('cooking_at', sa.DateTime(), nullable=True),
            sa.Column('ready_at', sa.DateTime(), nullable=True),
            sa.Column('served_at', sa.DateTime(), nullable=True),
            sa.Column('cancelled_at', sa.DateTime(), nullable=True),
            sa.Column('cancel_reason', sa.String(300), nullable=True),
            sa.Column('cancelled_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('cancel_approved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('write_off', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.CheckConstraint("status IN ('draft','sent','cooking','ready','served','cancelled')",
                               name='ck_rest_order_items_status'),
            sa.CheckConstraint('quantity > 0', name='ck_rest_order_items_qty'),
        )
        op.create_index('ix_restaurant_order_items_id', 'restaurant_order_items', ['id'])
        op.create_index('ix_restaurant_order_items_company_id', 'restaurant_order_items', ['company_id'])
        op.create_index('ix_restaurant_order_items_order_id', 'restaurant_order_items', ['order_id'])

    if 'kitchen_tickets' not in tables:
        op.create_table(
            'kitchen_tickets',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id'), nullable=False),
            sa.Column('order_id', sa.Integer(), sa.ForeignKey('restaurant_orders.id', ondelete='CASCADE'), nullable=False),
            sa.Column('station_id', sa.Integer(), sa.ForeignKey('kitchen_stations.id', ondelete='SET NULL'), nullable=True),
            sa.Column('kind', sa.String(10), nullable=False, server_default='order'),
            sa.Column('lines', sa.JSON(), nullable=False),
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('printed_at', sa.DateTime(), nullable=True),
            sa.Column('print_attempts', sa.Integer(), nullable=False, server_default='0'),
        )
        op.create_index('ix_kitchen_tickets_id', 'kitchen_tickets', ['id'])
        op.create_index('ix_kitchen_tickets_company_id', 'kitchen_tickets', ['company_id'])
        op.create_index('ix_kitchen_tickets_branch_id', 'kitchen_tickets', ['branch_id'])
        op.create_index('ix_kitchen_tickets_order_id', 'kitchen_tickets', ['order_id'])


def downgrade() -> None:
    op.drop_table('kitchen_tickets')
    op.drop_table('restaurant_order_items')
    op.drop_table('restaurant_orders')
    op.drop_column('users', 'pin_hash')
