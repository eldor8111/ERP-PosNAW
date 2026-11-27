"""R8.1: stol bron qilish — reservations.

Additiv va takroriy xavfsiz.

Revision ID: r8_1
Revises: r7_5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r8_1'
down_revision: Union[str, Sequence[str], None] = 'r7_5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables():
    from alembic import context
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 'deposit' faqat sale_payments.payment_type (String) ga yoziladi; sales.payment_type (native enum) ga
    # depozitli chekda 'mixed' yoziladi, shuning uchun paymenttype enumini o'zgartirish shart emas
    # (prod DB foydalanuvchisi enum turining egasi emas: ALTER TYPE ruxsat etilmaydi).
    if 'reservations' in _tables():
        return
    op.create_table(
        'reservations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('table_ids', sa.JSON(), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('duration_min', sa.Integer(), nullable=False),
        sa.Column('guests', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('phone', sa.String(30), nullable=True),
        sa.Column('note', sa.String(500), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='booked'),
        sa.Column('deposit_amount', sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('deposit_type', sa.String(20), nullable=True),
        sa.Column('deposit_wallet_id', sa.Integer(), sa.ForeignKey('wallets.id', ondelete='SET NULL'), nullable=True),
        sa.Column('deposit_status', sa.String(20), nullable=True),
        sa.Column('deposit_applied', sa.Numeric(14, 2), nullable=False, server_default='0'),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('restaurant_orders.id', ondelete='SET NULL'), nullable=True),
        sa.Column('cancel_reason', sa.String(200), nullable=True),
        sa.Column('reminded_at', sa.DateTime(), nullable=True),
        sa.Column('remind_channel', sa.String(20), nullable=True),
        sa.Column('arrived_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    for col in ('company_id', 'branch_id', 'starts_at', 'ends_at', 'customer_id', 'order_id'):
        op.create_index(f'ix_reservations_{col}', 'reservations', [col])


def downgrade() -> None:
    op.drop_table('reservations')
