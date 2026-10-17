"""T3.9: tariflar modul bayroqlari va agent/kuryer limitlarini mavjud korxonalar holatiga moslash

e1f2a3b4c5d6 migratsiyasi tariflarga max_couriers/max_agents DEFAULT 0 va has_distribution/
has_manufacturing DEFAULT FALSE yozgan edi; check_courier_limit / check_agent_limit /
check_production_limit aynan shu qiymatlarda 403 beradi. Shu sabab modulni yoqib ishlayotgan
korxonalar bloklanib qolishi mumkin.

Faqat MA'LUMOT migratsiyasi (yangi ustun yo'q), hammasi idempotent:
1) korxonasi distribution_enabled=TRUE bo'lgan tarifda has_distribution=TRUE;
2) korxonasi manufacturing_enabled=TRUE bo'lgan tarifda has_manufacturing=TRUE;
3) has_distribution=TRUE tariflarda max_couriers / max_agents = 0 bo'lsa NULL (cheksiz).

Ogohlantirish: 1-2 qadam shu tarifdagi HAMMA korxonalarga modulni ochadi (bitta korxona yoqqan
bo'lsa ham). Deploydan keyin super admin tariflarni SuperAdmin sahifasida qo'lda tekshirsin.

Revision ID: t3_9
Revises:
"""
from alembic import op

revision = 't3_9'
down_revision = 't3_8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE tariffs SET has_distribution = TRUE
        WHERE COALESCE(has_distribution, FALSE) = FALSE
          AND EXISTS (SELECT 1 FROM companies c WHERE c.tariff_id = tariffs.id AND c.distribution_enabled = TRUE)
        """
    )
    op.execute(
        """
        UPDATE tariffs SET has_manufacturing = TRUE
        WHERE COALESCE(has_manufacturing, FALSE) = FALSE
          AND EXISTS (SELECT 1 FROM companies c WHERE c.tariff_id = tariffs.id AND c.manufacturing_enabled = TRUE)
        """
    )
    # NULL = cheksiz: check_courier_limit / check_agent_limit faqat `max_* is not None` bo'lganda sanaydi
    op.execute("UPDATE tariffs SET max_couriers = NULL WHERE max_couriers = 0 AND has_distribution = TRUE")
    op.execute("UPDATE tariffs SET max_agents = NULL WHERE max_agents = 0 AND has_distribution = TRUE")


def downgrade() -> None:
    # Ma'lumotni qaytarib bo'lmaydi: qaysi tarif bayrog'i migratsiyadan oldin FALSE/0 ekani saqlanmagan.
    pass
