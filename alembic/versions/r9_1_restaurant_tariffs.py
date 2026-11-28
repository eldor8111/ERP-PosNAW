"""R9.1: restoran tariflari — tariffs.max_waiter_devices, max_kds_screens, restaurant_features.

Additiv va takroriy xavfsiz (enum turlariga tegmaydi).

Revision ID: r9_1
Revises: r8_1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'r9_1'
down_revision: Union[str, Sequence[str], None] = 'r8_1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set:
    from alembic import context
    if context.is_offline_mode():
        return set()
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c['name'] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _columns('tariffs')
    if 'max_waiter_devices' not in cols:
        op.add_column('tariffs', sa.Column('max_waiter_devices', sa.Integer(), nullable=True))
    if 'max_kds_screens' not in cols:
        op.add_column('tariffs', sa.Column('max_kds_screens', sa.Integer(), nullable=True))
    if 'restaurant_features' not in cols:
        op.add_column('tariffs', sa.Column('restaurant_features', sa.JSON(), nullable=True))
    _seed_restaurant_tariffs()


# TZ 15-bo'lim (kelishilgan boshlang'ich taklif; Super Admin'da o'zgartiriladi). Imkoniyatlar va qurilma
# limitlari belgilanmaydi (NULL = cheklovsiz) — ularni Super Admin hal qiladi. Cheksiz = 9999.
_SEED = (
    # name, description, bhm_percent, max_users, max_branches, max_warehouses, sort_order
    ("Restoran sinov", "Restoran uchun 7 kunlik bepul sinov", None, 25, 1, 2, 0),
    ("Kafe", "Kichik kafe: 1 filial, 8 xodim", 40.0, 8, 1, 2, 1),
    ("Restoran", "Restoran: 1 filial, 25 xodim", 70.0, 25, 1, 2, 2),
    ("Tarmoq", "Restoranlar tarmog'i: filial va xodim cheksiz (qo'shimcha filial narxi Super Admin'da kelishiladi)",
     95.0, 9999, 9999, 9999, 3),
)


def _seed_restaurant_tariffs() -> None:
    """Restoran tarifi umuman bo'lmasa boshlang'ich tariflar yaratiladi (takroriy ishga tushirishda qo'shilmaydi)."""
    from datetime import datetime, timezone
    from alembic import context
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    exists = bind.execute(sa.text("SELECT 1 FROM tariffs WHERE business_type = 'restaurant' LIMIT 1")).first()
    if exists:
        return
    t = sa.table(
        'tariffs',
        sa.column('name', sa.String), sa.column('description', sa.Text), sa.column('price_per_month', sa.Numeric),
        sa.column('duration_days', sa.Integer), sa.column('max_users', sa.Integer),
        sa.column('max_branches', sa.Integer), sa.column('max_warehouses', sa.Integer),
        sa.column('max_agents', sa.Integer), sa.column('max_couriers', sa.Integer),
        sa.column('min_duration_months', sa.Integer), sa.column('has_pnl_compare', sa.Boolean),
        sa.column('has_manufacturing', sa.Boolean), sa.column('has_distribution', sa.Boolean),
        sa.column('is_active', sa.Boolean), sa.column('sort_order', sa.Integer), sa.column('bhm_percent', sa.Float),
        sa.column('business_type', sa.String), sa.column('created_at', sa.DateTime), sa.column('updated_at', sa.DateTime),
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    for name, desc, pct, users, branches, whs, order in _SEED:
        rows.append({
            "name": name, "description": desc,
            # ro'yxatda ko'rinishi uchun > 0; haqiqiy narx bhm_percent bo'yicha hisoblanadi
            "price_per_month": round(440000 * pct / 100) if pct else 0,
            "duration_days": 7 if pct is None else 30, "max_users": users, "max_branches": branches,
            "max_warehouses": whs, "max_agents": 0, "max_couriers": 0, "min_duration_months": 1,
            "has_pnl_compare": False, "has_manufacturing": False, "has_distribution": False,
            "is_active": True, "sort_order": order, "bhm_percent": pct, "business_type": "restaurant",
            "created_at": now, "updated_at": now,
        })
    op.bulk_insert(t, rows)


def downgrade() -> None:
    cols = _columns('tariffs')
    for c in ('restaurant_features', 'max_kds_screens', 'max_waiter_devices'):
        if c in cols:
            op.drop_column('tariffs', c)
