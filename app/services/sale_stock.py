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
