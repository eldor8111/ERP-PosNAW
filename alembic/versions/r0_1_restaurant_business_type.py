"""R0.2/R0.3: restoran rejimi — companies.business_type, companies.restaurant_settings, tariffs.business_type,
kitchen_stations, halls, restaurant_tables jadvallari.

Additiv va takroriy xavfsiz: mavjud korxonalar 'retail' bo'ladi, ularning ma'lumotiga tegilmaydi.
(app/main.py startup ALTERlari ustunlarni oldinroq qo'shgan bo'lishi mumkin — shuning uchun tekshiriladi.)

Revision ID: r0_1
Revises: ai_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r0_1'
down_revision: Union[str, Sequence[str], None] = 'ai_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp():
    from alembic import context
    if context.is_offline_mode():   # --sql rejimi: bazaga ulanmasdan SQL chiqarish
        return None
    return sa.inspect(op.get_bind())


def _cols(insp, table):
    if insp is None:
        return set()
    return {c['name'] for c in insp.get_columns(table)}


def _checks(insp, table):
    if insp is None:
        return set()
    try:
        return {c['name'] for c in insp.get_check_constraints(table)}
    except NotImplementedError:
        return set()


def upgrade() -> None:
    insp = _insp()
    tables = set(insp.get_table_names()) if insp is not None else set()

    company_cols = _cols(insp, 'companies')
    if 'business_type' not in company_cols:
        op.add_column('companies', sa.Column('business_type', sa.String(20), nullable=False, server_default='retail'))
    if 'restaurant_settings' not in company_cols:
        op.add_column('companies', sa.Column('restaurant_settings', sa.JSON(), nullable=True))
    if 'ck_companies_business_type' not in _checks(insp, 'companies'):
        op.create_check_constraint('ck_companies_business_type', 'companies',
                                   "business_type IN ('retail','restaurant')")

    if 'business_type' not in _cols(insp, 'tariffs'):
        op.add_column('tariffs', sa.Column('business_type', sa.String(20), nullable=False, server_default='retail'))

    if 'kitchen_stations' not in tables:
        op.create_table(
            'kitchen_stations',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('kds_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_kitchen_stations_id', 'kitchen_stations', ['id'])
        op.create_index('ix_kitchen_stations_company_id', 'kitchen_stations', ['company_id'])

    if 'halls' not in tables:
        op.create_table(
            'halls',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('service_pct', sa.Numeric(5, 2), nullable=True),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_halls_id', 'halls', ['id'])
        op.create_index('ix_halls_company_id', 'halls', ['company_id'])
        op.create_index('ix_halls_branch_id', 'halls', ['branch_id'])

    if 'restaurant_tables' not in tables:
        op.create_table(
            'restaurant_tables',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
            sa.Column('hall_id', sa.Integer(), sa.ForeignKey('halls.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(50), nullable=False),
            sa.Column('seats', sa.Integer(), nullable=False, server_default='4'),
            sa.Column('x', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('y', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('w', sa.Integer(), nullable=False, server_default='2'),
            sa.Column('h', sa.Integer(), nullable=False, server_default='2'),
            sa.Column('shape', sa.String(10), nullable=False, server_default='rect'),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_restaurant_tables_id', 'restaurant_tables', ['id'])
        op.create_index('ix_restaurant_tables_company_id', 'restaurant_tables', ['company_id'])
        op.create_index('ix_restaurant_tables_hall_id', 'restaurant_tables', ['hall_id'])


def downgrade() -> None:
    insp = _insp()
    tables = set(insp.get_table_names()) if insp is not None else {'restaurant_tables', 'halls', 'kitchen_stations'}
    for t in ('restaurant_tables', 'halls', 'kitchen_stations'):
        if t in tables:
            op.drop_table(t)
    if insp is None or 'business_type' in _cols(insp, 'tariffs'):
        op.drop_column('tariffs', 'business_type')
    if insp is None or 'ck_companies_business_type' in _checks(insp, 'companies'):
        op.drop_constraint('ck_companies_business_type', 'companies', type_='check')
    company_cols = _cols(insp, 'companies') if insp is not None else {'restaurant_settings', 'business_type'}
    if 'restaurant_settings' in company_cols:
        op.drop_column('companies', 'restaurant_settings')
    if 'business_type' in company_cols:
        op.drop_column('companies', 'business_type')
