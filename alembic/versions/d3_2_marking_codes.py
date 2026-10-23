"""Markirovka kodlari: marking_codes jadvali (D3.2)

Additiv: faqat yangi jadval; mavjud ma'lumotga tegilmaydi. Oddiy do'konlarda jadval bo'sh qoladi.

Revision ID: d3_2
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd3_2'
down_revision: Union[str, Sequence[str], None] = 'd2_5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS marking_codes (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            code VARCHAR(300) NOT NULL,
            gtin VARCHAR(14),
            serial VARCHAR(100),
            lot_number VARCHAR(100),
            expiry_date DATE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL,
            warehouse_id INTEGER REFERENCES warehouses(id),
            status VARCHAR(20) NOT NULL DEFAULT 'in_stock',
            sale_item_id INTEGER REFERENCES sale_items(id) ON DELETE SET NULL,
            received_po_id INTEGER REFERENCES purchase_orders(id) ON DELETE SET NULL,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_marking_codes_company_code UNIQUE (company_id, code)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_marking_codes_id ON marking_codes (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_marking_codes_company_id ON marking_codes (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_marking_codes_product_id ON marking_codes (product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_marking_codes_sale_item_id ON marking_codes (sale_item_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_marking_codes_company_status ON marking_codes (company_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS marking_codes")
