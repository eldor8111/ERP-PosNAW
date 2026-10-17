"""T3.7: label_templates — yorliq (shtrix-kod) shablonlari serverda (korxona + ixtiyoriy filial)

Revision ID: t3_7
Revises:
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = 't3_7'
down_revision = 't2_12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'label_templates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('branch_id', sa.Integer(), sa.ForeignKey('branches.id', ondelete='SET NULL'), nullable=True),
        sa.Column('kind', sa.String(20), nullable=False, server_default='product'),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.execute("CREATE INDEX ix_label_templates_id ON label_templates (id)")
    op.execute("CREATE INDEX ix_label_templates_company_kind ON label_templates (company_id, kind)")
    # Oddiy UniqueConstraint NULL branch_id ni takrorlashga yo'l qo'yadi — shu sabab COALESCE
    op.execute(
        "CREATE UNIQUE INDEX uq_label_templates_scope "
        "ON label_templates (company_id, kind, name, COALESCE(branch_id, 0))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_label_templates_scope")
    op.execute("DROP INDEX IF EXISTS ix_label_templates_company_kind")
    op.execute("DROP INDEX IF EXISTS ix_label_templates_id")
    op.drop_table('label_templates')
