"""Dori ma'lumotlari: product_pharma, pharma_substances, product_substances (D2.1)

Additiv: faqat yangi jadvallar; mavjud ma'lumotga tegilmaydi. Oddiy do'konlarda jadvallar bo'sh qoladi.

Revision ID: d2_1
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'd2_1'
down_revision: Union[str, Sequence[str], None] = 'd1_3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS pharma_substances (
            id SERIAL PRIMARY KEY,
            company_id INTEGER REFERENCES companies(id),
            name_uz VARCHAR(200) NOT NULL,
            name_ru VARCHAR(200),
            name_lat VARCHAR(200),
            created_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pharma_substances_company_id ON pharma_substances (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pharma_substances_name_uz ON pharma_substances (name_uz)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pharma_substances_name_ru ON pharma_substances (name_ru)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pharma_substances_name_lat ON pharma_substances (name_lat)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS product_pharma (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL UNIQUE REFERENCES products(id) ON DELETE CASCADE,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            dosage_form VARCHAR(20),
            strength VARCHAR(100),
            pack_qty INTEGER,
            manufacturer VARCHAR(200),
            country VARCHAR(100),
            reg_number VARCHAR(100),
            reg_valid_until DATE,
            atc_code VARCHAR(20),
            storage VARCHAR(20),
            is_rx BOOLEAN NOT NULL DEFAULT FALSE,
            control_class VARCHAR(20) NOT NULL DEFAULT 'none',
            max_retail_price NUMERIC(16, 4),
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_pharma_id ON product_pharma (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_pharma_company_id ON product_pharma (company_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS product_substances (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            substance_id INTEGER NOT NULL REFERENCES pharma_substances(id),
            CONSTRAINT uq_product_substances_pair UNIQUE (product_id, substance_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_substances_product_id ON product_substances (product_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_product_substances_substance_id ON product_substances (substance_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS product_substances")
    op.execute("DROP TABLE IF EXISTS product_pharma")
    op.execute("DROP TABLE IF EXISTS pharma_substances")
