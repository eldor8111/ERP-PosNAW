"""T4.3 — filial narxlari, aksiya filiallari, sotuv qatorida aksiya, korxonada avto-aksiya

- branch_product_prices: filial bo'yicha chakana/ulgurji narx (korxona narxini ustidan yozadi)
- promotion_branches: aksiya filiallari (bo'sh = hamma filial; mavjud aksiyalar o'zgarishsiz qoladi)
- sale_items.promotion_id / promotion_discount: sotuv qatorida qo'llangan aksiya
- companies.promotions_auto_apply: serverda aksiyani avtomatik qo'llash (sukut o'chiq)

Revision ID: t4_3
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 't4_3'
down_revision: Union[str, None] = 't4_2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Filial narxlari
    op.execute("""
        CREATE TABLE IF NOT EXISTS branch_product_prices (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            branch_id INTEGER NOT NULL REFERENCES branches(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            variant_id INTEGER REFERENCES product_variants(id),
            sale_price NUMERIC(16,4),
            wholesale_price NUMERIC(16,4),
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT ck_branch_price_any CHECK (sale_price IS NOT NULL OR wholesale_price IS NOT NULL),
            CONSTRAINT ck_branch_price_sale_nonneg CHECK (sale_price IS NULL OR sale_price >= 0),
            CONSTRAINT ck_branch_price_wholesale_nonneg CHECK (wholesale_price IS NULL OR wholesale_price >= 0)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_branch_product_prices_id ON branch_product_prices(id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_branch_product_prices_company_id ON branch_product_prices(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_branch_product_prices_branch_id ON branch_product_prices(branch_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_branch_product_prices_product_id ON branch_product_prices(product_id)")
    # variant_id NULL bo'lgani uchun oddiy UNIQUE yetmaydi (stock_levels dagi uq_stock_product_variant_warehouse kabi)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_branch_product_price "
        "ON branch_product_prices (branch_id, product_id, COALESCE(variant_id, 0))"
    )

    # 2. Aksiya filiallari (mavjud aksiyalarda yozuv yo'q = hamma filialda amal qiladi)
    op.execute("""
        CREATE TABLE IF NOT EXISTS promotion_branches (
            promotion_id INTEGER NOT NULL REFERENCES promotions(id) ON DELETE CASCADE,
            branch_id INTEGER NOT NULL REFERENCES branches(id),
            PRIMARY KEY (promotion_id, branch_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_promotion_branches_branch ON promotion_branches(branch_id)")

    # 3. Sotuv qatorida aksiya
    op.execute(
        "ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS promotion_id INTEGER "
        "REFERENCES promotions(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS promotion_discount NUMERIC(16,4)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_items_promotion ON sale_items(promotion_id)")

    # 4. Korxona: aksiyani serverda avtomatik qo'llash (sukut o'chiq)
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS promotions_auto_apply BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS promotions_auto_apply")
    op.execute("DROP INDEX IF EXISTS ix_sale_items_promotion")
    op.execute("ALTER TABLE sale_items DROP COLUMN IF EXISTS promotion_discount")
    op.execute("ALTER TABLE sale_items DROP COLUMN IF EXISTS promotion_id")
    op.execute("DROP TABLE IF EXISTS promotion_branches")
    op.execute("DROP INDEX IF EXISTS uq_branch_product_price")
    op.execute("DROP TABLE IF EXISTS branch_product_prices")
