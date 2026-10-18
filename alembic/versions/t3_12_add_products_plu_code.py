"""T3.12 — products.plu_code: tarozi PLU kodi (korxona ichida unikal, 1..99999)

Ko'chirish: birligi kg/g bo'lgan faol mahsulotlar (company_id, id tartibida) aylanib chiqiladi.
Nomzod = SKU raqamlarining oxirgi 5 tasi (eski TMA eksporti bilan bir xil), shunda bosilgan
yorliqlar bekor bo'lmaydi. Nomzod 0 bo'lsa yoki korxonada band bo'lsa (masalan 'SKU-A1B2C3' va
'SKU-1A2B3C' ikkalasi 123 ga tushadi) eng kichik bo'sh raqam beriladi. O'zgargan mahsulotlar
migratsiya logiga chiqariladi — ularni tarozilarga qayta yuklash kerak.

Revision ID: t3_12
Revises: (zanjir bosqich oxirida ulanadi)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 't3_12'
down_revision: Union[str, None] = 't3_9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLU_MAX = 99999


def _legacy_candidate(sku) -> int:
    """Eski TMA qoidasi: SKU raqamlarining oxirgi 5 tasi (raqam yo'q bo'lsa 0)."""
    digits = ''.join(ch for ch in str(sku or '') if ch.isdigit())[-5:]
    return int(digits) if digits else 0


def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS plu_code INTEGER")

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, company_id, sku, plu_code FROM products "
        "WHERE unit IN ('kg','g') AND is_deleted = false "
        "ORDER BY company_id, id"
    )).fetchall()

    # Korxona bo'yicha band PLU lar (qayta ishga tushirishda mavjud qiymatlar saqlanadi)
    taken: dict = {}
    for r in rows:
        if r.plu_code:
            taken.setdefault(r.company_id, set()).add(r.plu_code)

    changed = []
    for r in rows:
        if r.plu_code:
            continue
        used = taken.setdefault(r.company_id, set())
        cand = _legacy_candidate(r.sku)
        kept = 1 <= cand <= PLU_MAX and cand not in used
        if not kept:
            cand = 1
            while cand in used and cand <= PLU_MAX:
                cand += 1
            if cand > PLU_MAX:
                print(f"[t3_12] OGOHLANTIRISH: korxona {r.company_id} da bo'sh PLU qolmadi (mahsulot {r.id})")
                continue
        used.add(cand)
        bind.execute(sa.text("UPDATE products SET plu_code = :c WHERE id = :i"), {"c": cand, "i": r.id})
        if not kept:
            changed.append((r.company_id, r.id, r.sku, cand))

    if changed:
        print(f"[t3_12] {len(changed)} ta mahsulot PLU si eski qoidadan farq qiladi — tarozilarga qayta yuklang:")
        for company_id, pid, sku, new in changed:
            print(f"[t3_12]   korxona={company_id} mahsulot={pid} sku={sku!r} -> PLU {new}")

    op.execute("ALTER TABLE products DROP CONSTRAINT IF EXISTS ck_products_plu_range")
    op.execute("ALTER TABLE products ADD CONSTRAINT ck_products_plu_range "
               "CHECK (plu_code IS NULL OR plu_code BETWEEN 1 AND 99999) NOT VALID")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_products_plu_active ON products (company_id, plu_code) "
               "WHERE is_deleted = false AND plu_code IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_products_plu_active")
    op.execute("ALTER TABLE products DROP CONSTRAINT IF EXISTS ck_products_plu_range")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS plu_code")
