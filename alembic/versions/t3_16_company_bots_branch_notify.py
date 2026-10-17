"""T3.16: company_bots — filial menejerlariga yuborish va hisobotda filiallar bo'limi

Faqat additiv: ikkita NOT NULL ustun, server_default=true (mavjud qatorlar o'zi to'ladi).
companies.daily_report_recipients qiymatlari o'zgarmaydi (default owners_and_admins).

Revision ID: t3_16
Revises:
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = 't3_16'
down_revision = 't3_15'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('company_bots', sa.Column('notify_branch_managers', sa.Boolean(), nullable=False,
                                            server_default=sa.true()))
    op.add_column('company_bots', sa.Column('report_by_branch', sa.Boolean(), nullable=False,
                                            server_default=sa.true()))


def downgrade() -> None:
    op.drop_column('company_bots', 'report_by_branch')
    op.drop_column('company_bots', 'notify_branch_managers')
