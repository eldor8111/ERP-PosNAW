"""add_attribute_name_to_tovarlar_catalog

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-06-12 16:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'n8o9p0q1r2s3'
down_revision: Union[str, None] = 'm7n8o9p0q1r2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name='tovarlar_catalog' AND column_name='attribute_name')"
    )).scalar()
    if not exists:
        op.add_column('tovarlar_catalog', sa.Column('attribute_name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tovarlar_catalog', 'attribute_name')
