"""T2.6 — Mijoz qarzi harakatlari jurnali (customer_debt_log)

CRM-06 / CRM-08 / FIN-14 / REPORT-27 / CRM-22: qarz faqat `customers.debt_balances` da turardi, harakatlar
jurnali yo'q edi. Endi har bir o'zgarish `customer_debt_log` ga yoziladi (kim, qaysi filial, nima uchun);
filial kesimidagi debitorlik va undirish hisobotlari shundan olinadi.

  * jadval `customer_debt_log` (IF NOT EXISTS — `main._create_missing_tables` oldin yaratib qo'yishi mumkin);
  * indekslar: (company_id, branch_id, customer_id), (customer_id, created_at), (sale_id), (transaction_id);
  * ko'chirish: jurnalida qatori yo'q har bir mijoz uchun `debt_balances` dagi har musbat chelakka bitta
    `kind='opening'` qator (`branch_id = customers.branch_id`, bo'sh bo'lsa NULL). Tarixiy filial bo'linishi
    taxminiy: eski to'lovlarda `Sale.paid_amount` yangilanmagan, shuning uchun filial aniqligi yangi amallardan boshlanadi.
    Takrorlanmaydi (NOT EXISTS) — qayta ishga tushirish xavfsiz.
Faqat additiv: ustun/jadval o'chirilmaydi.

Revision ID: t2_6
Revises: (bosqich oxirida ulanadi)
Create Date: 2026-10-16

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 't2_6'
down_revision = 't2_2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS customer_debt_log (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id),
            customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
            branch_id INTEGER NULL REFERENCES branches(id),
            cash_branch_id INTEGER NULL REFERENCES branches(id),
            user_id INTEGER NULL REFERENCES users(id),
            kind VARCHAR(20) NOT NULL,
            currency VARCHAR(3) NOT NULL DEFAULT 'UZS',
            delta NUMERIC(20, 4) NOT NULL,
            delta_uzs NUMERIC(20, 4) NOT NULL,
            rate NUMERIC(14, 4),
            sale_id INTEGER NULL REFERENCES sales(id) ON DELETE SET NULL,
            transaction_id INTEGER NULL REFERENCES transactions(id) ON DELETE SET NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_debt_log_id ON customer_debt_log(id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customer_debt_log_company_branch_customer "
        "ON customer_debt_log(company_id, branch_id, customer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_customer_debt_log_customer_created "
        "ON customer_debt_log(customer_id, created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_debt_log_sale ON customer_debt_log(sale_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_debt_log_transaction ON customer_debt_log(transaction_id)")

    # Ko'chirish (a): debt_balances JSON dagi har bir musbat chelak uchun bitta 'opening' qatori
    op.execute(
        """INSERT INTO customer_debt_log
               (company_id, customer_id, branch_id, kind, currency, delta, delta_uzs, rate, reason, created_at)
           SELECT c.company_id, c.id, c.branch_id, 'opening', upper(left(e.key, 3)), e.value::numeric,
                  e.value::numeric * COALESCE((SELECT cu.rate FROM currencies cu
                       WHERE upper(cu.code) = upper(e.key) AND (cu.company_id = c.company_id OR cu.company_id IS NULL)
                       ORDER BY (cu.company_id IS NULL), cu.id LIMIT 1), 1),
                  COALESCE((SELECT cu.rate FROM currencies cu
                       WHERE upper(cu.code) = upper(e.key) AND (cu.company_id = c.company_id OR cu.company_id IS NULL)
                       ORDER BY (cu.company_id IS NULL), cu.id LIMIT 1), 1),
                  'Boshlang''ich qarz (jurnal ochilganda ko''chirildi)', NOW()
           FROM customers c, json_each_text(CASE WHEN json_typeof(c.debt_balances::json) = 'object' THEN c.debt_balances::json ELSE '{}'::json END) e
           WHERE c.company_id IS NOT NULL AND c.debt_balances IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM customer_debt_log l WHERE l.customer_id = c.id)
             AND (CASE WHEN e.value ~ '^[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?$' THEN e.value::numeric ELSE 0 END) > 0.005"""
    )
    # Ko'chirish (b): debt_balances bo'sh, lekin eski debt_balance musbat bo'lsa (UZS)
    op.execute(
        """INSERT INTO customer_debt_log
               (company_id, customer_id, branch_id, kind, currency, delta, delta_uzs, rate, reason, created_at)
           SELECT c.company_id, c.id, c.branch_id, 'opening', 'UZS', c.debt_balance, c.debt_balance, 1,
                  'Boshlang''ich qarz (jurnal ochilganda ko''chirildi)', NOW()
           FROM customers c
           WHERE c.company_id IS NOT NULL AND c.debt_balance > 0.005
             AND NOT EXISTS (SELECT 1 FROM customer_debt_log l WHERE l.customer_id = c.id)"""
    )


def downgrade() -> None:
    # Jurnal o'chirilsa qarz harakatlari tarixi yo'qoladi; balanslar (customers.debt_balances) saqlanadi.
    op.execute("DROP INDEX IF EXISTS ix_customer_debt_log_transaction")
    op.execute("DROP INDEX IF EXISTS ix_customer_debt_log_sale")
    op.execute("DROP INDEX IF EXISTS ix_customer_debt_log_customer_created")
    op.execute("DROP INDEX IF EXISTS ix_customer_debt_log_company_branch_customer")
    op.execute("DROP INDEX IF EXISTS ix_customer_debt_log_id")
    op.execute("DROP TABLE IF EXISTS customer_debt_log")
