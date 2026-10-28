"""Partiyalarni (Batch) ombor bo'yicha ajratish — sotuv, tahrir va chiqim uchun yagona qoida (T1.6).

Tartib (har bir (mahsulot, variant, ombor) uchun):
  1) `Batch.warehouse_id == warehouse_id` (shu ombor partiyalari);
  2) `Batch.warehouse_id IS NULL` (omborsiz eski partiyalar);
  3) boshqa omborlar partiyalari OLINMAYDI — yetmagan qism `shortfall` bo'ladi
     (chaqiruvchi uni `product.cost_price` bilan hisoblaydi).
Har bosqich ichida: oddiy tovarda FIFO (`created_at, id`); `is_perishable` kategoriyada
muddati o'tganlar chiqariladi va FEFO (`expiry_date ASC NULLS LAST, id`).

DORIXONA REJIMI (D1.2): modul yoqilgan korxonada (service turidan tashqari) HAMMA mahsulot
perishable sifatida: FEFO tartibi; muddati NULL partiya FEFO oxirida.
P.13: dorixonada sotuv CHEKLANMAYDI — avval yaroqli (muddati o'tmagan, faol) partiyalar FEFO, yetmasa
muddati o'tgan va faol bo'lmagan partiyalar (`take_rest`, FEFO), qolgani partiyasiz `shortfall`
(minus qoldiq). Sotuv rad etilmaydi; javobda ogohlantirish (`sold_invalid_warnings`). Modul o'chiq
korxonada hech narsa o'zgarmaydi.

PARTIYA HOLATI (D3.3): `Batch.status` NULL/'active' — faol; 'quarantine' | 'defect' | 'recalled' partiyalar
birinchi navbatda ajratilmaydi (`batch_active_filter`), dorixona sotuvida faqat yaroqlilari yetmaganda.
Oddiy do'konda status doim NULL — natija o'zgarmaydi.

QULF TARTIBI (deadlock bo'lmasligi uchun barqaror): avval `StockLevel` qatorlari
(`lock_stock_rows`: ORDER BY StockLevel.id), so'ng partiyalar (ORDER BY Batch.id).
Qulf faqat kerakli (mahsulot, variant, ombor) kalitlariga qo'yiladi — boshqa omborlarda
shu mahsulotni sotayotgan kassirlar bir-birini kutmaydi.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable, List, Optional, Tuple

from fastapi import HTTPException
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


def expiry_cutoff(today: Optional[date] = None, block_days: int = 0) -> datetime:
    """Shu vaqtdan oldin muddati tugaydigan partiya yaroqsiz.

    `block_days == 0` — faqat muddati o'tganlar (muddat bugun tugasa hali yaroqli);
    `block_days > 0` — muddatiga shuncha kun yoki kam qolganlar ham yaroqsiz.
    """
    today = today or tashkent_today()
    days = int(block_days or 0)
    if days > 0:
        today = today + timedelta(days=days + 1)
    return datetime.combine(today, time.min)


def pharmacy_applies(pharmacy_enabled: bool, product) -> bool:
    """Dorixona qoidalari shu mahsulotga tegishlimi: modul yoqilgan va mahsulot xizmat (service) emas."""
    return bool(pharmacy_enabled) and getattr(product, "product_type", "stock") != "service"


def batch_active_filter():
    """D3.3: faqat faol partiya (status NULL yoki 'active'). Oddiy do'konda status doim NULL — natija o'zgarmaydi."""
    return or_(Batch.status.is_(None), Batch.status == "active")


def _candidate_query(db: Session, company_id, product_id, variant_id, warehouse_id, perishable, today,
                     expiry_block_days: int = 0):
    q = db.query(Batch).filter(
        Batch.product_id == product_id,
        Batch.quantity > 0,
        Batch.company_id == company_id,
        batch_active_filter(),
    )
    q = q.filter(Batch.variant_id == variant_id) if variant_id is not None else q.filter(Batch.variant_id.is_(None))
    if warehouse_id is not None:
        q = q.filter(or_(Batch.warehouse_id == warehouse_id, Batch.warehouse_id.is_(None)))
    if perishable:
        q = q.filter(or_(Batch.expiry_date.is_(None), Batch.expiry_date >= expiry_cutoff(today, expiry_block_days)))
    return q


def lock_batches(db: Session, company_id: int, keys: Iterable[Tuple[int, Optional[int], int]]) -> List[Batch]:
    """Berilgan `(product_id, variant_id, warehouse_id)` kalitlari uchun partiyalarni
    (shu ombor + omborsiz, P.13: faol bo'lmaganlari ham) `ORDER BY Batch.id` tartibida `FOR UPDATE` qiladi."""
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
    pharmacy: bool = False,
    expiry_block_days: int = 0,
) -> Tuple[List[dict], Decimal]:
    """`quantity` ni partiyalardan ajratadi.

    `pharmacy=True` (D1.2; chaqiruvchi `pharmacy_applies` bilan sotuv uchun bir marta aniqlaydi) —
    mahsulot perishable deb olinadi (FEFO); P.13: yaroqlilari yetmasa qolgan partiyalardan (`take_rest`).

    Qaytaradi: (`[{"batch", "batch_id", "quantity", "unit_cost"}]`, shortfall).
    `deduct=True` bo'lsa partiya qoldig'i kamayadi; `False` — faqat hisoblaydi (tekshiruv uchun).
    `lock=True` — nomzod partiyalar `ORDER BY Batch.id FOR UPDATE` bilan olinadi (yangilanib).
    `warehouse_id=None` — ombor cheklovi yo'q (eski chaqiruvlar uchun; sotuvda hech qachon None emas).
    """
    qty = _dec(quantity)
    allocations: List[dict] = []
    if qty <= 0:
        return allocations, _ZERO

    perishable = perishable or pharmacy
    q = _candidate_query(
        db, company_id, product_id, variant_id, warehouse_id, perishable, today,
        expiry_block_days if pharmacy else 0,
    ).order_by(Batch.id.asc())
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
    if pharmacy and remaining > 0:
        remaining = take_rest(
            db, company_id=company_id, product_id=product_id, variant_id=variant_id, warehouse_id=warehouse_id,
            remaining=remaining, allocations=allocations, exclude_ids={a["batch_id"] for a in allocations},
            deduct=deduct, lock=lock,
        )
    return allocations, remaining


def take_rest(db: Session, *, company_id, product_id, variant_id, warehouse_id, remaining, allocations: List[dict],
              exclude_ids=(), deduct: bool = True, lock: bool = True) -> Decimal:
    """P.13: dorixona sotuvi — yaroqli partiyalar yetmaganda qolgan partiyalar (muddati o'tgan, karantin / brak /
    qaytarib olingan): shu ombor avval, so'ng omborsiz; FEFO. Ajratilganlar `allocations` ga `invalid: True` bilan
    qo'shiladi. `exclude_ids` — oldingi bosqichda to'liq olingan partiyalar. Qaytaradi: qolgan (partiyasiz) miqdor."""
    remaining = _dec(remaining)
    if remaining <= 0:
        return remaining
    q = db.query(Batch).filter(
        Batch.product_id == product_id, Batch.quantity > 0, Batch.company_id == company_id,
    )
    q = q.filter(Batch.variant_id == variant_id) if variant_id is not None else q.filter(Batch.variant_id.is_(None))
    if warehouse_id is not None:
        q = q.filter(or_(Batch.warehouse_id == warehouse_id, Batch.warehouse_id.is_(None)))
    if exclude_ids:
        q = q.filter(~Batch.id.in_(list(exclude_ids)))
    q = q.order_by(Batch.id.asc())
    if lock:
        q = q.populate_existing().with_for_update()
    rest = q.all()
    rest.sort(key=lambda b: (0 if warehouse_id is None or b.warehouse_id == warehouse_id else 1,
                             b.expiry_date is None, _naive(b.expiry_date) or _MAX_DT, b.id))
    for batch in rest:
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
            "batch": batch, "batch_id": batch.id, "quantity": take,
            "unit_cost": batch.purchase_price or _ZERO, "invalid": True,
        })
    return remaining


def sold_invalid_warnings(product, allocations: List[dict]) -> List[dict]:
    """P.13: sotuv javobidagi ogohlantirish (sotuv to'xtamaydi) — muddati o'tgan yoki yaroqsiz partiyadan sotildi."""
    bad = sum((_dec(a["quantity"]) for a in allocations if a.get("invalid")), _ZERO)
    if bad <= 0:
        return []
    return [{
        "code": "sold_invalid_batch", "product_id": getattr(product, "id", None),
        "message": f"'{getattr(product, 'name', '')}': {_fmt_qty(bad)} muddati o'tgan yoki yaroqsiz partiyadan sotildi",
    }]


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


def _fmt_qty(v) -> str:
    d = _dec(v)
    return format(d.normalize(), "f") if d != 0 else "0"


def add_sale_item_batches(db: Session, sale_item_id: int, allocations: List[dict]) -> None:
    """Ajratish natijasidan `SaleItemBatch` qatorlarini yozadi."""
    for a in allocations:
        db.add(SaleItemBatch(
            sale_item_id=sale_item_id, batch_id=a["batch_id"],
            quantity=a["quantity"], unit_cost=a["unit_cost"],
        ))


# ─── Sotuv qatori (tahrir / tasdiqlash) ──────────────────────────────────────

def deduct_sale_item(db: Session, sale, item, user, allow_negative: bool, reason: Optional[str] = None,
                     pharmacy_ctx: Optional[Tuple[bool, dict]] = None) -> None:
    """Bitta sotuv qatori uchun qoldiqni yechadi (variant va qator ombori bilan), partiyalarni
    OMBOR bo'yicha (`allocate_batches`) kamaytiradi, `SaleItemBatch` yozadi va `item.cost_price`
    ni yangilaydi. `create_sale` bilan bir xil qoida (T1.6).

    `item` bazaga yozilgan (id bor) bo'lishi shart.
    `pharmacy_ctx` — sotuv uchun bir marta olingan `pharmacy_context` (berilmasa shu yerda olinadi, D1.2).
    """
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

    if pharmacy_ctx is None:
        from app.services.pharmacy import pharmacy_context
        pharmacy_ctx = pharmacy_context(db, sale.company_id)
    ph_on = pharmacy_applies(pharmacy_ctx[0], stock_product)

    deduct_stock(
        db=db, product_id=deduct_id, quantity=deduct_qty,
        user_id=user.id, reason=text,
        reference_type="sale", reference_id=sale.id,
        warehouse_id=wh_id, allow_negative=allow_negative or is_service or ph_on,   # P.13: dorixonada cheklov yo'q
        variant_id=variant_id,
    )

    fallback_cost = (src.cost_price if (conv and src) else (product.cost_price if product else None))
    allocations, shortfall = allocate_batches(
        db, company_id=sale.company_id, product_id=deduct_id, variant_id=variant_id,
        warehouse_id=wh_id, quantity=deduct_qty, perishable=is_perishable_product(stock_product),
        today=tashkent_today(), pharmacy=ph_on,
    )
    add_sale_item_batches(db, item.id, allocations)
    if qty > 0:
        item.cost_price = allocation_cost(allocations, shortfall, fallback_cost) / qty
    db.flush()
