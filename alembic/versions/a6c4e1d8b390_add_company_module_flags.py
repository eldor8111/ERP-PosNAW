"""company module flags: manufacturing_enabled, distribution_enabled

Revision ID: a6c4e1d8b390
Revises: f5b9d2e7a813
Create Date: 2026-09-27

Mavjud ma'lumoti bor kompaniyalarda modul avtomatik yoqiladi — yangilanishdan
keyin ularning bo'limlari yo'qolib qolmasligi uchun.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a6c4e1d8b390'
down_revision = 'f5b9d2e7a813'
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('companies')}
    if 'manufacturing_enabled' not in existing:
        op.add_column('companies', sa.Column('manufacturing_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    if 'distribution_enabled' not in existing:
        op.add_column('companies', sa.Column('distribution_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.execute("""
        UPDATE companies SET manufacturing_enabled = true
        WHERE id IN (SELECT company_id FROM boms UNION SELECT company_id FROM production_orders)
    """)
    op.execute("""
        UPDATE companies SET distribution_enabled = true
        WHERE id IN (
            SELECT company_id FROM customers WHERE customer_type = 'distributor'
            UNION SELECT company_id FROM vehicles
            UNION SELECT company_id FROM delivery_routes
            UNION SELECT company_id FROM sale_deliveries
        )
    """)


def downgrade() -> None:
    op.drop_column('companies', 'distribution_enabled')
    op.drop_column('companies', 'manufacturing_enabled')
