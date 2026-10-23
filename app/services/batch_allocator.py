"""Partiyalarni (Batch) ombor bo'yicha ajratish — sotuv, tahrir va chiqim uchun yagona qoida (T1.6).

Tartib (har bir (mahsulot, variant, ombor) uchun):
  1) `Batch.warehouse_id == warehouse_id` (shu ombor partiyalari);
  2) `Batch.warehouse_id IS NULL` (omborsiz eski partiyalar);
  3) boshqa omborlar partiyalari OLINMAYDI — yetmagan qism `shortfall` bo'ladi
     (chaqiruvchi uni `product.cost_price` bilan hisoblaydi).
Har bosqich ichida: oddiy tovarda FIFO (`created_at, id`); `is_perishable` kategoriyada
muddati o'tganlar chiqariladi va FEFO (`expiry_date ASC NULLS LAST, id`).

DORIXONA REJIMI (D1.2): modul yoqilgan korxonada (service turidan tashqari) HAMMA mahsulot
perishable sifatida: FEFO tartibi, muddati o'tgan va muddatiga `expiry_block_days` yoki kam
qolgan partiyalar chetlatiladi; muddati NULL partiya yaroqli (FEFO oxirida). Yaroqli partiya
yetmasa sotuv `assert_pharmacy_sellable` bilan yozuvlardan OLDIN 400 bilan rad etiladi
(`allow_negative` / `pos_allow_negative_stock` buni chetlab o'tmaydi). Modul o'chiq korxonada
hech narsa o'zgarmaydi.

PARTIYA HOLATI (D3.3): `Batch.status` NULL/'active' — faol; 'quarantine' | 'defect' | 'recalled' partiyalar
sotuvga ajratilmaydi (`batch_active_filter`: `allocate_batches`, `lock_batches`, `pharmacy_valid_split`).
Oddiy do'konda status doim NULL — natija o'zgarmaydi.

QULF TARTIBI (deadlock bo'lmasligi uchun barqaror): avval `StockLevel` qatorlari
(`lock_stock_rows`: ORDER BY StockLevel.id), so'ng partiyalar (ORDER BY Batch.id).
Qulf faqat kerakli (mahsulot, variant, ombor) kalitlariga qo'yiladi — boshqa omborlarda
shu mahsulotni sotayotgan kassirlar bir-birini kutmaydi.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

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
        .filter(Batch.company_id == company_id, Batch.quantity > 0, batch_active_filter(), or_(*conds))
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
    mahsulot perishable deb olinadi va muddatiga `expiry_block_days` yoki kam qolgan partiyalar ham chetlatiladi.

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


def _fmt_qty(v) -> str:
    d = _dec(v)
    return format(d.normalize(), "f") if d != 0 else "0"


def pharmacy_valid_split(
    db: Session, *, company_id, product_id, variant_id, warehouse_id,
    expiry_block_days: int = 0, today: Optional[date] = None, credit: Optional[Dict[int, Decimal]] = None,
) -> Tuple[Decimal, Decimal]:
    """(yaroqli qoldiq, yaroqsiz qoldiq) — shu ombor va omborsiz partiyalar bo'yicha.

    Yaroqli: muddati NULL yoki `expiry_cutoff` dan keyin. `credit` — {batch_id: miqdor}:
    tahrirda eski sotuv qaytarilgach partiyalarga qaytadigan miqdor (hali qaytarilmagan).
    """
    credit = credit or {}
    q = db.query(Batch).filter(
        Batch.product_id == product_id,
        Batch.company_id == company_id,
    )
    q = q.filter(Batch.variant_id == variant_id) if variant_id is not None else q.filter(Batch.variant_id.is_(None))
    if warehouse_id is not None:
        q = q.filter(or_(Batch.warehouse_id == warehouse_id, Batch.warehouse_id.is_(None)))
    if credit:
        q = q.filter(or_(Batch.quantity > 0, Batch.id.in_(list(credit.keys()))))
    else:
        q = q.filter(Batch.quantity > 0)
    cutoff = expiry_cutoff(today, expiry_block_days)
    valid = invalid = _ZERO
    for b in q.all():
        have = _dec(b.quantity) + _dec(credit.get(b.id, 0))
        if have <= 0:
            continue
        exp = _naive(b.expiry_date)
        if b.status not in (None, "active"):
            invalid += have  # D3.3: karantin / brak / qaytarib olingan partiya sotilmaydi
        elif exp is None or exp >= cutoff:
            valid += have
        else:
            invalid += have
    return valid, invalid


def assert_pharmacy_sellable(
    db: Session, *, company_id: int, lines: Iterable[tuple], pharmacy_ctx: Tuple[bool, dict],
    today: Optional[date] = None, credit: Optional[Dict[int, Decimal]] = None,
) -> None:
    """Dorixona rejimi: har (mahsulot, variant, ombor) bo'yicha jami miqdor yaroqli partiyalar
    yig'indisidan oshsa 400 (yozuvlardan OLDIN chaqiring). Modul o'chiq bo'lsa hech narsa qilmaydi.

    `lines`: `(stock_product, variant_id, warehouse_id, quantity)` — virtual mahsulotda manba mahsulot va
    ko'paytirilgan miqdor. `pharmacy_ctx` — `pharmacy_context(db, company_id)` natijasi (bir marta olingan).
    """
    enabled, settings = pharmacy_ctx
    if not enabled:
        return
    need: Dict[tuple, list] = {}
    for product, variant_id, warehouse_id, qty in lines:
        if product is None or not pharmacy_applies(True, product):
            continue
        q = _dec(qty)
        if q <= 0:
            continue
        key = (product.id, int(variant_id) if variant_id else None, warehouse_id)
        if key in need:
            need[key][1] += q
        else:
            need[key] = [product, q]
    block_days = int((settings or {}).get("expiry_block_days") or 0)
    for (pid, vid, wid), (product, q) in need.items():
        valid, invalid = pharmacy_valid_split(
            db, company_id=company_id, product_id=pid, variant_id=vid, warehouse_id=wid,
            expiry_block_days=block_days, today=today, credit=credit,
        )
        if q > valid:
            raise HTTPException(
                status_code=400,
                detail=f"{product.name}: yaroqli qoldiq {_fmt_qty(valid)}, muddati o'tgan yoki yaroqsiz {_fmt_qty(invalid)}",
            )


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
    ph_days = int(pharmacy_ctx[1].get("expiry_block_days") or 0) if ph_on else 0

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
        today=tashkent_today(), pharmacy=ph_on, expiry_block_days=ph_days,
    )
    if ph_on and shortfall > 0:
        # Oldindan tekshiruvdan keyin ham muddati o'tgan dori sotilib ketmasin (parallel o'zgarish)
        raise HTTPException(
            status_code=400,
            detail=f"{stock_product.name}: yaroqli qoldiq {_fmt_qty(deduct_qty - shortfall)}, "
                   f"yetmaydigan miqdor {_fmt_qty(shortfall)} (muddati o'tgan yoki yaroqsiz)",
        )
    add_sale_item_batches(db, item.id, allocations)
    if qty > 0:
        item.cost_price = allocation_cost(allocations, shortfall, fallback_cost) / qty
    db.flush()
