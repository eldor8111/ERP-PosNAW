"""T4.2: filial rekvizitlari (kod, yuridik nom, STIR, soliq rejimi, ish vaqti, chek shabloni)

Faqat additiv: yangi ustunlar NULL, mavjud ma'lumot o'zgarmaydi. Fiskal modullar reyestri T3.18 da
(`fiscal_devices`, `sales.fiscal_factory_id`) yaratilgan, bu yerda takrorlanmaydi.

Revision ID: t4_2
Revises:
Create Date: 2026-10-17
"""
from alembic import op
import sqlalchemy as sa

revision = 't4_2'
down_revision = 't4_1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('branches', sa.Column('code', sa.String(20), nullable=True))
    op.add_column('branches', sa.Column('legal_name', sa.String(200), nullable=True))
    op.add_column('branches', sa.Column('stir', sa.String(14), nullable=True))
    op.add_column('branches', sa.Column('tax_regime', sa.String(20), nullable=True))
    op.add_column('branches', sa.Column('working_hours', sa.JSON(), nullable=True))
    op.add_column('branches', sa.Column('receipt_templates', sa.JSON(), nullable=True))
    # Kod korxona ichida noyob (katta-kichik harfsiz); kodsiz filiallar cheklanmaydi
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_branches_company_code "
        "ON branches (company_id, lower(code)) WHERE code IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_branches_company_code")
    for col in ('receipt_templates', 'working_hours', 'tax_regime', 'stir', 'legal_name', 'code'):
        op.drop_column('branches', col)
