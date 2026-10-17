"""Sotiladigan omborlar doirasi va qoldiq yig'indisi (T1.17).

POS, agent katalogi, do'kon katalogi, Telegram "Do'kon" va sotuvdagi default ombor bir xil
qoidadan foydalanadi:
  - ombor korxonaniki va faol (`is_active`) bo'lishi shart;
  - xom ashyo, WIP va tranzit omborlari sotiladigan qoldiqqa kirmaydi (`NON_SELLABLE_TYPES`);
  - filial berilsa — faqat shu filial(lar) omborlari, boshqa filialga jimgina o'tilmaydi;
  - qoldiq yig'indisida `warehouse_id IS NULL` qatorlar hisoblanmaydi (omborga inner join).
"""
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import StockLevel
from app.models.warehouse import Warehouse, WarehouseType

# `returns` ombori hozircha sotiladigan qoldiqqa kiradi (mavjud xulq saqlanadi).
# Qaytarilgan tovar chiqarilsin desak, shu yerga `WarehouseType.returns` qo'shiladi.
NON_SELLABLE_TYPES = (WarehouseType.raw_material, WarehouseType.wip, WarehouseType.transit)

# Default ombor tanlashda tur ustuvorligi: shop > main > boshqalari
_TYPE_RANK = {WarehouseType.shop: 0, WarehouseType.main: 1}


def sellable_warehouses_query(
    db: Session,
    company_id: Optional[int],
    branch_id: Optional[int] = None,
    branch_ids: Optional[Iterable[int]] = None,
):
    """Sotiladigan (faol, xom ashyosiz) omborlar so'rovi.

    `branch_id` berilsa faqat shu filial; `branch_ids` berilsa (bo'sh bo'lsa ham) shu filiallar
    to'plami (bo'sh to'plam — hech narsa). Ikkalasi ham `None` bo'lsa — butun korxona
    (filialsiz omborlar ham).
    """
    q = db.query(Warehouse).filter(
        Warehouse.company_id == company_id,
        Warehouse.is_active == True,  # noqa: E712
        Warehouse.type.notin_(NON_SELLABLE_TYPES),
    )
    if branch_id is not None:
        q = q.filter(Warehouse.branch_id == branch_id)
    elif branch_ids is not None:
        ids = list(branch_ids)
        q = q.filter(Warehouse.branch_id.in_(ids)) if ids else q.filter(Warehouse.id == None)  # noqa: E711
    return q


def sellable_warehouse_ids(
    db: Session,
    company_id: Optional[int],
    branch_id: Optional[int] = None,
    branch_ids: Optional[Iterable[int]] = None,
) -> List[int]:
    """Sotiladigan omborlar id'lari (id bo'yicha tartiblangan)."""
    rows = sellable_warehouses_query(db, company_id, branch_id, branch_ids).order_by(Warehouse.id).all()
    return [w.id for w in rows]


def default_sale_warehouse_id(db: Session, company_id: Optional[int], branch_id: Optional[int]) -> Optional[int]:
    """Filialning default sotuv ombori: `shop` > `main` > boshqa sotiladigan tur; bir xil turda
    avval `is_default` (T1.4), keyin eng kichik id. Deterministik. Filialda sotiladigan ombor
    bo'lmasa `None` (boshqa filialga o'tmaydi). `branch_id=None` — butun korxona bo'yicha."""
    rows = sellable_warehouses_query(db, company_id, branch_id).order_by(Warehouse.id).all()
    if not rows:
        return None
    best = min(rows, key=lambda w: (_TYPE_RANK.get(w.type, 2), 0 if w.is_default else 1, w.id))
    return best.id


def stock_totals(db: Session, product_ids: Iterable[int], wh_ids: Iterable[int]) -> Dict[int, Decimal]:
    """Mahsulot bo'yicha qoldiq yig'indisi, faqat berilgan omborlar bo'yicha.
    `StockLevel` `Warehouse` bilan inner join qilinadi, shuning uchun `warehouse_id IS NULL`
    qatorlar tushmaydi. Omborlar yoki mahsulotlar bo'sh bo'lsa — bo'sh lug'at."""
    pids = list(product_ids)
    whs = list(wh_ids)
    if not pids or not whs:
        return {}
    rows = (
        db.query(StockLevel.product_id, func.coalesce(func.sum(StockLevel.quantity), 0))
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .filter(StockLevel.product_id.in_(pids), StockLevel.warehouse_id.in_(whs))
        .group_by(StockLevel.product_id)
        .all()
    )
    return {pid: Decimal(str(total or 0)) for pid, total in rows}
