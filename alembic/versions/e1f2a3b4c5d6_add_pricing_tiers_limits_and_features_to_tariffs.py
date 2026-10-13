"""add pricing tiers limits and features to tariffs

Revision ID: e1f2a3b4c5d6
Revises: dd7268ae19c3
Create Date: 2026-10-13 15:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'dd7268ae19c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS max_warehouses INTEGER DEFAULT 1;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS max_products INTEGER;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS max_agents INTEGER DEFAULT 0;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS max_couriers INTEGER DEFAULT 0;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS max_monthly_orders INTEGER;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS max_production_orders INTEGER;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS min_duration_months INTEGER DEFAULT 1;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS has_pnl_compare BOOLEAN DEFAULT FALSE;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS has_manufacturing BOOLEAN DEFAULT FALSE;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS has_distribution BOOLEAN DEFAULT FALSE;")
    op.execute("ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS period_discounts JSON;")


def downgrade() -> None:
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS max_warehouses;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS max_products;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS max_agents;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS max_couriers;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS max_monthly_orders;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS max_production_orders;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS min_duration_months;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS has_pnl_compare;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS has_manufacturing;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS has_distribution;")
    op.execute("ALTER TABLE tariffs DROP COLUMN IF EXISTS period_discounts;")
