"""Sotuv qoldig'i va partiyalari bilan ishlash — yagona yordamchilar (T0.30).

Sotuv yaratish, tahrirlash, tasdiqlash (pending -> completed) va teskari qilish
(o'chirish, completed -> pending/cancelled) BIR XIL mantiqdan foydalanadi:

- qoldiq aynan chiqqan ombor va variant qatoriga qaytadi (StockMovement.warehouse_id,
  u bo'lmasa (eski yozuvlar) mos SaleItem.warehouse_id, oxirida Sale.warehouse_id);
- faqat nisbiy `+= quantity` (absolyut `qty_before` yozilmaydi — oradagi boshqa
  sotuvlar yo'qolmasin);
- partiyalar (FIFO) va SaleItemBatch har yo'lda bir xil kamaytiriladi/qaytariladi.

QULF TARTIBI (customer_service bilan bir xil): mijoz -> ombor qoldig'i -> hamyon.
"""
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.inventory import StockLevel, StockMovement
from app.models.sale import Sale, SaleItem, SaleItemBatch, SaleStatus


def _stock_row(db: Session, product_id: int, warehouse_id: Optional[int], variant_id: Optional[int]) -> StockLevel:
    """Aniq (mahsulot, ombor, variant) qatorini qulf bilan oladi; yo'q bo'lsa yaratadi.

    `get_or_create_stock` dan farqi: `warehouse_id=None` bo'lsa ixtiyoriy ombor emas,
    aynan omborsiz (NULL) qator olinadi — qoldiq boshqa omborga tushib qolmasin.
    """
    q = db.query(StockLevel).filter(StockLevel.product_id == product_id)
    q = q.filter(StockLevel.warehouse_id == warehouse_id) if warehouse_id is not None else q.filter(StockLevel.warehouse_id.is_(None))
    q = q.filter(StockLevel.variant_id == variant_id) if variant_id is not None else q.filter(StockLevel.variant_id.is_(None))
    stock = q.with_for_update().first()
    if not stock:
        stock = StockLevel(product_id=product_id, warehouse_id=warehouse_id, variant_id=variant_id, quantity=Decimal("0"))
        db.add(stock)
        db.flush()
    return stock


def _movement_warehouse(db: Session, sale: Sale, movement: StockMovement, items: List[SaleItem]) -> Optional[int]:
    """Harakat qaysi ombordan chiqqanini aniqlaydi.

    Tartib: `movement.warehouse_id` -> mos `SaleItem.warehouse_id` (shu mahsulot va
    variant; virtual mahsulotda manba mahsulot bo'yicha) -> `sale.warehouse_id`.
    """
    if movement.warehouse_id is not None:
        return movement.warehouse_id
    for item in items:
        if item.product_id == movement.product_id and (item.variant_id or None) == (movement.variant_id or None):
            return item.warehouse_id if item.warehouse_id is not None else sale.warehouse_id
    # Virtual (sell) mahsulot: harakat manba mahsulotga yozilgan
    from app.utils.product_conversion import deduct_target_for_sale
    for item in items:
        deduct_id, _q, conv, _src = deduct_target_for_sale(db, item.product_id, Decimal("1"))
        if conv is not None and deduct_id == movement.product_id:
            return item.warehouse_id if item.warehouse_id is not None else sale.warehouse_id
    return sale.warehouse_id


def restore_sale_stock(db: Session, sale: Sale) -> None:
    """Sotuvning barcha `StockMovement(reference_type="sale")` harakatlarini teskari qiladi.

    Har harakat uchun qoldiq o'z ombori va varianti qatoriga nisbiy (`+=`) qaytariladi,
    harakat yozuvi o'chiriladi (avvalgi xatti-harakat saqlanadi).
    """
    # Qatorlar bazadan (sale.items kolleksiyasi tahrirdan keyin eskirgan bo'lishi mumkin)
    items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
    movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "sale",
        StockMovement.reference_id == sale.id,
    ).order_by(StockMovement.id.asc()).all()
    for movement in movements:
        wh_id = _movement_warehouse(db, sale, movement, items)
        stock = _stock_row(db, movement.product_id, wh_id, movement.variant_id)
        stock.quantity = Decimal(str(stock.quantity or 0)) + Decimal(str(movement.quantity or 0))
        db.delete(movement)
    db.flush()


def restore_sale_batches(db: Session, sale: Sale) -> None:
    """`SaleItemBatch` bo'yicha partiyalarni qaytaradi va yozuvlarni o'chiradi."""
    item_ids = [r[0] for r in db.query(SaleItem.id).filter(SaleItem.sale_id == sale.id).all()]
    if not item_ids:
        return
    sibs = db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id.in_(item_ids)).all()
    for sib in sibs:
        batch = db.query(Batch).filter(Batch.id == sib.batch_id).with_for_update().first()
        if batch:
            batch.quantity = Decimal(str(batch.quantity or 0)) + Decimal(str(sib.quantity or 0))
        db.delete(sib)
    db.flush()


def allocate_batches_fifo(
    db: Session,
    product_id: int,
    variant_id: Optional[int],
    qty: Decimal,
    company_id: Optional[int],
    fallback_cost: Optional[Decimal] = None,
) -> Tuple[List[dict], Decimal]:
    """Partiyalardan FIFO bo'yicha `qty` ajratadi (partiya qoldig'i kamayadi).

    Qaytaradi: (`[{"batch_id", "quantity", "unit_cost"}]`, jami tannarx). Partiya yetmasa
    qolgan qism `fallback_cost` (mahsulot tannarxi) bilan hisoblanadi. Ombor bo'yicha
    cheklash yo'q (create_sale bilan bir xil; ombor cheklovi T1.6 da).
    """
    qty = Decimal(str(qty or 0))
    allocations: List[dict] = []
    total_cost = Decimal("0")
    if qty <= 0:
        return allocations, total_cost
    q = db.query(Batch).filter(
        Batch.product_id == product_id,
        Batch.quantity > 0,
        Batch.company_id == company_id,
    )
    q = q.filter(Batch.variant_id == variant_id) if variant_id is not None else q.filter(Batch.variant_id.is_(None))
    batches = q.order_by(Batch.created_at.asc(), Batch.id.asc()).with_for_update().all()

    remaining = qty
    for batch in batches:
        if remaining <= 0:
            break
        take = min(remaining, Decimal(str(batch.quantity or 0)))
        if take <= 0:
            continue
        batch.quantity = Decimal(str(batch.quantity or 0)) - take
        remaining -= take
        unit_cost = batch.purchase_price or Decimal("0")
        total_cost += take * unit_cost
        allocations.append({"batch_id": batch.id, "quantity": take, "unit_cost": unit_cost})
    if remaining > 0:
        total_cost += remaining * (fallback_cost or Decimal("0"))
    return allocations, total_cost


def deduct_sale_item(db: Session, sale: Sale, item: SaleItem, user, allow_negative: bool, reason: Optional[str] = None) -> None:
    """Bitta sotuv qatori uchun qoldiqni yechadi (variant va qator ombori bilan),
    partiyalarni FIFO kamaytiradi, `SaleItemBatch` yozadi va `item.cost_price` ni yangilaydi.

    `item` bazaga yozilgan (id bor) bo'lishi shart.
    """
    from app.services.inventory_service import deduct_stock
    from app.utils.product_conversion import deduct_target_for_sale

    qty = Decimal(str(item.quantity or 0))
    deduct_id, deduct_qty, conv, src = deduct_target_for_sale(db, item.product_id, qty)
    product = item.product
    # Virtual mahsulotda chiqim manba mahsulotdan, variantsiz (create_sale bilan bir xil)
    variant_id = None if conv else item.variant_id
    wh_id = item.warehouse_id if item.warehouse_id is not None else sale.warehouse_id

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
    allocations, total_cost = allocate_batches_fifo(
        db, deduct_id, variant_id, deduct_qty, sale.company_id, fallback_cost=fallback_cost,
    )
    for ab in allocations:
        db.add(SaleItemBatch(
            sale_item_id=item.id, batch_id=ab["batch_id"],
            quantity=ab["quantity"], unit_cost=ab["unit_cost"],
        ))
    if qty > 0:
        item.cost_price = total_cost / qty
    db.flush()


def is_return_linked(db: Session, sale: Sale) -> bool:
    """Sotuv qaytarish bilan bog'liqmi: qaytarish hujjati (`R...`, `original_sale_id`),
    `refunded`/`partial_refund` holati yoki biror qatori qisman qaytarilgan.
    Bunday sotuvni o'chirish/to'liq tahrirlash qoldiq va pulni ikki marta hisoblaydi."""
    if getattr(sale, "original_sale_id", None):
        return True
    if (sale.number or "").startswith("R"):
        return True
    if sale.status in (SaleStatus.refunded, SaleStatus.partial_refund):
        return True
    returned = db.query(SaleItem.id).filter(
        SaleItem.sale_id == sale.id,
        SaleItem.returned_quantity > 0,
    ).first()
    return returned is not None


# ─── D2.4: quti, blister va dona bitta kartochkada ───────────────────────────
# Qoldiq doim asosiy (eng kichik) birlikda. `unit_id` berilgan sotuv qatori shu yerda asosiy birlikka
# o'tkaziladi (miqdor * nisbat, narx / nisbat); quti ochilishi qoidalari — `allocate_unit_batches`.
# Faqat dorixona moduli yoqilgan korxonada ishlaydi; oddiy do'konda `unit_id` rad etiladi (jim e'tiborsiz emas).

def _udec(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def _ufmt(v) -> str:
    d = _udec(v)
    return format(d.normalize(), "f") if d != 0 else "0"


def list_product_units(db: Session, product_id: int, company_id: int) -> list:
    """Mahsulot birliklari (katta nisbatdan kichigiga: quti, blister, dona)."""
    from app.models.product_units import ProductUnit
    return (
        db.query(ProductUnit)
        .filter(ProductUnit.product_id == product_id, ProductUnit.company_id == company_id)
        .order_by(ProductUnit.ratio.desc(), ProductUnit.sort_order.asc(), ProductUnit.id.asc())
        .all()
    )


def pack_ratio_of(db: Session, product_id: int, company_id: int, units: Optional[list] = None) -> Optional[Decimal]:
    """Quti nisbati: `ProductPharma.pack_qty` (bo'lsa) yoki birliklar ichida eng kattasi. Hech biri yo'q -> None."""
    from app.models.product_pharma import ProductPharma
    pack = (
        db.query(ProductPharma.pack_qty)
        .filter(ProductPharma.product_id == product_id, ProductPharma.company_id == company_id)
        .scalar()
    )
    if pack and int(pack) > 0:
        return Decimal(int(pack))
    if units is None:
        units = list_product_units(db, product_id, company_id)
    ratios = [_udec(u.ratio) for u in units if _udec(u.ratio) > 0]
    return max(ratios) if ratios else None


def pack_unit_name(units: list, pack_ratio: Optional[Decimal]) -> str:
    """Quti birligi nomi (nisbati quti nisbatiga teng birlik); topilmasa 'quti'."""
    if pack_ratio is not None:
        for u in units:
            if _udec(u.ratio) == pack_ratio:
                return u.name
    return "quti"


def _round_up(price: Decimal, step) -> Decimal:
    from decimal import ROUND_CEILING
    step = _udec(step)
    if step <= 0:
        return price
    return (price / step).to_integral_value(rounding=ROUND_CEILING) * step


def unit_list_price(unit, units: list, product_price, pack_ratio: Optional[Decimal], price_round) -> Decimal:
    """Bir birlikning ro'yxat narxi: `unit.sale_price`; yo'q bo'lsa quti narxidan (nisbat bo'yicha, `price_round`
    qadamiga yuqoriga yaxlitlab); quti narxi ham yo'q bo'lsa `product.sale_price * ratio`."""
    if unit.sale_price is not None:
        return _udec(unit.sale_price)
    ratio = _udec(unit.ratio)
    if pack_ratio is not None and ratio < pack_ratio:
        box = next((u for u in units if _udec(u.ratio) == pack_ratio and u.sale_price is not None), None)
        if box is not None:
            return _round_up(_udec(box.sale_price) * ratio / pack_ratio, price_round)
    return _udec(product_price) * ratio


def resolve_sale_unit(db: Session, company_id: int, product, item_data, pharmacy_ctx) -> dict:
    """`unit_id` li sotuv qatorini asosiy birlikka o'tkazadi (yozmaydi).

    Qaytaradi: unit, unit_qty, ratio, base_qty, pack_ratio, whole_boxes (butun quti sotuvi), unit_list_price (bir
    birlik ro'yxat narxi), price_item (narx hisoblash uchun asosiy birlikdagi qator nusxasi: miqdor — asosiy
    birlikda, qo'lda narx — bir donaga bo'lingan) va price_overridden (kassir narxni qo'lda bergan).
    """
    from types import SimpleNamespace
    from fastapi import HTTPException

    enabled, settings = pharmacy_ctx
    if not enabled:
        raise HTTPException(status_code=400, detail="Qadoq birliklari (quti, blister) faqat dorixona rejimida ishlaydi")
    if getattr(product, "product_type", "stock") in ("sell", "parent", "service"):
        raise HTTPException(status_code=400, detail=f"'{product.name}' uchun qadoq birligini tanlab bo'lmaydi")
    units = list_product_units(db, product.id, company_id)
    unit = next((u for u in units if u.id == item_data.unit_id), None)
    if unit is None:
        raise HTTPException(status_code=404, detail="Birlik topilmadi")
    ratio = _udec(unit.ratio)
    unit_qty = _udec(item_data.quantity)
    base_qty = unit_qty * ratio
    pack = pack_ratio_of(db, product.id, company_id, units)
    whole = bool(pack and ratio >= pack and base_qty % pack == 0)
    list_price = unit_list_price(unit, units, product.sale_price, pack, settings.get("price_round") or 0)

    fields = item_data.model_dump() if hasattr(item_data, "model_dump") else dict(vars(item_data))
    client_price = getattr(item_data, "unit_price", None)
    manual = getattr(item_data, "price_manual", None)
    overridden = False
    price_for_base = None
    if client_price is not None and manual is not False:
        if manual is True or _udec(client_price) != list_price:
            price_for_base = _udec(client_price) / ratio   # kassir bergan narx — bir birlik narxi
            overridden = True
    fields.update(quantity=base_qty, unit_price=price_for_base)
    return {
        "unit": unit, "unit_qty": unit_qty, "ratio": ratio, "base_qty": base_qty, "pack_ratio": pack,
        "whole_boxes": whole, "unit_list_price": list_price, "price_overridden": overridden,
        "price_item": SimpleNamespace(**fields),
    }


def allocate_unit_batches(
    db: Session, *, company_id: int, product, variant_id: Optional[int], warehouse_id: Optional[int], quantity,
    pack_ratio: Optional[Decimal], whole_boxes: bool, today=None, expiry_block_days: int = 0,
    lock: bool = True, deduct: bool = True,
) -> Tuple[List[dict], Decimal]:
    """Dorixona: qadoq birligidan sotuvda partiya tanlash (FEFO; muddati o'tgan / yaroqsiz partiya olinmaydi).

    - Dona/blister (`whole_boxes=False`): avval ochilgan qutisi bor partiyalar (qoldiq % quti_ratio != 0), ular
      ichida FEFO; yetmasa — qolgan partiyalar FEFO bo'yicha (yangi quti ochiladi).
    - Butun quti (`whole_boxes=True`): har partiyadan faqat butun qutilar (floor(qoldiq / quti) * quti), FEFO;
      ochilgan quti qoldig'idan "yig'ma quti" tuzilmaydi. Yetmasa 400 (butun quti va ochilgan dona soni bilan).
    Qaytaradi: (`[{"batch", "batch_id", "quantity", "unit_cost"}]`, shortfall). Dona sotuvida shortfall > 0 ni
    chaqiruvchi rad etadi (`allocate_batches` bilan bir xil).
    """
    from fastapi import HTTPException
    from app.services.batch_allocator import _candidate_query, _naive, _MAX_DT

    qty = _udec(quantity)
    allocations: List[dict] = []
    if qty <= 0:
        return allocations, Decimal("0")
    q = _candidate_query(db, company_id, product.id, variant_id, warehouse_id, True, today, expiry_block_days)
    q = q.order_by(Batch.id.asc())
    if lock:
        q = q.populate_existing().with_for_update()
    cands = q.all()

    def _tier(b) -> int:
        if warehouse_id is None:
            return 0
        return 0 if b.warehouse_id == warehouse_id else 1

    cands.sort(key=lambda b: (_tier(b), b.expiry_date is None, _naive(b.expiry_date) or _MAX_DT, b.id))
    pack = pack_ratio if (pack_ratio and pack_ratio > 0) else None

    def _take(batch, take):
        if deduct:
            batch.quantity = _udec(batch.quantity) - take
        allocations.append({"batch": batch, "batch_id": batch.id, "quantity": take,
                            "unit_cost": batch.purchase_price or Decimal("0")})

    remaining = qty
    if whole_boxes and pack:
        avail = {}
        for b in cands:
            avail[b.id] = (_udec(b.quantity) // pack) * pack
        for b in cands:
            if remaining <= 0:
                break
            take = min(remaining, avail[b.id])
            if take > 0:
                _take(b, take)
                remaining -= take
        if remaining > 0:
            full = sum(avail.values(), Decimal("0")) / pack
            loose = sum((_udec(b.quantity) - avail[b.id] for b in cands), Decimal("0"))
            raise HTTPException(
                status_code=400,
                detail=f"{product.name}: butun quti {_ufmt(full)} ta, ochilgan qutida {_ufmt(loose)} dona bor",
            )
        return allocations, remaining

    if pack:
        ordered = [b for b in cands if _udec(b.quantity) % pack != 0] + [b for b in cands if _udec(b.quantity) % pack == 0]
    else:
        ordered = cands
    for b in ordered:
        if remaining <= 0:
            break
        take = min(remaining, _udec(b.quantity))
        if take > 0:
            _take(b, take)
            remaining -= take
    return allocations, remaining


def loose_units_by_product(db: Session, company_id: int, packs: dict, warehouse_ids) -> dict:
    """{product_id: ochilgan qutilardagi dona} — `packs` = {product_id: quti_ratio}; faqat faol, qoldig'i bor partiyalar."""
    ids = [pid for pid, p in packs.items() if p]
    wh = list(warehouse_ids or [])
    out = {pid: Decimal("0") for pid in ids}
    if not ids or not wh:
        return out
    rows = db.query(Batch.product_id, Batch.quantity).filter(
        Batch.product_id.in_(ids), Batch.company_id == company_id, Batch.warehouse_id.in_(wh),
        Batch.quantity > 0, or_(Batch.status.is_(None), Batch.status == "active"),
    ).all()
    for pid, qty in rows:
        out[pid] += _udec(qty) % packs[pid]
    return out


def stock_display_of(total, loose, pack_ratio: Optional[Decimal], pack_name: str, base_name: str) -> dict:
    """Qoldiqni qadoq bo'yicha ko'rsatish: {"stock_display": "2 quti 5 dona", "full_boxes", "loose_units"}.
    Quti nisbati noma'lum bo'lsa (birlik ham, pack_qty ham yo'q) — maydonlar None."""
    if not pack_ratio:
        return {"stock_display": None, "full_boxes": None, "loose_units": None}
    total = _udec(total)
    loose = min(max(_udec(loose), Decimal("0")), max(total, Decimal("0")))
    full = (max(total, Decimal("0")) - loose) // pack_ratio
    parts = []
    if full > 0:
        parts.append(f"{_ufmt(full)} {pack_name}")
    if loose > 0:
        parts.append(f"{_ufmt(loose)} {base_name or 'dona'}")
    return {
        "stock_display": " ".join(parts) if parts else f"0 {base_name or 'dona'}",
        "full_boxes": int(full), "loose_units": float(loose),
    }
