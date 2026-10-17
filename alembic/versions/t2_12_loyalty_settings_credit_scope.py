"""T2.12: sodiqlik sozlamalari, filial qoidalari, sales.loyalty_base, companies.credit_limit_scope,
karta raqamlarini normallashtirish.

Revision ID: t2_12
Revises:
Create Date: 2026-10-16

ESLATMA: `customers.cashback_percent` CHECK (0..100) t0_26 migratsiyasida (ck_customers_cashback_0_100)
allaqachon qo'yilgan; bu yerda faqat himoya sifatida qiymatlar qirqiladi (idempotent).
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = 't2_12'
down_revision = 't2_10'
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Korxona sodiqlik sozlamalari (qator bo'lmasa kod sukut qiymatlarni qaytaradi)
    op.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_settings (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL UNIQUE REFERENCES companies(id),
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            points_percent NUMERIC(5,2) NOT NULL DEFAULT 1.00,
            point_value NUMERIC(14,2) NOT NULL DEFAULT 1,
            default_cashback_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
            max_redeem_percent NUMERIC(5,2) NOT NULL DEFAULT 100,
            accrue_on_unpaid BOOLEAN NOT NULL DEFAULT true,
            return_reverses_loyalty BOOLEAN NOT NULL DEFAULT true,
            tier_bronze INTEGER NOT NULL DEFAULT 1000,
            tier_silver INTEGER NOT NULL DEFAULT 5000,
            tier_gold INTEGER NOT NULL DEFAULT 10000,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            CONSTRAINT ck_loyalty_settings_percents CHECK (
                points_percent BETWEEN 0 AND 100 AND default_cashback_percent BETWEEN 0 AND 100
                AND max_redeem_percent BETWEEN 0 AND 100),
            CONSTRAINT ck_loyalty_settings_point_value CHECK (point_value > 0),
            CONSTRAINT ck_loyalty_settings_tiers CHECK (tier_bronze < tier_silver AND tier_silver < tier_gold)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyalty_settings_id ON loyalty_settings (id)")

    # 2. Filial qoidalari
    op.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_branch_rules (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            branch_id INTEGER NOT NULL REFERENCES branches(id),
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            cashback_percent_override NUMERIC(5,2) NULL,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            CONSTRAINT uq_loyalty_branch_rule UNIQUE (company_id, branch_id),
            CONSTRAINT ck_loyalty_branch_rules_cashback CHECK (
                cashback_percent_override IS NULL OR cashback_percent_override BETWEEN 0 AND 100)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyalty_branch_rules_company_id ON loyalty_branch_rules (company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_loyalty_branch_rules_id ON loyalty_branch_rules (id)")

    # 3. sales.loyalty_base + orqaga to'ldirish (boshqa sotuvlarda NULL: kodda COALESCE(loyalty_base, total_amount))
    op.execute("ALTER TABLE sales ADD COLUMN IF NOT EXISTS loyalty_base NUMERIC(20,4) NULL")
    r = conn.execute(sa.text(
        "UPDATE sales SET loyalty_base = total_amount "
        "WHERE loyalty_base IS NULL AND customer_id IS NOT NULL "
        "AND (cashback_earned > 0 OR loyalty_points_earned > 0)"
    ))
    log.info(f"[t2_12] sales.loyalty_base to'ldirildi: {r.rowcount} ta sotuv")

    # 4. companies.credit_limit_scope (hozirgi xatti-harakat saqlanadi: faqat distribyutor)
    op.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS credit_limit_scope VARCHAR(20) NOT NULL DEFAULT 'distributor'"
    )
    op.execute("ALTER TABLE companies DROP CONSTRAINT IF EXISTS ck_companies_credit_limit_scope")
    op.execute(
        "ALTER TABLE companies ADD CONSTRAINT ck_companies_credit_limit_scope "
        "CHECK (credit_limit_scope IN ('distributor','all'))"
    )

    # 5. customers.cashback_percent: himoya qirqish (CHECK t0_26 da bor)
    r = conn.execute(sa.text("UPDATE customers SET cashback_percent = 100 WHERE cashback_percent > 100"))
    print(f"[t2_12] cashback_percent 100 ga tushirildi: {r.rowcount} ta mijoz")
    r = conn.execute(sa.text("UPDATE customers SET cashback_percent = 0 WHERE cashback_percent < 0"))
    print(f"[t2_12] cashback_percent 0 ga tushirildi: {r.rowcount} ta mijoz")

    # 6. customers.card_number normalizatsiyasi (faqat raqamlar). uq_company_customer_card_number buzilmasligi
    # uchun avval (company_id, normallashgan raqam) bo'yicha dublikatlar: eng kichik id qoladi, qolganlariga NULL.
    r = conn.execute(sa.text("""
        UPDATE customers SET card_number = NULL
        WHERE id IN (
            SELECT id FROM (
                SELECT id, regexp_replace(card_number, '\\D', '', 'g') AS n,
                       row_number() OVER (
                           PARTITION BY company_id, regexp_replace(card_number, '\\D', '', 'g') ORDER BY id
                       ) AS rn
                FROM customers WHERE card_number IS NOT NULL
            ) t
            WHERE t.rn > 1 OR t.n = ''
        )
    """))
    print(f"[t2_12] karta dublikatlari/bo'sh kartalar NULL qilindi: {r.rowcount} ta mijoz")
    r = conn.execute(sa.text(
        "UPDATE customers SET card_number = regexp_replace(card_number, '\\D', '', 'g') WHERE card_number ~ '\\D'"
    ))
    print(f"[t2_12] karta raqami normallashtirildi: {r.rowcount} ta mijoz")


def downgrade() -> None:
    # Karta normalizatsiyasi va cashback_percent qirqilishi QAYTARILMAYDI (ma'lumot yo'qolgan).
    op.execute("ALTER TABLE companies DROP CONSTRAINT IF EXISTS ck_companies_credit_limit_scope")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS credit_limit_scope")
    op.execute("ALTER TABLE sales DROP COLUMN IF EXISTS loyalty_base")
    op.execute("DROP TABLE IF EXISTS loyalty_branch_rules")
    op.execute("DROP TABLE IF EXISTS loyalty_settings")
