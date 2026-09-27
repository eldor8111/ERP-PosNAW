"""Ta'minotchiga tovar qaytarish: yaratish, bekor qilish, qaytim to'lovini o'chirish.

Hujjat AuditLog(action="RETURN_TO_SUPPLIER", entity_type="supplier") da saqlanadi:
  movements  — [{id, product_id, variant_id, qty, value, warehouse_id, batches: [[batch_id, qty]]}]
  value      — qaytarilgan tovar qiymati (UZS)
  received   — ta'minotchi qaytargan pul (UZS)
  allocation — qarzga ta'sir {valyuta: summa} (supplier_ledger.apply_payment natijasi),
               bekor qilishda aynan shu qaytariladi
  refund_tx_id, reverted
Qarzga ta'sir: qarz (qiymat − olingan pul) ga kamayadi; ortig'i avans bo'ladi.
"""
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.inventory import MovementType, StockMovement
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.services import supplier_ledger as ledger

ZERO = Decimal("0")
ACTION = "RETURN_TO_SUPPLIER"


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def _take_batches(db: Session, product_id: int, qty: Decimal, warehouse_id: Optional[int],
                  company_id: int, variant_id: Optional[int]) -> list:
    """Partiyalardan eng eskisidan boshlab ayiradi (partiya yetmasa — borigacha, xato bermaydi)."""
    q = db.query(Batch).filter(
        Batch.product_id == product_id, Batch.company_id == company_id, Batch.quantity > 0,
    )
    q = q.filter(Batch.variant_id == variant_id) if variant_id else q.filter(Batch.variant_id.is_(None))
    if warehouse_id is not None:
        q = q.filter(Batch.warehouse_id == warehouse_id)
    taken, remaining = [], qty
    for b in q.order_by(Batch.created_at.asc(), Batch.id.asc()).with_for_update().all():
        if remaining <= 0:
            break
        take = min(remaining, _d(b.quantity))
        b.quantity = _d(b.quantity) - take
        remaining -= take
        taken.append([b.id, str(take)])
    return taken


def _movement_warehouse(db: Session, mv: StockMovement, company_id: int) -> Optional[int]:
    """Harakat ombori. Eski harakatlarda warehouse_id yozilmagan: sababdagi "Ombor #N" dan,
    bo'lmasa mahsulot qoldig'i turgan yagona ombordan, bo'lmasa kompaniyaning birinchi omboridan."""
    import re
    from app.models.inventory import StockLevel

    if mv.warehouse_id:
        return mv.warehouse_id
    m = re.search(r"Ombor #(\d+)", mv.reason or "")
    if m:
        wh = db.query(Warehouse).filter(Warehouse.id == int(m.group(1)), Warehouse.company_id == company_id).first()
        if wh:
            return wh.id
    q = db.query(StockLevel.warehouse_id).filter(
        StockLevel.product_id == mv.product_id, StockLevel.warehouse_id.isnot(None),
    )
    q = q.filter(StockLevel.variant_id == mv.variant_id) if mv.variant_id else q.filter(StockLevel.variant_id.is_(None))
    wh_ids = {r[0] for r in q.all()}
    if len(wh_ids) == 1:
        return wh_ids.pop()
    wh = db.query(Warehouse).filter(Warehouse.company_id == company_id, Warehouse.is_active == True).order_by(Warehouse.id).first()
    return wh.id if wh else None


def _find_log(db: Session, supplier_id: int, movement_id: int) -> Optional[AuditLog]:
    logs = db.query(AuditLog).filter(
        AuditLog.action == ACTION, AuditLog.entity_type == "supplier", AuditLog.entity_id == supplier_id,
    ).order_by(AuditLog.id.desc()).all()
    for log in logs:
        vals = log.new_values or {}
        if vals.get("reverted"):
            continue
        if any(m.get("id") == movement_id for m in vals.get("movements", [])):
            return log
    return None


def return_logs(db: Session, supplier_id: int) -> list:
    """Ta'minotchi tarixi uchun amaldagi (bekor qilinmagan) qaytarish hujjatlari."""
    res = []
    logs = db.query(AuditLog).filter(
        AuditLog.action == ACTION, AuditLog.entity_type == "supplier", AuditLog.entity_id == supplier_id,
    ).all()
    for log in logs:
        vals = log.new_values or {}
        if vals.get("reverted"):
            continue
        n = len(vals.get("movements", []))
        note = (vals.get("note") or "").strip()
        res.append({
            "id": log.id,
            "date": log.created_at.isoformat() if log.created_at else "",
            "value": float(_d(vals.get("value"))),
            "received": float(_d(vals.get("received"))),
            "user_id": log.user_id,
            "description": f"Ta'minotchiga qaytarish: {n} ta pozitsiya" + (f" — {note}" if note else ""),
        })
    return res


def create_supplier_return(db: Session, data, user) -> dict:
    from app.services.inventory_service import deduct_stock

    cid = user.company_id
    supplier = db.query(Supplier).filter(
        Supplier.id == data.supplier_id, Supplier.company_id == cid, Supplier.is_active == True,
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    if data.warehouse_id is not None:
        wh = db.query(Warehouse).filter(Warehouse.id == data.warehouse_id, Warehouse.company_id == cid).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Ombor topilmadi")
    received = _d(data.received_amount)
    if received > 0 and not data.wallet_id:
        raise HTTPException(status_code=400, detail="Qaytgan pul uchun kassani tanlang")

    movements_info = []
    total_value = ZERO
    for item in data.items:
        qty = _d(item.quantity)
        if qty <= 0:
            continue
        product = db.query(Product).filter(
            Product.id == item.product_id, Product.company_id == cid, Product.is_deleted == False,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {item.product_id}")
        res = deduct_stock(
            db=db, product_id=product.id, quantity=qty, user_id=user.id,
            reason=f"Ta'minotchiga qaytarish: {supplier.name}. {data.note or ''}".strip(),
            reference_type="return_to_supplier", reference_id=supplier.id,
            warehouse_id=data.warehouse_id, variant_id=item.variant_id,
        )
        mvs = res if isinstance(res, list) else [res]
        item_value = qty * _d(item.unit_cost)
        total_value += item_value
        for mv in mvs:
            mv_qty = _d(mv.quantity)
            movements_info.append({
                "id": mv.id, "product_id": product.id, "variant_id": item.variant_id,
                "qty": str(mv_qty), "value": str(round(item_value * mv_qty / qty, 2)),
                "warehouse_id": mv.warehouse_id,
                "batches": _take_batches(db, product.id, mv_qty, mv.warehouse_id, cid, item.variant_id),
            })
    if not movements_info:
        raise HTTPException(status_code=400, detail="Qaytariladigan mahsulot kiritilmagan")

    before = {k: float(v) for k, v in ledger.balances(supplier).items()}
    net = total_value - received
    if net > 0:
        allocation = ledger.apply_payment(db, supplier, net, "UZS")
    elif net < 0:  # ta'minotchi tovar qiymatidan ko'p pul qaytardi — qarzimiz oshadi
        ledger.add(db, supplier, "UZS", -net)
        allocation = {"UZS": str(net)}
    else:
        allocation = {}

    log = AuditLog(
        user_id=user.id, action=ACTION, entity_type="supplier", entity_id=supplier.id,
        old_values={"debt_balances": before},
        new_values={
            "movements": movements_info, "value": str(round(total_value, 2)), "received": str(received),
            "allocation": allocation, "warehouse_id": data.warehouse_id, "note": data.note,
            "refund_tx_id": None, "reverted": False,
        },
    )
    db.add(log)
    db.flush()

    if received > 0:
        tx = ledger.record_cash(
            db, user=user, direction="in", amount=received, currency="UZS",
            payment_type=getattr(data, "payment_type", None) or "cash", wallet_id=data.wallet_id,
            reference_type="return_to_supplier", reference_id=supplier.id,
            description=f"Ta'minotchidan qaytarish uchun pul qaytdi: {supplier.name}",
            meta={"return_log_id": log.id, "refund_uzs": str(received)}, warehouse_id=data.warehouse_id,
        )
        log.new_values = {**log.new_values, "refund_tx_id": tx.id}
    db.flush()
    return {"value": total_value, "received": received, "log_id": log.id}


def revert_supplier_return(db: Session, movement: StockMovement, user) -> dict:
    """Qaytarishni bekor qilish — butun hujjat bo'yicha: qoldiq va partiyalar tiklanadi,
    qarzga ta'sir aynan qaytariladi, qaytim to'lovi kassadan olib tashlanadi."""
    from app.models.moliya import Transaction
    from app.services.inventory_service import get_or_create_stock

    def _restore(mv: StockMovement, batches=()):
        wh_id = _movement_warehouse(db, mv, user.company_id)
        stock = get_or_create_stock(db, mv.product_id, wh_id, mv.variant_id)
        before = _d(stock.quantity)
        stock.quantity = before + _d(mv.quantity)
        db.add(StockMovement(
            product_id=mv.product_id, variant_id=mv.variant_id, warehouse_id=wh_id,
            type=MovementType.IN, qty_before=before, qty_after=stock.quantity, quantity=mv.quantity,
            reference_type="return_revert", reference_id=mv.id, user_id=user.id,
            reason=f"Ta'minotchi qaytaruvi bekor qilindi (asl harakat ID: {mv.id})",
        ))
        for batch_id, qty in batches:
            b = db.get(Batch, batch_id)
            if b:
                b.quantity = _d(b.quantity) + _d(qty)
        db.delete(mv)

    log = _find_log(db, movement.reference_id, movement.id) if movement.reference_id else None
    if not log:
        # Tuzatishdan oldingi qaytarish: qiymati saqlanmagan — faqat qoldiq tiklanadi
        _restore(movement)
        return {"count": 1, "legacy": True}

    vals = dict(log.new_values or {})
    count = 0
    for info in vals.get("movements", []):
        mv = db.get(StockMovement, info.get("id"))
        if mv:
            _restore(mv, info.get("batches") or [])
            count += 1

    supplier = db.get(Supplier, log.entity_id)
    if supplier:
        ledger.reverse_allocation(db, supplier, vals.get("allocation") or {})
    if vals.get("refund_tx_id"):
        tx = db.get(Transaction, vals["refund_tx_id"])
        if tx:
            ledger.reverse_cash(db, tx)

    vals["reverted"] = True
    vals["reverted_by"] = user.id
    log.new_values = vals
    db.add(AuditLog(user_id=user.id, action=f"{ACTION}_REVERT", entity_type="supplier",
                    entity_id=log.entity_id, new_values={"return_log_id": log.id, "count": count}))
    db.flush()
    return {"count": count, "legacy": False}


def on_refund_tx_deleted(db: Session, tx) -> None:
    """Qaytim to'lovi (ta'minotchidan kelgan pul) o'chirildi: pul kelmagan deb hisoblanadi,
    demak qaytarilgan tovar qarzni shu summaga ko'proq kamaytiradi."""
    supplier = db.query(Supplier).filter(Supplier.id == tx.reference_id, Supplier.company_id == tx.company_id).first()
    if not supplier:
        return
    meta = tx.meta or {}
    amount = _d(meta.get("refund_uzs") or tx.amount)
    if amount <= 0:
        return
    alloc = ledger.apply_payment(db, supplier, amount, "UZS")
    log = db.get(AuditLog, meta["return_log_id"]) if meta.get("return_log_id") else None
    if log and log.action == ACTION:
        vals = dict(log.new_values or {})
        merged = {k: _d(v) for k, v in (vals.get("allocation") or {}).items()}
        for k, v in alloc.items():
            merged[k] = merged.get(k, ZERO) + _d(v)
        vals["allocation"] = {k: str(v) for k, v in merged.items()}
        vals["received"] = "0"
        vals["refund_tx_id"] = None
        log.new_values = vals
