"""add_user_companies_table

Revision ID: c3d4e5f6a7b8
Revises: a9f1b2c3d4e5
Create Date: 2026-04-15 09:18:00.000000

Multi-korxona qo'llab-quvvatlash uchun user_companies jadvali qo'shiladi.
Mavjud users.company_id maydoni saqlanadi (backward compat.).
"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'a9f1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. user_companies jadvali yaratish
    op.create_table(
        'user_companies',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.Enum(
            'super_admin', 'admin', 'director', 'manager',
            'accountant', 'warehouse', 'cashier',
            name='userrole'
        ), nullable=False, server_default='cashier'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('user_id', 'company_id', name='uq_user_company'),
    )
    op.create_index('ix_user_companies_user_id', 'user_companies', ['user_id'])
    op.create_index('ix_user_companies_company_id', 'user_companies', ['company_id'])

    # 2. Mavjud foydalanuvchilarni ko'chirish (data migration)
    #    users.company_id bo'lganlarni user_companies ga qo'shamiz
    op.execute("""
        INSERT INTO user_companies (user_id, company_id, role, is_active, created_at)
        SELECT
            id,
            company_id,
            role,
            CASE WHEN status = 'active' THEN TRUE ELSE FALSE END,
            created_at
        FROM users
        WHERE company_id IS NOT NULL
        ON CONFLICT (user_id, company_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index('ix_user_companies_company_id', 'user_companies')
    op.drop_index('ix_user_companies_user_id', 'user_companies')
    op.drop_table('user_companies')
