"""check_product_new_columns

Revision ID: 2bc53fc213d4
Revises: fb5a84d57e55
Create Date: 2026-06-15 16:56:26.000726

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '2bc53fc213d4'
down_revision: Union[str, None] = 'fb5a84d57e55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('cost_currency', sa.String(length=3), server_default='UZS', nullable=False))
    op.add_column('products', sa.Column('sale_currency', sa.String(length=3), server_default='UZS', nullable=False))


def downgrade() -> None:
    op.drop_column('products', 'sale_currency')
    op.drop_column('products', 'cost_currency')
