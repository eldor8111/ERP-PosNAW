from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import nulls_last
from sqlalchemy.orm import Session

from app.models.batch import Batch
from app.models.inventory import MovementType, StockMovement
from app.models.inventory import StockLevel
from app.models.product import Product, ProductConversion
from app.models.transfer import StockTransfer, StockTransferBatch, StockTransferItem, TransferStatus
from app.core.audit import log_action
from app.models.warehouse import Warehouse
from app.services.document_numbers import next_document_number
from app.services.inventory_service import _deduct_batches_fifo, get_or_create_stock
from app.services.warehouse_access import assert_warehouse_branch_access, resolve_ctx


# ─── Korxona izolyatsiyasi yordamchilari ───
# company_id=None faqat super_admin uchun: filtr o'tkazib yuboriladi.

def _company_warehouse_ids_subq(db: Session, company_id: int):
    """Korxona omborlari ID'lari — IN (SELECT ...) uchun subquery, ro'yxat materializatsiya qilinmaydi"""
    return db.query(Warehouse.id).filter(Warehouse.company_id == company_id)


def _get_company_warehouse(db: Session, wh_id: int, company_id: Optional[int]) -> Warehouse:
    """Faol omborni korxona bo'yicha tekshirib oladi, topilmasa 404"""
    q = db.query(Warehouse).filter(Warehouse.id == wh_id, Warehouse.is_active == True)
    if company_id is not None:
        q = q.filter(Warehouse.company_id == company_id)
    wh = q.first()
    if not wh:
        raise HTTPException(status_code=404, detail=f"Ombor ID={wh_id} topilmadi")
    return wh


def _get_company_product(db: Session, product_id: int, company_id: Optional[int], label: str = "Mahsulot") -> Product:
    """Mahsulotni korxona bo'yicha tekshirib oladi, topilmasa 404"""
    q = db.query(Product).filter(Product.id == product_id)
    if company_id is not None:
        q = q.filter(Product.company_id == company_id)
    prod = q.first()
    if not prod:
        raise HTTPException(status_code=404, detail=f"{label} ID={product_id} topilmadi")
    return prod


def get_company_transfer(db: Session, transfer_id: int, company_id: Optional[int]) -> StockTransfer:
    """Transferni ikkala ombori (from va to) korxonaga tegishli bo'lgan holda oladi, aks holda 404"""
    q = db.query(StockTransfer).filter(StockTransfer.id == transfer_id)
    if company_id is not None:
        wh_ids = _company_warehouse_ids_subq(db, company_id)
        q = q.filter(
            StockTransfer.from_warehouse_id.in_(wh_ids),
            StockTransfer.to_warehouse_id.in_(wh_ids),
        )
    transfer = q.first()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    return transfer


def generate_transfer_number(db: Session, company_id: int, branch_id: Optional[int] = None) -> str:
    """Transfer raqami (T1.14): `TR{YYYYMMDD}-{korxona}-{filial}-{NNNN}`, atomar hisoblagich bilan
    (hujjat o'chirilsa ham raqam qayta ishlatilmaydi)."""
    return next_document_number(db, company_id=company_id, branch_id=branch_id, doc_type="TR")


def _transfer_snapshot(transfer: StockTransfer, items: Optional[list] = None) -> dict:
    """Audit uchun transfer holati: omborlar, status va qatorlar (50 tagacha qirqiladi)."""
    if items is None:
        items = [
            {"product_id": i.product_id, "variant_id": i.variant_id,
             "target_product_id": i.target_product_id, "quantity": float(i.quantity or 0)}
            for i in (transfer.items or [])
        ]
    st = transfer.status
    return {
        "number": transfer.number,
        "from_warehouse_id": transfer.from_warehouse_id,
        "to_warehouse_id": transfer.to_warehouse_id,
        "status": st.value if hasattr(st, "value") else st,
        "items": items,
    }


def _items_snapshot(collected_items: list) -> list:
    return [
        {"product_id": r["product_id"], "variant_id": r["variant_id"],
         "target_product_id": r["target_product_id"], "quantity": float(r["quantity"])}
        for r in collected_items
    ]


def _transfer_scope(db: Session, transfer: StockTransfer) -> dict:
    """Audit kesimi: manba ombor korxonasi va filiali (super_admin amali uchun ham to'g'ri korxona)."""
    wh = db.get(Warehouse, transfer.from_warehouse_id)
    if wh is None:
        return {}
    return {"company_id": wh.company_id, "branch_id": wh.branch_id}


# ─── Qator validatsiyasi ───

def _ensure_transferable(db: Session, prod: Product) -> None:
    """Tarkibiy (sell, ProductConversion) va xizmat mahsulotlarini ko'chirib bo'lmaydi — 400.
    Virtual mahsulot qoldig'i omborda yuritilmaydi (products.py da doim 0 ko'rinadi)."""
    ptype = getattr(prod, "product_type", None) or "simple"
    has_conv = db.query(ProductConversion.id).filter(ProductConversion.sell_product_id == prod.id).first() is not None
    if ptype in ("sell", "service") or has_conv:
        raise HTTPException(
            status_code=400,
            detail=f"'{prod.name}': tarkibiy/xizmat mahsulotni ko'chirib bo'lmaydi",
        )


def _validate_items(db: Session, data, company_id: Optional[int]) -> list:
    """Mahsulot, maqsad mahsulot va variantlarni qoldiqqa tegmasdan tekshiradi.
    Qaytaradi: collected_items ro'yxati (ORM cache'ga ishonmasdan, Decimal miqdor bilan)."""
    collected = []
    for item_data in data.items:
        prod = _get_company_product(db, item_data.product_id, company_id)
        _ensure_transferable(db, prod)

        # Maqsad mahsulotni tekshirish (agar ko'rsatilgan bo'lsa)
        target_product_id = getattr(item_data, 'target_product_id', None) or None
        if target_product_id:
            target_prod = _get_company_product(db, target_product_id, company_id, label="Maqsad mahsulot")
            _ensure_transferable(db, target_prod)

        variant_id = getattr(item_data, 'variant_id', None) or None
        if variant_id is not None:
            from app.models.product_variant import ProductVariant
            variant = db.query(ProductVariant).filter(
                ProductVariant.id == variant_id, ProductVariant.product_id == item_data.product_id
            ).first()
            if not variant:
                raise HTTPException(status_code=404, detail=f"Variant ID={variant_id} topilmadi")

        quantity = Decimal(str(item_data.quantity))
        if quantity <= 0:
            raise HTTPException(status_code=400, detail=f"'{prod.name}': miqdor musbat bo'lishi kerak")

        collected.append({
            'product_id': item_data.product_id,
            'variant_id': variant_id,
            'quantity': quantity,
            'target_product_id': target_product_id,
            'prod': prod,
        })
    return collected


def _add_items(db: Session, transfer: StockTransfer, collected_items: list) -> None:
    """collected_items bo'yicha StockTransferItem qatorlarini yozadi (ref['item'] ga bog'laydi)"""
    for ref in collected_items:
        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=ref['product_id'],
            variant_id=ref['variant_id'],
            target_product_id=ref['target_product_id'],
            quantity=ref['quantity'],
        )
        db.add(item)
        ref['item'] = item
    db.flush()


# ─── Partiyalarni ko'chirish (T4.1: yuborishda ayirish, qabulda ko'zgu yaratish) ───

def _take_batches(
    db: Session,
    transfer: StockTransfer,
    item: StockTransferItem,
    company_id: Optional[int],
    qty: Decimal,
) -> None:
    """YUBORISH: manba ombordagi partiyalardan FEFO tartibida `qty` ayiradi va har biri uchun
    StockTransferBatch bog'lanishini yozadi (dest_batch_id hali NULL — tovar yo'lda).
    Partiyasi yo'q (eski, narxsiz) qoldiq qismi partiyasiz ko'chadi (xato bermaydi)."""
    q = db.query(Batch).filter(
        Batch.product_id == item.product_id,
        Batch.warehouse_id == transfer.from_warehouse_id,
        Batch.quantity > 0,
    )
    if company_id is not None:
        q = q.filter(Batch.company_id == company_id)
    if item.variant_id is not None:
        q = q.filter(Batch.variant_id == item.variant_id)
    else:
        q = q.filter(Batch.variant_id.is_(None))
    q = q.order_by(nulls_last(Batch.expiry_date.asc()), Batch.created_at.asc(), Batch.id.asc())
    batches = q.with_for_update().all()

    remaining = Decimal(qty)
    for b in batches:
        if remaining <= 0:
            break
        take = min(remaining, Decimal(b.quantity))
        b.quantity = Decimal(b.quantity) - take
        db.add(StockTransferBatch(
            transfer_id=transfer.id,
            item_id=item.id,
            product_id=item.product_id,
            source_batch_id=b.id,
            dest_batch_id=None,
            quantity=take,
        ))
        remaining -= take
    db.flush()


def _land_batches(
    db: Session,
    transfer: StockTransfer,
    item: StockTransferItem,
    dest_product_id: int,
    dest_variant_id: Optional[int],
    qty_received: Decimal,
    company_id: Optional[int],
) -> None:
    """QABUL: yuborishda ayirilgan partiyalardan `qty_received` miqdorga manzil omborda ko'zgu partiyalar
    yaratadi. Kamomad qismi (qabul qilinmagan) dest_batch_id=NULL bilan alohida bog'lanish bo'lib qoladi —
    bekor qilinsa manba partiyaga qaytadi."""
    links = (
        db.query(StockTransferBatch)
        .filter(
            StockTransferBatch.transfer_id == transfer.id,
            StockTransferBatch.item_id == item.id,
            StockTransferBatch.dest_batch_id.is_(None),
        )
        .order_by(StockTransferBatch.id.asc())
        .all()
    )
    remaining = Decimal(qty_received)
    for link in links:
        if remaining <= 0:
            break
        link_qty = Decimal(link.quantity)
        take = min(remaining, link_qty)
        src = db.get(Batch, link.source_batch_id)
        mirror = Batch(
            product_id=dest_product_id,
            variant_id=dest_variant_id,
            warehouse_id=transfer.to_warehouse_id,
            lot_number=src.lot_number,
            manufacture_date=src.manufacture_date,
            expiry_date=src.expiry_date,
            initial_quantity=take,
            quantity=take,
            purchase_price=src.purchase_price,
            company_id=src.company_id if src.company_id is not None else company_id,
        )
        db.add(mirror)
        db.flush()
        link.dest_batch_id = mirror.id
        if take < link_qty:
            # qisman qabul: kamomad qismi alohida (manzilsiz) bog'lanish
            link.quantity = take
            db.add(StockTransferBatch(
                transfer_id=transfer.id,
                item_id=item.id,
                product_id=link.product_id,
                source_batch_id=link.source_batch_id,
                dest_batch_id=None,
                quantity=link_qty - take,
            ))
        remaining -= take
    db.flush()


def _send_items(db: Session, transfer: StockTransfer, collected_items: list, user_id: int, suffix: str = "") -> None:
    """YUBORISH: faqat manba ombordan TRANSFER_OUT (warehouse_id bilan) va partiyalarni ayirish.
    Manzil qoldig'i o'zgarmaydi — tovar "yo'lda" (status=in_transit)."""
    for ref in collected_items:
        item = ref['item']
        prod = ref['prod']
        product_id = ref['product_id']
        variant_id = ref['variant_id']
        quantity = Decimal(ref['quantity'])

        from_stock = get_or_create_stock(db, product_id, transfer.from_warehouse_id, variant_id)
        qty_before_from = Decimal(from_stock.quantity or 0)
        if qty_before_from < quantity:
            raise HTTPException(
                status_code=400,
                detail=f"'{prod.name}': manba omborida yetarli qoldiq yo'q "
                       f"(mavjud: {qty_before_from:.3f}, kerak: {quantity:.3f})"
            )
        from_stock.quantity = qty_before_from - quantity
        db.add(StockMovement(
            product_id=product_id,
            variant_id=variant_id,
            warehouse_id=transfer.from_warehouse_id,
            type=MovementType.TRANSFER_OUT,
            qty_before=qty_before_from,
            qty_after=from_stock.quantity,
            quantity=quantity,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=user_id,
            reason=f"Transfer #{transfer.number} chiqim{suffix}",
        ))
        item.qty_sent = quantity
        _take_batches(db, transfer, item, prod.company_id, quantity)
    db.flush()


def _receive_items(db: Session, transfer: StockTransfer, rows: list, user_id: int, suffix: str = "") -> None:
    """QABUL: faqat manzil omborga TRANSFER_IN (warehouse_id bilan) — haqiqiy qabul qilingan miqdor.
    rows: [(StockTransferItem, qty_received, reason)]. Kamomad manzilga o'tmaydi, hujjatda qoladi."""
    for item, qty_received, reason in rows:
        qty_received = Decimal(qty_received)
        qty_sent = Decimal(item.qty_sent if item.qty_sent is not None else item.quantity)
        item.qty_received = qty_received
        item.discrepancy_reason = (reason or None) if qty_received < qty_sent else None
        if qty_received <= 0:
            continue

        # Maqsad ombor: target_product_id ko'rsatilgan bo'lsa uni, aks holda source mahsulot
        dest_product_id = item.target_product_id if item.target_product_id else item.product_id
        # Boshqa mahsulotga yo'naltirilgan bo'lsa, manba variant maqsadga tegishli emas
        dest_variant_id = None if item.target_product_id else item.variant_id
        to_stock = get_or_create_stock(db, dest_product_id, transfer.to_warehouse_id, dest_variant_id)
        qty_before_to = Decimal(to_stock.quantity or 0)
        to_stock.quantity = qty_before_to + qty_received
        db.add(StockMovement(
            product_id=dest_product_id,
            variant_id=dest_variant_id,
            warehouse_id=transfer.to_warehouse_id,
            type=MovementType.TRANSFER_IN,
            qty_before=qty_before_to,
            qty_after=to_stock.quantity,
            quantity=qty_received,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=user_id,
            reason=f"Transfer #{transfer.number} kirim{suffix}",
        ))
        # Partiyalar (yaroqlilik muddati, tannarx) manzilga ko'chadi
        _land_batches(db, transfer, item, dest_product_id, dest_variant_id, qty_received, item.product.company_id)
    db.flush()


def _apply_items(db: Session, transfer: StockTransfer, collected_items: list, user_id: int, suffix: str = "") -> None:
    """Bir bosqichli ko'chirish: yuborish + to'liq qabul bir amalda (create va update uchun umumiy)."""
    _send_items(db, transfer, collected_items, user_id, suffix)
    _receive_items(
        db, transfer, [(ref['item'], Decimal(ref['quantity']), None) for ref in collected_items], user_id, suffix,
    )


# ─── Qaytarish (bekor qilish / tahrir / o'chirish) ───

def _stock_key_filter(q, wh_id: int, product_id: int, variant_id: Optional[int]):
    q = q.filter(StockLevel.product_id == product_id, StockLevel.warehouse_id == wh_id)
    return q.filter(StockLevel.variant_id == variant_id) if variant_id is not None \
        else q.filter(StockLevel.variant_id.is_(None))


def revert_transfer_stock(
    db: Session,
    transfer_id: int,
    from_warehouse_id: int,
    to_warehouse_id: int,
    company_id: Optional[int] = None,
    user_id: Optional[int] = None,
    reason: Optional[str] = None,
):
    """Transfer harakatlarini bekor qilish va qoldiqlarni qaytarish (ikki o'tishli).
    T1.19: asl StockMovement qatorlari O'CHIRILMAYDI — teskari (storno) harakat yoziladi
    (reference_type="stock_transfer_revert"). Takroriy chaqiruvda ikki marta qaytarilmasligi uchun
    faqat hali qaytarilmagan (asl − storno) sof ta'sir hisobga olinadi.
    1-o'tish: hech narsa o'zgartirmasdan manzil omborida qoldiq yetarliligi tekshiriladi
    (tovar allaqachon sotilgan/ko'chirilgan bo'lsa 400 — baza o'zgarmaydi).
    2-o'tish: qoldiqlar o'zgaradi, storno harakatlar va partiyalar qaytariladi."""
    movements = db.query(StockMovement).filter(
        StockMovement.reference_type.in_(("stock_transfer", "stock_transfer_revert")),
        StockMovement.reference_id == transfer_id,
    ).order_by(StockMovement.id.asc()).all()

    # (warehouse_id, product_id, variant_id) → qoldiqqa HALI qo'llanib turgan sof ta'sir
    applied: dict = {}
    for m in movements:
        qty = Decimal(m.quantity or 0)
        if m.type == MovementType.TRANSFER_OUT:
            key = (m.warehouse_id or from_warehouse_id, m.product_id, m.variant_id)
            applied[key] = applied.get(key, Decimal(0)) - qty
        elif m.type == MovementType.TRANSFER_IN:
            key = (m.warehouse_id or to_warehouse_id, m.product_id, m.variant_id)
            applied[key] = applied.get(key, Decimal(0)) + qty
        elif m.type == MovementType.IN:      # storno: manbaga qaytarish
            key = (m.warehouse_id or from_warehouse_id, m.product_id, m.variant_id)
            applied[key] = applied.get(key, Decimal(0)) + qty
        elif m.type == MovementType.OUT:     # storno: manzildan chiqarish
            key = (m.warehouse_id or to_warehouse_id, m.product_id, m.variant_id)
            applied[key] = applied.get(key, Decimal(0)) - qty
    # Qaytariladigan o'zgarish = -(sof ta'sir); nol bo'lganlar tashlanadi
    deltas: dict = {k: -v for k, v in applied.items() if v != 0}

    # Qatorlarni id tartibida qulflash (deadlock oldini olish uchun barqaror tartib)
    locked: dict = {}
    if deltas:
        product_ids = {k[1] for k in deltas}
        rows = (
            db.query(StockLevel)
            .filter(
                StockLevel.warehouse_id.in_(list({k[0] for k in deltas})),
                StockLevel.product_id.in_(list(product_ids)),
            )
            .order_by(StockLevel.id.asc())
            .with_for_update()
            .all()
        )
        for s in rows:
            locked[(s.warehouse_id, s.product_id, s.variant_id)] = s

    # 1-o'tish: tekshiruv (manzil tomonida qoldiq kamayadi — yetarli bo'lishi shart)
    for key, delta in deltas.items():
        if delta >= 0:
            continue
        need = -delta
        stock = locked.get(key)
        have = Decimal(stock.quantity or 0) if stock is not None else Decimal(0)
        if stock is None or have < need:
            prod = db.query(Product).filter(Product.id == key[1]).first()
            name = prod.name if prod else f"ID={key[1]}"
            raise HTTPException(
                status_code=400,
                detail=f"'{name}': manzil omborida yetarli qoldiq yo'q "
                       f"(mavjud: {have:.3f}, kerak: {need:.3f}) — tovar allaqachon sotilgan/ko'chirilgan",
            )

    # 2-o'tish: qoldiqlarni o'zgartirish va storno harakatlarni yozish (asl harakatlar saqlanadi)
    transfer = db.get(StockTransfer, transfer_id)
    base_reason = reason or f"Transfer #{transfer.number if transfer else transfer_id} bekor qilindi (storno)"
    for key, delta in deltas.items():
        stock = locked.get(key)
        if stock is None:
            # Manba tomonida qator yo'q bo'lsa — yaratib qaytaramiz (jim o'tkazmaymiz)
            stock = get_or_create_stock(db, key[1], key[0], key[2])
        before = Decimal(stock.quantity or 0)
        stock.quantity = before + delta
        db.add(StockMovement(
            product_id=key[1],
            variant_id=key[2],
            warehouse_id=key[0],
            type=MovementType.IN if delta > 0 else MovementType.OUT,
            qty_before=before,
            qty_after=stock.quantity,
            quantity=abs(delta),
            reference_type="stock_transfer_revert",
            reference_id=transfer_id,
            user_id=user_id,
            reason=base_reason,
        ))

    # Partiyalar: ko'zgu partiyadan ayirib, manba partiyaga qaytarish
    links = db.query(StockTransferBatch).filter(
        StockTransferBatch.transfer_id == transfer_id
    ).order_by(StockTransferBatch.id.asc()).all()
    for link in links:
        qty = Decimal(link.quantity or 0)
        dest_b = (
            db.query(Batch).filter(Batch.id == link.dest_batch_id).with_for_update().first()
            if link.dest_batch_id is not None else None   # T4.1: yo'lda/kamomad qismi — ko'zgu partiya yo'q
        )
        src_b = db.query(Batch).filter(Batch.id == link.source_batch_id).with_for_update().first()
        if dest_b is not None:
            take = min(Decimal(dest_b.quantity or 0), qty)
            if take > 0:
                dest_b.quantity = Decimal(dest_b.quantity) - take
            shortfall = qty - take
            if shortfall > 0:
                # Ko'zgu partiya qisman sotilgan — qolganini manzil omboridagi boshqa partiyalardan
                comp = dest_b.company_id if dest_b.company_id is not None else company_id
                _deduct_batches_fifo(
                    db, dest_b.product_id, shortfall, dest_b.warehouse_id, comp,
                    variant_id=dest_b.variant_id, strict=False,
                )
        if src_b is not None:
            src_b.quantity = Decimal(src_b.quantity or 0) + qty
        db.delete(link)
    db.flush()


# ─── Asosiy amallar ───

_BYPASS_ROLES = ("admin", "director", "super_admin")


def _requires_two_step(from_wh: Warehouse, to_wh: Warehouse) -> bool:
    """Ikki bosqich faqat ikkala ombor ham filialga bog'langan va filiallar farq qilsa majburiy.
    Bir filial ichida yoki filialsiz korxonada eski bir bosqichli xatti-harakat saqlanadi."""
    return bool(from_wh.branch_id and to_wh.branch_id and from_wh.branch_id != to_wh.branch_id)


def _is_two_step_doc(transfer: StockTransfer) -> bool:
    """Hujjat ikki bosqichli yaratilganmi: yo'lda yoki qabul vaqti yuborish vaqtidan farq qiladi.
    (Bir bosqichli va eski hujjatlarda sent_at == confirmed_at.) Qoralama uchun False — tahrir erkin."""
    if transfer.status == TransferStatus.in_transit:
        return True
    if transfer.status == TransferStatus.received and transfer.sent_at and transfer.confirmed_at:
        return transfer.sent_at != transfer.confirmed_at
    return False


def _role_value(user) -> str:
    role = getattr(user, "role", None)
    return getattr(role, "value", role)


def _wh_in_scope(ctx, wh: Warehouse) -> bool:
    """Ombor foydalanuvchi filiali doirasidami (bypass/cheklanmagan kontekst — doim ha)."""
    if ctx is None or ctx.bypass:
        return True
    ids = ctx.scope_ids()
    return ids is None or wh.branch_id in ids


def transfer_flags(user, ctx, transfer: StockTransfer) -> dict:
    """Joriy foydalanuvchi uchun send/receive/cancel ruxsatlari (filial qoidasi) — UI va servis uchun yagona."""
    src = _wh_in_scope(ctx, transfer.from_warehouse)
    dst = _wh_in_scope(ctx, transfer.to_warehouse)
    st = transfer.status
    if st == TransferStatus.pending:
        can_cancel = src or dst or transfer.created_by == getattr(user, "id", None)
    elif st == TransferStatus.in_transit:
        can_cancel = src or dst
    elif st == TransferStatus.received:
        can_cancel = _role_value(user) in _BYPASS_ROLES
    else:
        can_cancel = False
    return {
        "can_send": st == TransferStatus.pending and src,
        "can_receive": st == TransferStatus.in_transit and dst,
        "can_cancel": bool(can_cancel),
    }


def _lock_transfer(db: Session, transfer_id: int, company_id: Optional[int]) -> StockTransfer:
    """Transferni korxona bo'yicha olib, qatorni qulflaydi va holatni bazadan yangilaydi —
    ikki parallel send/receive/cancel qoldiqni ikki marta o'zgartirmasligi uchun."""
    t = get_company_transfer(db, transfer_id, company_id)
    locked = (
        db.query(StockTransfer).filter(StockTransfer.id == t.id)
        .populate_existing().with_for_update().first()
    )
    return locked or t


def _collected_from_transfer(db: Session, transfer: StockTransfer) -> list:
    """Saqlangan transfer qatorlaridan collected_items (send uchun)"""
    collected = []
    for item in transfer.items:
        prod = db.query(Product).filter(Product.id == item.product_id).first()
        if not prod:
            raise HTTPException(status_code=404, detail=f"Mahsulot ID={item.product_id} topilmadi")
        collected.append({
            'product_id': item.product_id,
            'variant_id': item.variant_id,
            'quantity': Decimal(item.quantity),
            'target_product_id': item.target_product_id,
            'prod': prod,
            'item': item,
        })
    return collected


def _do_send(db: Session, transfer: StockTransfer, user_id: int) -> None:
    """pending → in_transit: manba ombordan yechish (holat/ruxsat tekshiruvi chaqiruvchida)"""
    collected = _collected_from_transfer(db, transfer)
    _send_items(db, transfer, collected, user_id)
    transfer.status = TransferStatus.in_transit
    transfer.sent_by = user_id
    transfer.sent_at = datetime.now(timezone.utc)
    db.flush()
    log_action(
        db, "TRANSFER_SEND", "stock_transfer", transfer.id, user_id=user_id,
        old_values={"status": "pending"},
        new_values=_transfer_snapshot(transfer, _items_snapshot(collected)),
        **_transfer_scope(db, transfer),
    )


def create_transfer(db: Session, data, user_id: int, company_id: Optional[int] = None,
                    user=None, ctx=None) -> StockTransfer:
    """Transfer yaratish. company_id — foydalanuvchi korxonasi (super_admin uchun None):
    omborlar va mahsulotlar shu korxonaga tegishli bo'lishi tekshiriladi (commitdan oldin).
    T1.3: `user` berilsa — filialga biriktirilgan non-bypass xodim uchun MANBA ombor ruxsat etilgan
    filialda bo'lishi shart (403); maqsad ombor istalgan korxona ombori bo'lishi mumkin.
    T4.1: omborlar farqli filiallarda bo'lsa (yoki `two_step=True`) — ikki bosqichli: `pending` yaratiladi,
    `send=True` bo'lsa darhol yuboriladi (in_transit, faqat manba kamayadi). Aks holda — bir bosqichli
    (darhol received)."""
    if data.from_warehouse_id == data.to_warehouse_id:
        raise HTTPException(status_code=400, detail="Manba va maqsad ombor bir xil bo'lmasligi kerak")

    from_wh = _get_company_warehouse(db, data.from_warehouse_id, company_id)
    to_wh = _get_company_warehouse(db, data.to_warehouse_id, company_id)
    if user is not None:
        assert_warehouse_branch_access(db, user, ctx, data.from_warehouse_id)
        assert_warehouse_branch_access(db, user, ctx, data.to_warehouse_id, as_transfer_target=True)

    # Mahsulot, maqsad mahsulot va variantlarni sarlavha yaratilishidan OLDIN tekshirish
    # (xato bo'lsa bazaga hech narsa yozilmaydi)
    collected_items = _validate_items(db, data, company_id)

    explicit = getattr(data, "two_step", None)
    two_step = explicit if explicit is not None else _requires_two_step(from_wh, to_wh)

    transfer = StockTransfer(
        number=generate_transfer_number(db, company_id or from_wh.company_id, from_wh.branch_id),
        from_warehouse_id=data.from_warehouse_id,
        to_warehouse_id=data.to_warehouse_id,
        note=data.note,
        created_by=user_id,
        status=TransferStatus.pending,
    )
    db.add(transfer)
    db.flush()

    _add_items(db, transfer, collected_items)

    if two_step:
        log_action(
            db, "TRANSFER_CREATE", "stock_transfer", transfer.id, user_id=user_id,
            new_values=_transfer_snapshot(transfer, _items_snapshot(collected_items)),
            **_transfer_scope(db, transfer),
        )
        if getattr(data, "send", True):
            _do_send(db, transfer, user_id)
        return transfer

    # ── Bir bosqichli: qoldiq va partiyalar darhol ko'chadi (yuborish + to'liq qabul) ──
    _apply_items(db, transfer, collected_items, user_id)

    now = datetime.now(timezone.utc)
    transfer.status = TransferStatus.received
    transfer.sent_by = user_id
    transfer.sent_at = now
    transfer.confirmed_by = user_id
    transfer.confirmed_at = now
    db.flush()
    log_action(
        db, "TRANSFER_CREATE", "stock_transfer", transfer.id, user_id=user_id,
        new_values=_transfer_snapshot(transfer, _items_snapshot(collected_items)),
        **_transfer_scope(db, transfer),
    )
    return transfer


def create_draft_transfer(db: Session, user, ctx, from_warehouse_id: int, to_warehouse_id: int,
                          items: list) -> StockTransfer:
    """T4.4: to'ldirish tavsiyasidan transfer QORALAMASI: `items=[(product_id, qty)]`. Doim ikki bosqichli
    (`two_step=True`, `send=False`) — `pending` holatda, ikkala ombor qoldig'iga TEGMAYDI; yuborish keyin
    `send_transfer` orqali. Korxona (404) va manba ombor filial ruxsati (403) `create_transfer` da tekshiriladi."""
    from app.schemas.transfer import TransferCreate, TransferItemCreate
    try:
        data = TransferCreate(
            from_warehouse_id=from_warehouse_id, to_warehouse_id=to_warehouse_id,
            note="Qoldiqni to'ldirish tavsiyasi (min/max)", two_step=True, send=False,
            items=[TransferItemCreate(product_id=pid, quantity=qty) for pid, qty in items],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Transfer qatorlari noto'g'ri: {e}")
    company_id = None if _role_value(user) == "super_admin" else user.company_id
    return create_transfer(db, data, user.id, company_id, user=user, ctx=ctx)


def send_transfer(db: Session, transfer_id: int, user, ctx=None) -> StockTransfer:
    """T4.1: pending → in_transit. Faqat manba ombor filialidagi xodim (yoki admin/director) yubora oladi (403).
    Holat mos emas — 409, qoldiq yetmasa — 400. Manba ombor kamayadi, manzil o'zgarmaydi."""
    company_id = None if _role_value(user) == "super_admin" else user.company_id
    transfer = _lock_transfer(db, transfer_id, company_id)
    if transfer.status != TransferStatus.pending:
        raise HTTPException(status_code=409, detail=f"Transfer holati '{transfer.status.value}' — yuborib bo'lmaydi")
    assert_warehouse_branch_access(db, user, ctx, transfer.from_warehouse_id)
    _do_send(db, transfer, user.id)
    return transfer


def receive_transfer(db: Session, transfer_id: int, payload, user, ctx=None) -> StockTransfer:
    """T4.1: in_transit → received. Faqat manzil ombor filialidagi xodim (yoki admin/director) qabul qila oladi (403).
    payload.items — [{item_id, qty_received, reason}]; ro'yxatda yo'q qatorlar to'liq qabul qilingan hisoblanadi.
    qty_received > qty_sent yoki kamomadda sabab yo'q — 400. Kamomad manzilga o'tmaydi, hujjatda qoladi."""
    company_id = None if _role_value(user) == "super_admin" else user.company_id
    transfer = _lock_transfer(db, transfer_id, company_id)
    if transfer.status != TransferStatus.in_transit:
        raise HTTPException(status_code=409, detail=f"Transfer holati '{transfer.status.value}' — qabul qilib bo'lmaydi")
    assert_warehouse_branch_access(db, user, ctx, transfer.to_warehouse_id)

    items_by_id = {i.id: i for i in transfer.items}
    given = {}
    for r in (getattr(payload, "items", None) or []):
        if r.item_id not in items_by_id:
            raise HTTPException(status_code=400, detail=f"Qator ID={r.item_id} bu transferga tegishli emas")
        if r.item_id in given:
            raise HTTPException(status_code=400, detail=f"Qator ID={r.item_id} takrorlangan")
        given[r.item_id] = r

    # Hamma tekshiruv qoldiqqa tegishdan OLDIN
    rows = []
    for item in transfer.items:
        sent = Decimal(item.qty_sent if item.qty_sent is not None else item.quantity)
        r = given.get(item.id)
        qty = Decimal(str(r.qty_received)) if r is not None else sent
        reason = (r.reason or "").strip() if r is not None else ""
        name = item.product.name if item.product else f"ID={item.product_id}"
        if qty < 0:
            raise HTTPException(status_code=400, detail=f"'{name}': miqdor manfiy bo'lmasligi kerak")
        if qty > sent:
            raise HTTPException(
                status_code=400,
                detail=f"'{name}': qabul qilingan miqdor yuborilganidan ({sent:.3f}) oshmasligi kerak",
            )
        if qty < sent and not reason:
            raise HTTPException(status_code=400, detail=f"'{name}': kamomad sababini kiriting")
        rows.append((item, qty, reason or None))

    _receive_items(db, transfer, rows, user.id)

    transfer.status = TransferStatus.received
    transfer.confirmed_by = user.id
    transfer.confirmed_at = datetime.now(timezone.utc)
    note = (getattr(payload, "note", None) or "").strip()
    if note:
        transfer.note = f"{transfer.note}\nQabul: {note}" if transfer.note else f"Qabul: {note}"
    db.flush()
    log_action(
        db, "TRANSFER_RECEIVE", "stock_transfer", transfer.id, user_id=user.id,
        old_values={"status": "in_transit"},
        new_values={
            "status": "received",
            "note": note or None,
            "items": [
                {"item_id": it.id, "product_id": it.product_id,
                 "qty_sent": float(it.qty_sent if it.qty_sent is not None else it.quantity),
                 "qty_received": float(q),
                 "shortage": float(Decimal(it.qty_sent if it.qty_sent is not None else it.quantity) - q),
                 "reason": rs}
                for it, q, rs in rows
            ],
        },
        **_transfer_scope(db, transfer),
    )
    return transfer


def confirm_transfer(db: Session, transfer_id: int, user, ctx=None) -> StockTransfer:
    """Eski /confirm: yo'ldagi transferni to'liq (qty_received=qty_sent) qabul qilish — receive_transfer'ga alias.
    pending bo'lsa — 400 "Avval yuboring"."""
    company_id = None if _role_value(user) == "super_admin" else user.company_id
    transfer = get_company_transfer(db, transfer_id, company_id)
    if transfer.status == TransferStatus.pending:
        raise HTTPException(status_code=400, detail="Transfer hali yuborilmagan — avval yuboring")
    if transfer.status != TransferStatus.in_transit:
        raise HTTPException(status_code=400, detail=f"Transfer holati '{transfer.status.value}' — tasdiqlab bo'lmaydi")
    return receive_transfer(db, transfer_id, None, user, ctx)


def update_transfer(db: Session, transfer_id: int, data, user_id: int, company_id: Optional[int] = None) -> StockTransfer:
    """Transferni tahrirlash. Hamma korxona tekshiruvi (transfer, omborlar, mahsulotlar)
    revert_transfer_stock(...) dan OLDIN bajariladi — xato bo'lsa qoldiq o'zgarmaydi.
    cancelled — 400; ikki bosqichli (yo'lda/qabul qilingan) — 409; pending — faqat sarlavha va qatorlar
    (qoldiq o'zgarmaydi); received (bir bosqichli) — avval qaytarish (manzil qoldig'i tekshiriladi),
    keyin yangi qatorlar qo'llanadi."""
    transfer = get_company_transfer(db, transfer_id, company_id)

    if transfer.status == TransferStatus.cancelled:
        raise HTTPException(status_code=400, detail="Bekor qilingan transferni tahrirlab bo'lmaydi")
    if _is_two_step_doc(transfer):
        raise HTTPException(
            status_code=409,
            detail="Ikki bosqichli transfer yuborilgandan keyin tahrirlanmaydi — bekor qilib qayta yarating",
        )

    if data.from_warehouse_id == data.to_warehouse_id:
        raise HTTPException(status_code=400, detail="Manba va maqsad ombor bir xil bo'lmasligi kerak")

    for wh_id in [data.from_warehouse_id, data.to_warehouse_id]:
        _get_company_warehouse(db, wh_id, company_id)

    # 0. Mahsulot, maqsad mahsulot va variantlarni oldindan tekshirish (qoldiqqa tegmasdan)
    collected_items = _validate_items(db, data, company_id)

    is_received = transfer.status == TransferStatus.received
    old_snapshot = _transfer_snapshot(transfer)

    # 1. Eski stock movementlarni teskari qaytarish (faqat qoldiq ko'chirilgan bo'lsa).
    # T1.19: asl harakatlar saqlanadi, storno yoziladi — tahrirdan keyin tarixda eski + storno + yangi qatorlar ko'rinadi
    if is_received:
        revert_transfer_stock(
            db, transfer.id, transfer.from_warehouse_id, transfer.to_warehouse_id, company_id,
            user_id=user_id, reason=f"Transfer #{transfer.number} tahrirlandi (storno)",
        )

    # 2. Eski itemlarni o'chirish
    for item in transfer.items:
        db.delete(item)
    db.flush()

    # 3. Header yangilash
    transfer.from_warehouse_id = data.from_warehouse_id
    transfer.to_warehouse_id = data.to_warehouse_id
    transfer.note = data.note

    # 4. Yangi itemlar va (received bo'lsa) stock movementlar
    _add_items(db, transfer, collected_items)
    if is_received:
        _apply_items(db, transfer, collected_items, user_id, suffix=" (yangilandi)")

    db.flush()
    # Eski itemlar db.delete, yangilari db.add orqali kiritildi — kolleksiya eskirmasin
    db.expire(transfer, ['items'])
    log_action(
        db, "TRANSFER_UPDATE", "stock_transfer", transfer.id, user_id=user_id,
        old_values=old_snapshot,
        new_values=_transfer_snapshot(transfer, _items_snapshot(collected_items)),
        **_transfer_scope(db, transfer),
    )
    return transfer


def cancel_transfer_stock(db: Session, transfer: StockTransfer, current_user, company_id: Optional[int],
                          action: str = "TRANSFER_CANCEL", reason: Optional[str] = None) -> None:
    """Transferni bekor qiladi (T1.19: qattiq o'chirish yo'q): qoldiq ko'chirilgan bo'lsa (yo'lda — manbaga,
    qabul qilingan — ikkala tomonda) storno harakat bilan qaytariladi, transfer faqat status=cancelled bo'ladi.
    pending — qoldiqqa tegmaydi. Auditga yoziladi. Commit qilmaydi."""
    old_snapshot = _transfer_snapshot(transfer)
    if transfer.status in (TransferStatus.received, TransferStatus.in_transit):
        # received: manzilda qoldiq yetmasa 400 (status o'zgarmaydi); in_transit: qty_sent manbaga qaytadi
        revert_transfer_stock(
            db, transfer.id, transfer.from_warehouse_id, transfer.to_warehouse_id, company_id,
            user_id=current_user.id,
            reason=(f"Transfer #{transfer.number} bekor qilindi (storno): {reason}" if reason else None),
        )
    transfer.status = TransferStatus.cancelled
    if reason:
        transfer.cancel_reason = reason
    db.flush()
    log_action(
        db, action, "stock_transfer", transfer.id, user_id=current_user.id,
        old_values=old_snapshot, new_values={"status": "cancelled", "reason": reason},
        **_transfer_scope(db, transfer),
    )


def cancel_transfer_flow(db: Session, transfer_id: int, user, reason: Optional[str] = None, ctx=None) -> StockTransfer:
    """T4.1: holatga qarab bekor qilish. pending — qoldiqqa tegmaydi; in_transit — qty_sent manba omborga
    qaytadi (jo'natuvchi/qabul qiluvchi filial yoki admin/director); received — faqat admin/director va
    manzilda yetarli qoldiq bo'lsa (aks holda 400). Commit qilmaydi."""
    company_id = None if _role_value(user) == "super_admin" else user.company_id
    transfer = _lock_transfer(db, transfer_id, company_id)
    if transfer.status == TransferStatus.cancelled:
        raise HTTPException(status_code=400, detail="Transfer allaqachon bekor qilingan")
    ctx = resolve_ctx(db, user, ctx)
    if not transfer_flags(user, ctx, transfer)["can_cancel"]:
        if transfer.status == TransferStatus.received:
            raise HTTPException(status_code=403, detail="Qabul qilingan transferni faqat admin/direktor bekor qila oladi")
        raise HTTPException(status_code=403, detail="Bu transfer sizning filialingizga tegishli emas")
    cancel_transfer_stock(db, transfer, user, company_id, action="TRANSFER_CANCEL", reason=(reason or "").strip() or None)
    return transfer


def delete_transfer(db: Session, transfer_id: int, current_user) -> None:
    """Transfer "o'chirish" (soft-delete): qoldiqlar storno harakat bilan qaytariladi, asl StockMovement
    qatorlari va transferning o'zi saqlanadi — status=cancelled. Transfer foydalanuvchi korxonasiga
    tegishli bo'lishi tekshiriladi (super_admin — hamma korxona). Ikki bosqichli transfer yo'lda yoki
    qabul qilingan bo'lsa — 409 (POST /cancel orqali bekor qilinadi)."""
    from app.models.user import UserRole

    company_id = None if current_user.role == UserRole.super_admin else current_user.company_id
    transfer = _lock_transfer(db, transfer_id, company_id)

    if transfer.status != TransferStatus.cancelled and _is_two_step_doc(transfer):
        raise HTTPException(
            status_code=409,
            detail="Ikki bosqichli transfer yuborilgandan keyin o'chirilmaydi — /cancel orqali bekor qiling",
        )
    if transfer.status != TransferStatus.cancelled:
        cancel_transfer_stock(db, transfer, current_user, company_id, action="TRANSFER_DELETE")
    db.commit()


def in_transit_summary(db: Session, warehouse_id: int, company_id: Optional[int]) -> list:
    """Manzil ombor uchun yo'ldagi tovar: status='in_transit' transferlarning qty_sent yig'indisi
    (stock_levels da ko'rinmaydi). Qaytaradi: [{product_id, variant_id, qty}]."""
    _get_company_warehouse(db, warehouse_id, company_id)
    rows = (
        db.query(StockTransferItem)
        .join(StockTransfer, StockTransfer.id == StockTransferItem.transfer_id)
        .filter(StockTransfer.to_warehouse_id == warehouse_id, StockTransfer.status == TransferStatus.in_transit)
        .all()
    )
    agg: dict = {}
    for it in rows:
        pid = it.target_product_id or it.product_id
        vid = None if it.target_product_id else it.variant_id
        qty = Decimal(it.qty_sent if it.qty_sent is not None else it.quantity)
        agg[(pid, vid)] = agg.get((pid, vid), Decimal(0)) + qty
    return [
        {"product_id": k[0], "variant_id": k[1], "qty": v}
        for k, v in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))
    ]
