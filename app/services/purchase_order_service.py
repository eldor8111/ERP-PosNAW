"""Xarid buyurtmalari (PO): yaratish, qabul qilish, tahrirlash, bekor qilish, o'chirish.

Qarz va to'lov qoidalari — app/services/supplier_ledger.py da. Qisqasi:
- ta'minotchi qarzi tovar qabul qilinganda paydo bo'ladi (qoralama/yuborilganda emas);
- xaridning balansga hissasi = qabul qilingan qiymat (chegirma bilan) − to'langan,
  u PurchaseOrder.supplier_debt da saqlanadi va har o'zgarishda farqi qo'shiladi;
- summalar bazada UZS da (unit_cost, total_amount, paid_amount), valyutali xarid
  exchange_rate (yaratilgandagi kurs) bo'yicha ta'minotchi valyutasiga o'tkaziladi.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.batch import Batch
from app.models.product import Product
from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.services import supplier_ledger as ledger
from app.services.inventory_service import receive_stock

ZERO = Decimal("0")
TINY = Decimal("0.0005")


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def generate_po_number(db: Session) -> str:
    """PO{YYYYMMDD}{NNNN}. Eng katta mavjud raqamdan davom etadi — o'chirilgan xariddan keyin
    ham takrorlanmaydi (avval "soni + 1" edi va unique xatosi berardi)."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"PO{today}"
    last = db.query(func.max(PurchaseOrder.number)).filter(PurchaseOrder.number.like(f"{prefix}%")).scalar()
    n = 0
    if last:
        try:
            n = int(last[len(prefix):])
        except ValueError:
            n = db.query(PurchaseOrder).filter(PurchaseOrder.number.like(f"{prefix}%")).count()
    return f"{prefix}{n + 1:04d}"


# ─── Tekshiruvlar ────────────────────────────────────────────────────────────

def _get_po(db: Session, po_id: int, user: User) -> PurchaseOrder:
    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    if user.role != UserRole.super_admin:
        q = q.filter(PurchaseOrder.company_id == user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    return po


def _company_supplier(db: Session, supplier_id: int, company_id: int) -> Supplier:
    s = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.company_id == company_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    return s


def _company_warehouse(db: Session, warehouse_id: int, company_id: int) -> Warehouse:
    wh = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id, Warehouse.is_active == True,
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    return wh


def _company_product(db: Session, product_id: int, company_id: int) -> Product:
    prod = db.query(Product).filter(
        Product.id == product_id, Product.company_id == company_id, Product.is_deleted == False,
    ).first()
    if not prod:
        raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {product_id}")
    if getattr(prod, "product_type", "stock") == "sell":
        raise HTTPException(status_code=400, detail=f"'{prod.name}' tarkibiy mahsulot bo'lgani uchun uni xarid qilib bo'lmaydi")
    return prod


# ─── Valyuta va qarz hissasi ─────────────────────────────────────────────────

def po_currency(po: PurchaseOrder) -> str:
    return (po.currency or "UZS").strip().upper() or "UZS"


def po_rate(db: Session, po: PurchaseOrder, persist: bool = True) -> Decimal:
    """Xarid kursi: yaratilgandagi kurs; eski xaridlarda joriy kurs (birinchi o'zgarishda qotiriladi)."""
    if po_currency(po) == "UZS":
        return Decimal("1")
    if po.exchange_rate and _d(po.exchange_rate) > 0:
        return _d(po.exchange_rate)
    rate = ledger.currency_rate(db, po.company_id, po_currency(po))
    if persist:
        po.exchange_rate = rate
    return rate


def recorded_contribution(db: Session, po: PurchaseOrder) -> Decimal:
    """Ta'minotchi balansiga shu xarid hozirgacha qo'shgan summa (supplier_debt_currency da)."""
    if po.supplier_debt is not None:
        return _d(po.supplier_debt)
    # Eski xaridlar: yaratilganda holatidan qat'i nazar (total − chegirma − to'langan) qo'shilgan,
    # faqat musbat bo'lsa; bekor qilish uni qaytarmagan.
    legacy_uzs = _d(po.total_amount) - _d(po.discount_amount) - _d(po.paid_amount)
    return legacy_uzs / po_rate(db, po, persist=False) if legacy_uzs > 0 else ZERO


def target_contribution(db: Session, po: PurchaseOrder, persist_rate: bool = True) -> Decimal:
    """Xaridning hozirgi hissasi (xarid valyutasida): qabul qilingan qiymat (chegirma ulushi bilan) − to'langan."""
    total = _d(po.total_amount)
    received = sum((_d(i.qty_received) * _d(i.unit_cost) for i in po.items), ZERO)
    ratio = (_d(po.discount_amount) / total) if total > 0 else ZERO
    net_received_uzs = received * (1 - ratio)
    return (net_received_uzs - _d(po.paid_amount)) / po_rate(db, po, persist=persist_rate)


def _sync_supplier_debt(db: Session, po: PurchaseOrder) -> None:
    supplier = db.get(Supplier, po.supplier_id)
    if not supplier:
        return
    cur = po_currency(po)
    target = target_contribution(db, po)
    old = recorded_contribution(db, po)
    old_cur = (po.supplier_debt_currency or cur).upper()
    if old_cur != cur:
        ledger.add(db, supplier, old_cur, -old)
        old = ZERO
    ledger.add(db, supplier, cur, target - old)
    po.supplier_debt = round(target, 4)
    po.supplier_debt_currency = cur


def display_amounts(db: Session, po: PurchaseOrder) -> dict:
    """Ro'yxat va ta'minotchi tarixi uchun bir xil hisob (xarid kursida, joriy kursda emas)."""
    cur = po_currency(po)
    rate = po_rate(db, po, persist=False)
    net_total = _d(po.total_amount) - _d(po.discount_amount)
    contribution = recorded_contribution(db, po) if po.supplier_debt is not None else target_contribution(db, po, persist_rate=False)
    return {
        "currency": cur,
        "rate": rate,
        "total_cur": round(net_total / rate, 2),
        "paid_cur": round(_d(po.paid_amount) / rate, 2),
        "debt_cur": round(contribution, 2),
        "debt_uzs": round(contribution * rate, 2),
    }


# ─── Qabul qilish ────────────────────────────────────────────────────────────

def _to_datetime(v):
    if v is None or isinstance(v, datetime):
        return v
    return datetime.combine(v, datetime.min.time())


def _update_product_on_receipt(db: Session, product: Product, item: POItem, company_id: int) -> None:
    """Oxirgi xarid narxi — mahsulot tannarxi (mahsulot tannarx valyutasida); yangi sotuv narxlari."""
    unit_uzs = _d(item.unit_cost)
    cur = (product.cost_currency or "UZS").strip().upper() or "UZS"
    product.cost_price = unit_uzs if cur == "UZS" else round(unit_uzs / ledger.currency_rate(db, company_id, cur), 4)
    if item.new_sale_price is not None:
        product.sale_price = item.new_sale_price
    if item.new_wholesale_price is not None:
        product.wholesale_price = item.new_wholesale_price


def _receive_item(db: Session, po: PurchaseOrder, item: POItem, qty: Decimal, user: User,
                  lot: Optional[str] = None, expiry=None) -> None:
    product = item.product or db.get(Product, item.product_id)
    if getattr(product, "product_type", "stock") == "sell":
        raise HTTPException(status_code=400, detail=f"'{product.name}' tarkibiy mahsulot bo'lgani uchun uni qabul qilib bo'lmaydi")
    receive_stock(
        db=db, product_id=item.product_id, quantity=qty, user_id=user.id,
        reason=f"PO #{po.number} qabul", reference_type="purchase_order", reference_id=po.id,
        warehouse_id=po.warehouse_id, variant_id=item.variant_id,
    )
    db.add(Batch(
        product_id=item.product_id, variant_id=item.variant_id, warehouse_id=po.warehouse_id,
        lot_number=lot or f"PO-{po.number}",
        expiry_date=_to_datetime(expiry) or item.expiry_date,  # qabulda berilmasa — xarid qatoridagi muddat
        initial_quantity=qty, quantity=qty, purchase_price=item.unit_cost,
        po_id=po.id, company_id=po.company_id,
    ))
    item.qty_received = _d(item.qty_received) + qty
    _update_product_on_receipt(db, product, item, po.company_id)


def _refresh_status(po: PurchaseOrder) -> None:
    if all(_d(i.qty_received) >= _d(i.qty_ordered) for i in po.items):
        po.status = POStatus.received
    elif any(_d(i.qty_received) > 0 for i in po.items):
        po.status = POStatus.partial


# ─── To'lov ──────────────────────────────────────────────────────────────────

def _po_payment_txs(db: Session, po: PurchaseOrder):
    from app.models.moliya import Transaction
    return db.query(Transaction).filter(
        Transaction.reference_type == "purchase_order",
        Transaction.reference_id == po.id,
        Transaction.company_id == po.company_id,
    ).order_by(Transaction.id).all()


def _record_po_payment(db: Session, po: PurchaseOrder, user: User, paid_uzs: Decimal, *,
                       payment_type: Optional[str], payment_currency: Optional[str],
                       payment_amount: Optional[Decimal], wallet_id: Optional[int], created_at=None):
    """Kassadan chiqqan pul: haqiqiy valyuta va summasi bilan (qarz hisobi uchun paid_amount — UZS)."""
    if paid_uzs <= 0:
        return None
    code = (payment_currency or "UZS").strip().upper() or "UZS"
    amount = _d(payment_amount) if (code != "UZS" and payment_amount) else paid_uzs
    if code == "UZS":
        amount = paid_uzs
    return ledger.record_cash(
        db, user=user, direction="out", amount=amount, currency=code, payment_type=payment_type or "cash",
        wallet_id=wallet_id, reference_type="purchase_order", reference_id=po.id,
        description=f"Ta'minotchi to'lovi #{po.number}" + (f" ({amount} {code})" if code != "UZS" else ""),
        meta={"po_paid_uzs": str(paid_uzs)}, warehouse_id=po.warehouse_id, created_at=created_at,
    )


def remove_po_payment(db: Session, tx) -> None:
    """Xarid to'lovi tranzaksiyasi o'chirildi (Moliya / ta'minotchi sahifasidan): kassa qaytadi,
    xaridning to'langan summasi kamayadi va ta'minotchi qarzi shunga oshadi."""
    po = db.query(PurchaseOrder).filter(
        PurchaseOrder.id == tx.reference_id, PurchaseOrder.company_id == tx.company_id,
    ).first()
    if po is None:
        ledger.reverse_cash(db, tx)
        return
    if po.supplier_debt is None:  # eski xarid: hozirgi hissani qotirib, faqat farqni qo'llaymiz
        po.supplier_debt = recorded_contribution(db, po)
        po.supplier_debt_currency = po_currency(po)
    meta = tx.meta or {}
    if meta.get("po_paid_uzs") is not None:
        paid_uzs = _d(meta["po_paid_uzs"])
    else:
        paid_uzs = _d(tx.amount) * ledger.currency_rate(db, po.company_id, tx.currency_code)
    po.paid_amount = max(ZERO, _d(po.paid_amount) - paid_uzs)
    ledger.reverse_cash(db, tx)
    _sync_supplier_debt(db, po)


def _build_items(db: Session, po: PurchaseOrder, items_data, company_id: int) -> Decimal:
    total = ZERO
    for it in items_data:
        prod = _company_product(db, it.product_id, company_id)
        item = POItem(
            product_id=prod.id,
            qty_ordered=it.qty_ordered,
            qty_received=ZERO,
            unit_cost=it.unit_cost,
            cost_currency=(it.cost_currency or "UZS").strip().upper() or "UZS",
            original_unit_cost=it.original_unit_cost if it.original_unit_cost is not None else it.unit_cost,
            expiry_date=it.expiry_date,
            new_sale_price=it.new_sale_price,
            new_wholesale_price=it.new_wholesale_price,
        )
        item.product = prod
        po.items.append(item)
        total += _d(it.qty_ordered) * _d(it.unit_cost)
    return total


def _check_discount(discount: Decimal, total: Decimal) -> Decimal:
    if discount > total + Decimal("0.01"):
        raise HTTPException(status_code=400, detail="Chegirma xarid summasidan oshib ketdi")
    return min(discount, total)


# ─── Amallar ─────────────────────────────────────────────────────────────────

def create_purchase_order(db: Session, data, current_user: User) -> PurchaseOrder:
    cid = current_user.company_id
    supplier = _company_supplier(db, data.supplier_id, cid)
    _company_warehouse(db, data.warehouse_id, cid)
    currency = (data.currency or "UZS").strip().upper() or "UZS"
    status = data.status or POStatus.draft

    po = PurchaseOrder(
        number=generate_po_number(db), supplier_id=supplier.id, warehouse_id=data.warehouse_id,
        note=data.note, expected_date=data.expected_date, created_by=current_user.id, company_id=cid,
        status=POStatus.draft, currency=currency, exchange_rate=ledger.currency_rate(db, cid, currency),
        total_amount=ZERO, paid_amount=ZERO, discount_amount=ZERO,
        supplier_debt=ZERO, supplier_debt_currency=currency,  # yangi xarid — hissa hali 0
    )
    db.add(po)
    db.flush()

    total = _build_items(db, po, data.items, cid)
    po.total_amount = total
    po.discount_amount = _check_discount(_d(data.discount_amount), total)
    po.paid_amount = _d(data.paid_amount)
    db.flush()

    if status == POStatus.received:
        for item in po.items:
            _receive_item(db, po, item, _d(item.qty_ordered), current_user)
        po.status = POStatus.received
    else:
        po.status = status

    _record_po_payment(
        db, po, current_user, po.paid_amount, payment_type=data.payment_type,
        payment_currency=data.payment_currency, payment_amount=data.payment_amount, wallet_id=data.wallet_id,
    )
    _sync_supplier_debt(db, po)
    log_action(db, action="CREATE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"number": po.number, "status": po.status.value, "total": str(total),
                           "paid": str(po.paid_amount), "currency": currency, "supplier_id": supplier.id})
    db.flush()
    return po


def receive_purchase_order(db: Session, po_id: int, data, current_user: User) -> PurchaseOrder:
    po = _get_po(db, po_id, current_user)
    if po.status == POStatus.cancelled:
        raise HTTPException(status_code=400, detail="Bekor qilingan buyurtmaga qabul qilib bo'lmaydi")
    if po.status == POStatus.received:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon to'liq qabul qilingan")

    items_map = {item.id: item for item in po.items}
    received_any = False
    for r in data.items:
        item = items_map.get(r.po_item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"PO item ID={r.po_item_id} topilmadi")
        qty = _d(r.qty_received)
        if qty <= 0:
            continue
        remaining = _d(item.qty_ordered) - _d(item.qty_received)
        if qty > remaining + TINY:
            raise HTTPException(status_code=400, detail=f"Qabul miqdori ({qty}) qolgan miqdordan ({remaining}) ko'p")
        _receive_item(db, po, item, qty, current_user, lot=r.lot_number, expiry=r.expiry_date)
        received_any = True
    if not received_any:
        raise HTTPException(status_code=400, detail="Qabul qilinadigan miqdor kiritilmagan")

    _refresh_status(po)
    _sync_supplier_debt(db, po)
    log_action(db, action="RECEIVE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"items": [{"po_item_id": r.po_item_id, "qty": str(r.qty_received)} for r in data.items],
                           "status": po.status.value})
    db.flush()
    return po


def cancel_purchase_order(db: Session, po_id: int, current_user: User) -> PurchaseOrder:
    """Bekor qilish: qabul qilinmagan qism uchun qarz yo'q; qabul qilingan qism va to'lov
    haqiqiy bo'lgani uchun saqlanadi (eski xaridlardagi ortiqcha qarz shu yerda tuzatiladi)."""
    po = _get_po(db, po_id, current_user)
    if po.status in (POStatus.received, POStatus.cancelled):
        raise HTTPException(status_code=400, detail=f"'{po.status.value}' holatdagi buyurtmani bekor qilib bo'lmaydi")
    po.status = POStatus.cancelled
    _sync_supplier_debt(db, po)
    log_action(db, action="CANCEL", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"number": po.number})
    db.flush()
    return po


def delete_purchase_order(db: Session, po_id: int, current_user: User) -> None:
    """O'chirish: qabul qilingan tovar ombordan aynan shu miqdorda ayiriladi (sotilgan bo'lsa —
    o'chirish taqiqlanadi), to'lovlar kassaga qaytariladi, qarz hissasi aynan qaytariladi."""
    from app.models.inventory import StockLevel, StockMovement, MovementType

    po = _get_po(db, po_id, current_user)

    # 1. Shu xariddan kelgan partiyalar ishlatilganmi?
    batches = db.query(Batch).filter(
        Batch.company_id == po.company_id,
        or_(Batch.po_id == po.id,
            and_(Batch.po_id.is_(None), Batch.lot_number == f"purchase_order-{po.id}")),  # eski avto-qabul
    ).all()
    used = [b for b in batches if _d(b.quantity) + TINY < _d(b.initial_quantity)]
    if used:
        names = sorted({(db.get(Product, b.product_id).name if db.get(Product, b.product_id) else str(b.product_id)) for b in used})
        raise HTTPException(
            status_code=400,
            detail=f"Bu xariddagi tovarlar sotilgan yoki ishlatilgan ({', '.join(names)}) — "
                   f"xaridni o'chirib bo'lmaydi. Ortiqchasini ta'minotchiga qaytarish orqali rasmiylashtiring.",
        )

    # 2. Qoldiqni aynan qabul qilingan miqdorga kamaytirish
    movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "purchase_order",
        StockMovement.reference_id == po.id,
        StockMovement.type == MovementType.IN,
    ).all()
    need = defaultdict(lambda: ZERO)
    for m in movements:
        need[(m.product_id, m.variant_id)] += _d(m.quantity)
    stocks = {}
    for (pid, vid), qty in need.items():
        q = db.query(StockLevel).filter(StockLevel.product_id == pid, StockLevel.warehouse_id == po.warehouse_id)
        q = q.filter(StockLevel.variant_id == vid) if vid else q.filter(StockLevel.variant_id.is_(None))
        stock = q.with_for_update().first()
        if not stock or _d(stock.quantity) + TINY < qty:
            prod = db.get(Product, pid)
            raise HTTPException(
                status_code=400,
                detail=f"'{prod.name if prod else pid}' qoldig'i ({_d(stock.quantity) if stock else 0}) "
                       f"qabul qilingan miqdordan ({qty}) kam — xaridni o'chirib bo'lmaydi",
            )
        stocks[(pid, vid)] = stock
    for (pid, vid), qty in need.items():
        stock = stocks[(pid, vid)]
        before = _d(stock.quantity)
        stock.quantity = before - qty
        db.add(StockMovement(
            product_id=pid, variant_id=vid, warehouse_id=po.warehouse_id, type=MovementType.OUT,
            qty_before=before, qty_after=before - qty, quantity=qty,
            reference_type="purchase_order_delete", reference_id=po.id, user_id=current_user.id,
            reason=f"PO #{po.number} o'chirildi",
        ))
    for b in batches:
        b.quantity = 0
        b.po_id = None

    # 3. To'lovlar kassaga qaytadi
    for tx in _po_payment_txs(db, po):
        ledger.reverse_cash(db, tx)

    # 4. Qarz hissasi aynan qaytariladi (boshqa xaridlar qarziga tegmaydi)
    supplier = db.get(Supplier, po.supplier_id)
    if supplier:
        ledger.add(db, supplier, (po.supplier_debt_currency or po_currency(po)), -recorded_contribution(db, po))

    log_action(db, action="DELETE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               old_values={"number": po.number, "status": po.status.value, "total": str(po.total_amount),
                           "paid": str(po.paid_amount), "supplier_id": po.supplier_id})
    db.flush()
    db.delete(po)
    db.commit()


def update_purchase_order(db: Session, po_id: int, data, current_user: User) -> PurchaseOrder:
    """Faqat qoralama yoki yuborilgan xaridni tahrirlash (qabul qilingan miqdorlar yo'qolmasligi uchun)."""
    po = _get_po(db, po_id, current_user)
    if po.status not in (POStatus.draft, POStatus.sent):
        raise HTTPException(status_code=400, detail="Faqat qoralama yoki yuborilgan xaridni tahrirlash mumkin")
    cid = po.company_id

    # Eski hissani to'liq olib tashlaymiz — oxirida yangi holat bo'yicha qo'shiladi
    old_supplier = db.get(Supplier, po.supplier_id)
    old_cur = (po.supplier_debt_currency or po_currency(po)).upper()
    if old_supplier:
        ledger.add(db, old_supplier, old_cur, -recorded_contribution(db, po))
    po.supplier_debt = ZERO
    po.supplier_debt_currency = old_cur

    if data.supplier_id is not None:
        po.supplier_id = _company_supplier(db, data.supplier_id, cid).id
    if data.warehouse_id is not None:
        po.warehouse_id = _company_warehouse(db, data.warehouse_id, cid).id
    if data.note is not None:
        po.note = data.note
    if data.expected_date is not None:
        po.expected_date = data.expected_date
    if data.currency:
        new_cur = data.currency.strip().upper()
        if new_cur != po_currency(po):
            po.currency = new_cur
            po.exchange_rate = ledger.currency_rate(db, cid, new_cur)

    if data.items is not None:
        po.items.clear()
        db.flush()
        po.total_amount = _build_items(db, po, data.items, cid)
    if data.discount_amount is not None:
        po.discount_amount = data.discount_amount
    po.discount_amount = _check_discount(_d(po.discount_amount), _d(po.total_amount))

    if data.paid_amount is not None:
        old_txs = _po_payment_txs(db, po)
        wallet_id = data.wallet_id or (old_txs[0].wallet_id if old_txs else None)
        ptype = data.payment_type or (old_txs[0].payment_type if old_txs else "cash")
        created_at = old_txs[0].created_at if old_txs else None
        for tx in old_txs:
            ledger.reverse_cash(db, tx)
        po.paid_amount = _d(data.paid_amount)
        _record_po_payment(
            db, po, current_user, po.paid_amount, payment_type=ptype,
            payment_currency=data.payment_currency, payment_amount=data.payment_amount,
            wallet_id=wallet_id, created_at=created_at,
        )

    db.flush()
    _sync_supplier_debt(db, po)
    log_action(db, action="UPDATE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"total": str(po.total_amount), "paid": str(po.paid_amount),
                           "currency": po_currency(po), "supplier_id": po.supplier_id})
    db.flush()
    return po
