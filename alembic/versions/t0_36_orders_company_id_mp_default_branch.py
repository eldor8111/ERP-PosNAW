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
    conn = op.get_bind()

    # 1. Ustun (avval nullable)
    op.add_column('orders', sa.Column('company_id', sa.Integer(), nullable=True))

    # 2. Backfill: mijoz korxonasi
    conn.execute(sa.text(
        "UPDATE orders SET company_id = c.company_id "
        "FROM customers c WHERE c.id = orders.customer_id AND orders.company_id IS NULL"
    ))

    # 3. Tekshiruv: customer_id NOT NULL bo'lgani uchun 0 bo'lishi kerak
    missing = conn.execute(sa.text("SELECT count(*) FROM orders WHERE company_id IS NULL")).scalar() or 0
    if missing > 0:
        raise RuntimeError(
            f"t0_36: {missing} ta buyurtmada company_id to'ldirilmadi (mijozi korxonasiz). "
            "Avval customers.company_id ni to'ldiring, so'ng migratsiyani qayta ishga tushiring."
        )

    # 4. Diagnostika: filiali boshqa korxonaga tegishli buyurtmalar (tuzatilmaydi)
    mismatched = conn.execute(sa.text(
        "SELECT count(*) FROM orders o JOIN branches b ON b.id = o.branch_id "
        "WHERE b.company_id <> o.company_id"
    )).scalar() or 0
    print(f"[t0_36] Diagnostika: filiali boshqa korxonaga tegishli buyurtmalar soni = {mismatched} "
          "(avtomatik tuzatilmaydi, T0.7/T0.25 da qo'lda ko'rib chiqiladi)")

    # 5. NOT NULL + FK + indekslar
    op.alter_column('orders', 'company_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key('fk_orders_company_id', 'orders', 'companies', ['company_id'], ['id'])
    op.create_index('ix_orders_company_id', 'orders', ['company_id'])
    # UNIQUE emas: bir guruhda (bir checkout) bir nechta qator bor
    op.create_index('ix_orders_company_group', 'orders', ['company_id', 'order_group_id'])

    # 6. Marketplace buyurtmalari uchun asosiy filial
    op.add_column('companies', sa.Column('marketplace_default_branch_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_companies_mp_default_branch', 'companies', 'branches',
        ['marketplace_default_branch_id'], ['id'], ondelete='SET NULL',
    )


def downgrade():
    op.drop_constraint('fk_companies_mp_default_branch', 'companies', type_='foreignkey')
    op.drop_column('companies', 'marketplace_default_branch_id')

    op.drop_index('ix_orders_company_group', table_name='orders')
    op.drop_index('ix_orders_company_id', table_name='orders')
    op.drop_constraint('fk_orders_company_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'company_id')
