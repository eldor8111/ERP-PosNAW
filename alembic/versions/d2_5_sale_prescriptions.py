"""Retseptli dori sotuvi: sale_prescriptions (D2.5)

Additiv: faqat yangi jadval; mavjud ma'lumotga tegilmaydi. Oddiy do'konlarda jadval bo'sh qoladi.

Revision ID: d2_5
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd2_5'
down_revision: Union[str, Sequence[str], None] = 'd2_4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sale_prescriptions (
            id SERIAL PRIMARY KEY,
            sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
            sale_item_id INTEGER REFERENCES sale_items(id) ON DELETE SET NULL,
            product_id INTEGER REFERENCES products(id),
            company_id INTEGER NOT NULL REFERENCES companies(id),
            number VARCHAR(100),
            issued_at DATE,
            doctor VARCHAR(200),
            clinic VARCHAR(200),
            patient VARCHAR(200),
            blank_type VARCHAR(20),
            reason_without_rx VARCHAR(500),
            created_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_prescriptions_id ON sale_prescriptions (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_prescriptions_sale_id ON sale_prescriptions (sale_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_prescriptions_company_id ON sale_prescriptions (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sale_prescriptions_sale_item_id ON sale_prescriptions (sale_item_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sale_prescriptions")
