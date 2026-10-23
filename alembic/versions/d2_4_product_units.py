"""Quti, blister va dona bitta kartochkada: product_units, sale_item_units (D2.4)

Additiv: faqat yangi jadvallar; mavjud ma'lumotga tegilmaydi. Oddiy do'konlarda jadvallar bo'sh qoladi.
Qoldiq asosiy birlikda saqlanadi; `product_units.ratio` — asosiy birlikda nechta.

Revision ID: d2_4
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd2_4'
down_revision: Union[str, Sequence[str], None] = 'd2_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS product_units (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            name VARCHAR(50) NOT NULL,
            ratio NUMERIC(14, 3) NOT NULL,
            sale_price NUMERIC(16, 4),
            barcode VARCHAR(100),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP,
            CONSTRAINT uq_product_units_company_barcode UNIQUE (company_id, barcode),
            CONSTRAINT uq_product_units_product_name UNIQUE (product_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_units_id ON product_units (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_units_product_id ON product_units (product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_units_company_id ON product_units (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_units_company_barcode ON product_units (company_id, barcode)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS sale_item_units (
            id SERIAL PRIMARY KEY,
            sale_item_id INTEGER NOT NULL UNIQUE REFERENCES sale_items(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            unit_id INTEGER REFERENCES product_units(id) ON DELETE SET NULL,
            unit_name VARCHAR(50) NOT NULL,
            unit_ratio NUMERIC(14, 3) NOT NULL,
            unit_qty NUMERIC(14, 3) NOT NULL,
            unit_price NUMERIC(16, 4),
            created_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_item_units_id ON sale_item_units (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_item_units_company_id ON sale_item_units (company_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sale_item_units")
    op.execute("DROP TABLE IF EXISTS product_units")
