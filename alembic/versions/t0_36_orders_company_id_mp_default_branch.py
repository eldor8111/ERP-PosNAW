"""T0.36: orders.company_id (customers dan to'ldiriladi) + companies.marketplace_default_branch_id

Mir-maza/Telegram buyurtmalarini korxonaga to'g'ri bog'lash uchun:
1. orders.company_id — nullable qo'shiladi, customers.company_id dan to'ldiriladi,
   bo'sh qator qolmasa NOT NULL qilinadi; FK + indekslar (company_id, company_id+order_group_id).
   Filiali boshqa korxonaga tegishli buyurtmalar soni diagnostika uchun chop etiladi
   (avtomatik tuzatilmaydi — T0.7/T0.25 da qo'lda ko'rib chiqiladi).
2. companies.marketplace_default_branch_id — Mir-maza buyurtmalari uchun asosiy filial
   (FK branches.id, ondelete SET NULL).

Revision ID: t0_36
Revises: t0_35
"""
from alembic import op
import sqlalchemy as sa


revision = 't0_36'
down_revision = 't0_35'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Ustun (avval nullable)
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS company_id INTEGER NULL")

    # 2. Backfill: 1-navbatda mijoz korxonasi, 2-navbatda filial korxonasi, 3-navbatda birinchi korxona
    op.execute("""
        UPDATE orders SET company_id = c.company_id 
        FROM customers c WHERE c.id = orders.customer_id AND orders.company_id IS NULL;

        UPDATE orders SET company_id = b.company_id 
        FROM branches b WHERE b.id = orders.branch_id AND orders.company_id IS NULL;

        UPDATE orders SET company_id = (SELECT id FROM companies ORDER BY id LIMIT 1) 
        WHERE company_id IS NULL;
    """)

    # 3. NOT NULL + FK + indekslar
    op.execute("""
        ALTER TABLE orders ALTER COLUMN company_id SET NOT NULL;

        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_orders_company_id') THEN
                ALTER TABLE orders ADD CONSTRAINT fk_orders_company_id 
                    FOREIGN KEY (company_id) REFERENCES companies(id);
            END IF;
        END $$;

        CREATE INDEX IF NOT EXISTS ix_orders_company_id ON orders (company_id);
        CREATE INDEX IF NOT EXISTS ix_orders_company_group ON orders (company_id, order_group_id);
    """)

    # 4. Marketplace buyurtmalari uchun asosiy filial
    op.execute("""
        ALTER TABLE companies ADD COLUMN IF NOT EXISTS marketplace_default_branch_id INTEGER NULL;

        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_companies_mp_default_branch') THEN
                ALTER TABLE companies ADD CONSTRAINT fk_companies_mp_default_branch 
                    FOREIGN KEY (marketplace_default_branch_id) REFERENCES branches(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)


def downgrade():
    op.drop_constraint('fk_companies_mp_default_branch', 'companies', type_='foreignkey')
    op.drop_column('companies', 'marketplace_default_branch_id')

    op.drop_index('ix_orders_company_group', table_name='orders')
    op.drop_index('ix_orders_company_id', table_name='orders')
    op.drop_constraint('fk_orders_company_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'company_id')
