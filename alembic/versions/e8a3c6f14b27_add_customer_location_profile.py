"""customer location/profile fields + customer_documents

Revision ID: e8a3c6f14b27
Revises: d7e2f5a91c38
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e8a3c6f14b27'
down_revision = 'd7e2f5a91c38'
branch_labels = None
depends_on = None

NEW_COLS = [
    sa.Column('region', sa.String(100), nullable=True),
    sa.Column('district', sa.String(100), nullable=True),
    sa.Column('address', sa.String(500), nullable=True),
    sa.Column('lat', sa.Numeric(10, 7), nullable=True),
    sa.Column('lng', sa.Numeric(10, 7), nullable=True),
    sa.Column('location_source', sa.String(20), nullable=True),
    sa.Column('extra_phones', sa.JSON(), nullable=False, server_default='[]'),
    sa.Column('agent_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
    sa.Column('work_days', sa.JSON(), nullable=False, server_default='[]'),
    sa.Column('visit_radius_m', sa.Integer(), nullable=True),
    sa.Column('photo_url', sa.String(300), nullable=True),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('customers')}
    for col in NEW_COLS:
        if col.name not in existing:
            op.add_column('customers', col)
    if 'agent_id' not in existing:
        op.create_index('ix_customers_agent_id', 'customers', ['agent_id'])

    if not sa.inspect(bind).has_table('customer_documents'):
        op.create_table(
            'customer_documents',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
            sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('file_path', sa.String(300), nullable=False),
            sa.Column('original_name', sa.String(255), nullable=False),
            sa.Column('content_type', sa.String(100), nullable=True),
            sa.Column('size', sa.Integer(), nullable=True),
            sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )
        for col in ('id', 'customer_id', 'company_id'):
            op.create_index(f'ix_customer_documents_{col}', 'customer_documents', [col])


def downgrade() -> None:
    op.drop_table('customer_documents')
    op.drop_index('ix_customers_agent_id', table_name='customers')
    for col in reversed(NEW_COLS):
        op.drop_column('customers', col.name)
