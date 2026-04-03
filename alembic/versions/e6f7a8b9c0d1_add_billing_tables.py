"""add billing tables: tariffs, balance_logs, company billing columns

Revision ID: e6f7a8b9c0d1
Revises: a9f1b2c3d4e5
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = 'e6f7a8b9c0d1'
down_revision = 'a9f1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    # ── 1. tariffs jadvali ────────────────────────────────────
    op.create_table(
        'tariffs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price_per_month', sa.Numeric(12, 2), default=0),
        sa.Column('duration_days', sa.Integer(), default=30),
        sa.Column('max_users', sa.Integer(), default=5),
        sa.Column('max_branches', sa.Integer(), default=1),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── 2. balance_logs jadvali ───────────────────────────────
    op.create_table(
        'balance_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('log_type', sa.String(30), nullable=False),
        sa.Column('note', sa.String(255), nullable=True),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    # ── 3. companies ga billing ustunlari ─────────────────────
    op.add_column('companies', sa.Column('tariff_id', sa.Integer(),
                  sa.ForeignKey('tariffs.id'), nullable=True))
    op.add_column('companies', sa.Column('subscription_ends_at', sa.DateTime(), nullable=True))
    op.add_column('companies', sa.Column('is_trial', sa.Boolean(), nullable=True,
                  server_default=sa.text('FALSE')))

    # ── 4. Default tariflarni qo'shish ────────────────────────
    op.execute("""
        INSERT INTO tariffs (name, description, price_per_month, duration_days, max_users, max_branches, is_active, sort_order, created_at)
        VALUES
          ('Sinov (Trial)', '7 kunlik bepul sinov muddati', 0, 7, 5, 1, TRUE, 0, NOW()),
          ('Boshlang''ich', 'Kichik do''konlar uchun', 150000, 30, 10, 2, TRUE, 1, NOW()),
          ('Professional', 'O''rta biznes uchun', 300000, 30, 30, 5, TRUE, 2, NOW()),
          ('Enterprise', 'Yirik tarmoqlar uchun', 600000, 30, 9999, 9999, TRUE, 3, NOW())
    """)


def downgrade():
    op.drop_column('companies', 'is_trial')
    op.drop_column('companies', 'subscription_ends_at')
    op.drop_column('companies', 'tariff_id')
    op.drop_table('balance_logs')
    op.drop_table('tariffs')
