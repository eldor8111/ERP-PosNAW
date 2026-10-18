"""T3.7: label_templates — yorliq (shtrix-kod) shablonlari serverda (korxona + ixtiyoriy filial)

Revision ID: t3_7
Revises:
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = 't3_7'
down_revision = 't2_12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS label_templates (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            branch_id INTEGER REFERENCES branches(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL DEFAULT 'product',
            name VARCHAR(100) NOT NULL,
            config JSON NOT NULL,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS ix_label_templates_id ON label_templates (id);
        CREATE INDEX IF NOT EXISTS ix_label_templates_company_kind ON label_templates (company_id, kind);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_label_templates_scope 
            ON label_templates (company_id, kind, name, COALESCE(branch_id, 0));
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_label_templates_scope")
    op.execute("DROP INDEX IF EXISTS ix_label_templates_company_kind")
    op.execute("DROP INDEX IF EXISTS ix_label_templates_id")
    op.drop_table('label_templates')
