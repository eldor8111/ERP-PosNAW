"""Partiyalarni (Batch) ombor bo'yicha ajratish — sotuv, tahrir va chiqim uchun yagona qoida (T1.6).

Tartib (har bir (mahsulot, variant, ombor) uchun):
  1) `Batch.warehouse_id == warehouse_id` (shu ombor partiyalari);
  2) `Batch.warehouse_id IS NULL` (omborsiz eski partiyalar);
  3) boshqa omborlar partiyalari OLINMAYDI — yetmagan qism `shortfall` bo'ladi
     (chaqiruvchi uni `product.cost_price` bilan hisoblaydi).
Har bosqich ichida: oddiy tovarda FIFO (`created_at, id`); `is_perishable` kategoriyada
muddati o'tganlar chiqariladi va FEFO (`expiry_date ASC NULLS LAST, id`).

QULF TARTIBI (deadlock bo'lmasligi uchun barqaror): avval `StockLevel` qatorlari
(`lock_stock_rows`: ORDER BY StockLevel.id), so'ng partiyalar (ORDER BY Batch.id).
Qulf faqat kerakli (mahsulot, variant, ombor) kalitlariga qo'yiladi — boshqa omborlarda
shu mahsulotni sotayotgan kassirlar bir-birini kutmaydi.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import and_, func, or_, tuple_
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.inventory import StockLevel
from app.models.sale import SaleItemBatch

_ZERO = Decimal("0")
_MIN_DT = datetime(1970, 1, 1)
_MAX_DT = datetime(9999, 12, 31)


def tashkent_today() -> date:
    """Toshkent sanasi (UTC+5) — muddati o'tganlikni aniqlash uchun (scheduler.py kabi)."""
    return (datetime.now(timezone.utc) + timedelta(hours=5)).date()


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    """tz-aware va tz-naive vaqtlarni solishtirib bo'lishi uchun tz ni olib tashlaydi."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) is not None else dt


def _dec(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


# ─── Qulflar ─────────────────────────────────────────────────────────────────

def lock_stock_rows(db: Session, keys: Iterable[Tuple[int, Optional[int], int]]) -> dict:
    """`(product_id, variant_id, warehouse_id)` kalitlari bo'yicha `StockLevel` qatorlarini
    `ORDER BY StockLevel.id` tartibida `FOR UPDATE` qiladi.

    Qaytaradi: `{(product_id, variant_id|None, warehouse_id): StockLevel}` (topilmaganlar yo'q).
    Bir kalitga bir nechta qator tushsa — eng kichik id li olinadi.
    """
    uniq = sorted({(int(p), (int(v) if v else None), int(w)) for p, v, w in keys},
                  key=lambda k: (k[0], k[1] or 0, k[2]))
    if not uniq:
        return {}
    pairs = [(p, v or 0, w) for p, v, w in uniq]
    rows = (
        db.query(StockLevel)
        .filter(tuple_(StockLevel.product_id, func.coalesce(StockLevel.variant_id, 0), StockLevel.warehouse_id).in_(pairs))
        .order_by(StockLevel.id.asc())
        .populate_existing()
        .with_for_update()
        .all()
    )
    result: dict = {}
    for r in rows:
        result.setdefault((r.product_id, r.variant_id or None, r.warehouse_id), r)
    return result


def _candidate_query(db: Session, company_id, product_id, variant_id, warehouse_id, perishable, today):
    q = db.query(Batch).filter(
        Batch.product_id == product_id,
        Batch.quantity > 0,
        Batch.company_id == company_id,
    )
    q = q.filter(Batch.variant_id == variant_id) if variant_id is not None else q.filter(Batch.variant_id.is_(None))
    if warehouse_id is not None:
        q = q.filter(or_(Batch.warehouse_id == warehouse_id, Batch.warehouse_id.is_(None)))
    if perishable:
        today = today or tashkent_today()
        q = q.filter(or_(Batch.expiry_date.is_(None), Batch.expiry_date >= datetime.combine(today, time.min)))
    return q


def lock_batches(db: Session, company_id: int, keys: Iterable[Tuple[int, Optional[int], int]]) -> List[Batch]:
    """Berilgan `(product_id, variant_id, warehouse_id)` kalitlari uchun partiyalarni
    (shu ombor + omborsiz) `ORDER BY Batch.id` tartibida `FOR UPDATE` qiladi va yangilaydi."""
    uniq = sorted({(int(p), (int(v) if v else None), int(w)) for p, v, w in keys},
                  key=lambda k: (k[0], k[1] or 0, k[2]))
    if not uniq:
        return []
    conds = []
    for p, v, w in uniq:
        conds.append(and_(
            Batch.product_id == p,
            Batch.variant_id == v if v is not None else Batch.variant_id.is_(None),
            or_(Batch.warehouse_id == w, Batch.warehouse_id.is_(None)),
        ))
    return (
        db.query(Batch)
        .filter(Batch.company_id == company_id, Batch.quantity > 0, or_(*conds))
        .order_by(Batch.id.asc())
        .populate_existing()
        .with_for_update()
        .all()
    )


# ─── Ajratish ────────────────────────────────────────────────────────────────

def allocate_batches(
    db: Session,
    *,
    company_id: int,
    product_id: int,
    variant_id: Optional[int],
    warehouse_id: Optional[int],
    quantity,
    perishable: bool = False,
    today: Optional[date] = None,
    lock: bool = True,
    deduct: bool = True,
) -> Tuple[List[dict], Decimal]:
    """`quantity` ni partiyalardan ajratadi.

    Qaytaradi: (`[{"batch", "batch_id", "quantity", "unit_cost"}]`, shortfall).
    `deduct=True` bo'lsa partiya qoldig'i kamayadi; `False` — faqat hisoblaydi (tekshiruv uchun).
    `lock=True` — nomzod partiyalar `ORDER BY Batch.id FOR UPDATE` bilan olinadi (yangilanib).
    `warehouse_id=None` — ombor cheklovi yo'q (eski chaqiruvlar uchun; sotuvda hech qachon None emas).
    """
    qty = _dec(quantity)
    allocations: List[dict] = []
    if qty <= 0:
        return allocations, _ZERO

    q = _candidate_query(db, company_id, product_id, variant_id, warehouse_id, perishable, today).order_by(Batch.id.asc())
    if lock:
        q = q.populate_existing().with_for_update()
    candidates = q.all()

    def _tier(b: Batch) -> int:
        if warehouse_id is None:
            return 0
        return 0 if b.warehouse_id == warehouse_id else 1

    if perishable:
        candidates.sort(key=lambda b: (_tier(b), b.expiry_date is None, _naive(b.expiry_date) or _MAX_DT, b.id))
    else:
        candidates.sort(key=lambda b: (_tier(b), _naive(b.created_at) or _MIN_DT, b.id))

    remaining = qty
    for batch in candidates:
        if remaining <= 0:
            break
        have = _dec(batch.quantity)
        take = min(remaining, have)
        if take <= 0:
            continue
        if deduct:
            batch.quantity = have - take
        remaining -= take
        allocations.append({
            "batch": batch,
            "batch_id": batch.id,
            "quantity": take,
            "unit_cost": batch.purchase_price or _ZERO,
        })
    return allocations, remaining


def apply_allocations(allocations: List[dict]) -> None:
    """`deduct=False` bilan hisoblangan ajratishni qo'llaydi (partiya qoldig'ini kamaytiradi)."""
    for a in allocations:
        b = a["batch"]
        b.quantity = _dec(b.quantity) - _dec(a["quantity"])


def allocation_cost(allocations: List[dict], shortfall, fallback_cost) -> Decimal:
    """Jami tannarx: partiyalar narxi + yetmagan qism `fallback_cost` (mahsulot tannarxi) bilan."""
    total = sum((_dec(a["quantity"]) * _dec(a["unit_cost"]) for a in allocations), _ZERO)
    return total + _dec(shortfall) * _dec(fallback_cost)


def is_perishable_product(product) -> bool:
    cat = getattr(product, "category", None) if product is not None else None
    return bool(getattr(cat, "is_perishable", False))


def add_sale_item_batches(db: Session, sale_item_id: int, allocations: List[dict]) -> None:
    """Ajratish natijasidan `SaleItemBatch` qatorlarini yozadi."""
    for a in allocations:
        db.add(SaleItemBatch(
            sale_item_id=sale_item_id, batch_id=a["batch_id"],
            quantity=a["quantity"], unit_cost=a["unit_cost"],
        ))


# ─── Sotuv qatori (tahrir / tasdiqlash) ──────────────────────────────────────

def deduct_sale_item(db: Session, sale, item, user, allow_negative: bool, reason: Optional[str] = None) -> None:
    """Bitta sotuv qatori uchun qoldiqni yechadi (variant va qator ombori bilan), partiyalarni
    OMBOR bo'yicha (`allocate_batches`) kamaytiradi, `SaleItemBatch` yozadi va `item.cost_price`
    ni yangilaydi. `create_sale` bilan bir xil qoida (T1.6).

    `item` bazaga yozilgan (id bor) bo'lishi shart.
    """
    from fastapi import HTTPException
    from app.services.inventory_service import deduct_stock
    from app.utils.product_conversion import deduct_target_for_sale

    qty = _dec(item.quantity)
    deduct_id, deduct_qty, conv, src = deduct_target_for_sale(db, item.product_id, qty)
    product = item.product
    # Virtual mahsulotda chiqim manba mahsulotdan, variantsiz (create_sale bilan bir xil)
    variant_id = None if conv else item.variant_id
    wh_id = item.warehouse_id if item.warehouse_id is not None else sale.warehouse_id
    if wh_id is None:
        raise HTTPException(status_code=400, detail="Ombor aniqlanmadi")

    text = reason or f"Sotuv #{sale.number}"
    if conv and src:
        text += f" ({product.name if product else item.product_id} → {src.name} x{conv.ratio})"
    stock_product = src if (conv and src) else product
    is_service = getattr(stock_product, "product_type", "stock") == "service"

    deduct_stock(
        db=db, product_id=deduct_id, quantity=deduct_qty,
        user_id=user.id, reason=text,
        reference_type="sale", reference_id=sale.id,
        warehouse_id=wh_id, allow_negative=allow_negative or is_service,
        variant_id=variant_id,
    )

    fallback_cost = (src.cost_price if (conv and src) else (product.cost_price if product else None))
    allocations, shortfall = allocate_batches(
        db, company_id=sale.company_id, product_id=deduct_id, variant_id=variant_id,
        warehouse_id=wh_id, quantity=deduct_qty, perishable=is_perishable_product(stock_product),
        today=tashkent_today(),
    )
    add_sale_item_batches(db, item.id, allocations)
    if qty > 0:
        item.cost_price = allocation_cost(allocations, shortfall, fallback_cost) / qty
    db.flush()
