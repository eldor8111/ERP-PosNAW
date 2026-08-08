from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.batch import Batch
from app.models.warehouse import Warehouse
from app.models.product import Product
from app.models.user import User, UserRole
from app.services.inventory_service import receive_stock


def generate_po_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"PO{today}"
    count = db.query(PurchaseOrder).filter(PurchaseOrder.number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}"


def _get_currency_rate(db: Session, currency_code: str) -> Decimal:
    """Valyuta kursini qaytaradi. UZS uchun 1.0"""
    if not currency_code or currency_code == "UZS":
        return Decimal("1")
    from app.models.currency import Currency as CurrencyModel
    obj = db.query(CurrencyModel).filter(CurrencyModel.code == currency_code).first()
    return Decimal(str(obj.rate)) if obj and obj.rate else Decimal("1")


def _update_debt_balances_add(db: Session, supplier, amount_uzs: Decimal, po_currency: str) -> None:
    """Ta'minotchi debt_balances JSON maydoniga qarz qo'shadi.
    
    - UZS xaridda: debt_balances['UZS'] ga UZS miqdor qo'shiladi
    - Chet el valyutasida: debt_balances['USD'] ga original valyuta miqdori qo'shiladi
    """
    if amount_uzs <= Decimal("0"):
        return

    balances = dict(supplier.debt_balances or {})
    po_currency = (po_currency or "UZS").strip().upper()

    if po_currency == "UZS":
        balances["UZS"] = float(Decimal(str(balances.get("UZS", 0))) + amount_uzs)
    else:
        rate = _get_currency_rate(db, po_currency)
        if rate > Decimal("0"):
            orig_amount = amount_uzs / rate
        else:
            orig_amount = amount_uzs
        balances[po_currency] = float(Decimal(str(balances.get(po_currency, 0))) + orig_amount)

    supplier.debt_balances = balances
    flag_modified(supplier, "debt_balances")


def _update_debt_balances_remove(db: Session, supplier, amount_uzs: Decimal, po_currency: str) -> None:
    """Ta'minotchi debt_balances JSON maydonidan qarz ayiradi (xarid o'chirilganda/tahrirlaganda)."""
    if amount_uzs <= Decimal("0"):
        return

    balances = dict(supplier.debt_balances or {})
    po_currency = (po_currency or "UZS").strip().upper()

    if po_currency == "UZS":
        current = Decimal(str(balances.get("UZS", 0)))
        balances["UZS"] = float(max(Decimal("0"), current - amount_uzs))
    else:
        rate = _get_currency_rate(db, po_currency)
        if rate > Decimal("0"):
            orig_amount = amount_uzs / rate
        else:
            orig_amount = amount_uzs
        current = Decimal(str(balances.get(po_currency, 0)))
        balances[po_currency] = float(max(Decimal("0"), current - orig_amount))

    supplier.debt_balances = balances
    flag_modified(supplier, "debt_balances")


def create_purchase_order(db: Session, data, current_user: User) -> PurchaseOrder:
    warehouse = db.query(Warehouse).filter(Warehouse.id == data.warehouse_id, Warehouse.is_active == True).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")

    po_currency = (getattr(data, 'currency', 'UZS') or 'UZS').strip().upper()

    po = PurchaseOrder(
        number=generate_po_number(db),
        supplier_id=data.supplier_id,
        warehouse_id=data.warehouse_id,
        note=data.note,
        expected_date=data.expected_date,
        created_by=current_user.id,
        company_id=current_user.company_id,
        status=data.status if getattr(data, 'status', None) else POStatus.draft,
        currency=po_currency,
    )
    # Add optional payment fields directly to the object since they were added to DB
    if hasattr(data, 'paid_amount'): po.paid_amount = data.paid_amount
    if hasattr(data, 'discount_amount'): po.discount_amount = data.discount_amount
    if hasattr(data, 'payment_type'): po.payment_type = data.payment_type

    db.add(po)
    db.flush()

    total = Decimal("0")
    for item_data in data.items:
        prod = db.query(Product).filter(
            Product.id == item_data.product_id,
            Product.company_id == current_user.company_id,
        ).first()
        if not prod:
            raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {item_data.product_id}")
            
        if getattr(prod, 'product_type', 'stock') == 'sell':
            raise HTTPException(status_code=400, detail=f"'{prod.name}' tarkibiy mahsulot bo'lgani uchun uni xarid qilib bo'lmaydi")

        # Update product prices if requested
        if item_data.new_sale_price is not None or item_data.new_wholesale_price is not None:
            if item_data.new_sale_price is not None:
                prod.sale_price = item_data.new_sale_price
            if item_data.new_wholesale_price is not None:
                prod.wholesale_price = item_data.new_wholesale_price

        item = POItem(
            po_id=po.id,
            product_id=item_data.product_id,
            qty_ordered=item_data.qty_ordered,
            qty_received=item_data.qty_ordered if po.status == POStatus.received else Decimal("0"),
            unit_cost=item_data.unit_cost,
            cost_currency=getattr(item_data, 'cost_currency', 'UZS') or 'UZS',
            original_unit_cost=getattr(item_data, 'original_unit_cost', None) or item_data.unit_cost,
        )
        db.add(item)
        total += item_data.qty_ordered * item_data.unit_cost

        # If perfectly auto-receiving directly from PO creation
        if po.status == POStatus.received:
            receive_stock(
                db=db,
                product_id=item_data.product_id,
                quantity=item_data.qty_ordered,
                user_id=current_user.id,
                reason=f"PO #{po.number} avto-qabul",
                reference_type="purchase_order",
                reference_id=po.id,
                warehouse_id=po.warehouse_id,
            )
            batch = Batch(
                product_id=item_data.product_id,
                warehouse_id=po.warehouse_id,
                lot_number=f"PO-{po.number}",
                initial_quantity=item_data.qty_ordered,
                quantity=item_data.qty_ordered,
                purchase_price=item_data.unit_cost,
                po_id=po.id,
                company_id=current_user.company_id,
            )
            db.add(batch)

    # Set amounts on the PO
    po.total_amount = total
    paid_amount = Decimal(str(getattr(data, 'paid_amount', Decimal("0")) or 0))
    discount_amount = Decimal(str(getattr(data, 'discount_amount', Decimal("0")) or 0))
    
    po.paid_amount = paid_amount
    po.discount_amount = discount_amount
    
    # Financial Transaction generation
    if paid_amount > 0:
        from app.models.moliya import Transaction, Wallet
        wallet_id = getattr(data, 'wallet_id', None)
        tx = Transaction(
            branch_id=current_user.branch_id if current_user.branch_id else po.warehouse_id,
            company_id=current_user.company_id,
            type="expense",
            amount=paid_amount,
            wallet_id=wallet_id,
            currency_code=po_currency,
            payment_type=getattr(data, 'payment_type', 'cash') or 'cash',
            reference_type="purchase_order",
            reference_id=po.id,
            description=f"Ta'minotchi to'lovi #{po.number}",
            user_id=current_user.id,
        )
        db.add(tx)
        if wallet_id:
            wallet = db.get(Wallet, wallet_id)
            if wallet:
                wallet.balance = float(wallet.balance) - float(paid_amount)

    # ── Ta'minotchi qarzini hisoblash va yangilash ──────────────────────────
    from app.models.supplier import Supplier
    supplier = db.get(Supplier, po.supplier_id)
    if supplier:
        debt_added = total - discount_amount - paid_amount
        if debt_added > Decimal("0"):
            # 1) Agregat UZS balansini yangilash
            supplier.debt_balance = float(
                Decimal(str(supplier.debt_balance or 0)) + debt_added
            )
            # 2) Valyuta bo'yicha JSON balansini yangilash ✅ TUZATILDI
            _update_debt_balances_add(db, supplier, debt_added, po_currency)

    db.flush()
    return po


def receive_purchase_order(db: Session, po_id: int, data, current_user: User) -> PurchaseOrder:
    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if po.status == POStatus.cancelled:
        raise HTTPException(status_code=400, detail="Bekor qilingan buyurtmaga qabul qilib bo'lmaydi")
    if po.status == POStatus.received:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon to'liq qabul qilingan")

    po_items_map = {item.id: item for item in po.items}

    for receive_item in data.items:
        po_item = po_items_map.get(receive_item.po_item_id)
        if not po_item:
            raise HTTPException(status_code=404, detail=f"PO item ID={receive_item.po_item_id} topilmadi")

        if getattr(po_item.product, 'product_type', 'stock') == 'sell':
            raise HTTPException(status_code=400, detail=f"'{po_item.product.name}' tarkibiy mahsulot bo'lgani uchun uni qabul qilib bo'lmaydi")

        remaining = po_item.qty_ordered - po_item.qty_received
        if receive_item.qty_received > remaining:
            raise HTTPException(
                status_code=400,
                detail=f"Qabul miqdori ({receive_item.qty_received}) buyurtmadan ({remaining}) ko'p"
            )

        po_item.qty_received += receive_item.qty_received

        # Update stock
        receive_stock(
            db=db,
            product_id=po_item.product_id,
            quantity=receive_item.qty_received,
            user_id=current_user.id,
            reason=f"PO #{po.number} qabul",
            reference_type="purchase_order",
            reference_id=po.id,
            warehouse_id=po.warehouse_id,
        )

        # Always create a financial batch for FIFO tracking
        lot = receive_item.lot_number or f"PO-{po.number}"
        batch = Batch(
            product_id=po_item.product_id,
            warehouse_id=po.warehouse_id,
            lot_number=lot,
            expiry_date=receive_item.expiry_date,
            initial_quantity=receive_item.qty_received,
            quantity=receive_item.qty_received,
            purchase_price=po_item.unit_cost,
            po_id=po.id,
            company_id=current_user.company_id,
        )
        db.add(batch)

    # Update PO status
    all_received = all(item.qty_received >= item.qty_ordered for item in po.items)
    any_received = any(item.qty_received > 0 for item in po.items)
    if all_received:
        po.status = POStatus.received
    elif any_received:
        po.status = POStatus.partial

    db.flush()
    return po


def delete_purchase_order(db: Session, po_id: int, current_user: User) -> None:
    """Xarid buyurtmasini o'chirish: qabul qilingan mahsulotlarni qaytarish"""
    from app.models.moliya import Transaction, Wallet
    from app.models.inventory import StockMovement, StockLevel

    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if po.status == POStatus.cancelled:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon bekor qilingan")

    po_currency = (getattr(po, 'currency', 'UZS') or 'UZS').strip().upper()

    # 1. StockMovement yozuvlarini o'chirish va stockni qaytarish
    old_movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "purchase_order",
        StockMovement.reference_id == po.id
    ).all()

    for movement in old_movements:
        stock = db.query(StockLevel).filter(
            StockLevel.product_id == movement.product_id,
            StockLevel.warehouse_id == po.warehouse_id
        ).first()
        if stock and movement.qty_before is not None:
            stock.quantity = movement.qty_before
        db.delete(movement)

    # 2. Moliya tranzaksiyalarini qaytarish (barcha expense tranzaksiyalar)
    old_txs = db.query(Transaction).filter(
        Transaction.reference_type == "purchase_order",
        Transaction.reference_id == po.id,
        Transaction.type == "expense"
    ).all()
    for tx in old_txs:
        if tx.wallet_id:
            wallet = db.get(Wallet, tx.wallet_id)
            if wallet:
                wallet.balance = float(wallet.balance) + float(tx.amount)
        db.delete(tx)

    # 3. Ta'minotchi qarzini orqaga qaytarish ✅ TUZATILDI
    from app.models.supplier import Supplier
    supplier = db.get(Supplier, po.supplier_id)
    if supplier:
        debt_added = Decimal(str(po.total_amount or 0)) - Decimal(str(po.discount_amount or 0)) - Decimal(str(po.paid_amount or 0))
        if debt_added > Decimal("0"):
            # 1) Agregat UZS balansini qaytarish
            supplier.debt_balance = float(
                max(Decimal("0"), Decimal(str(supplier.debt_balance or 0)) - debt_added)
            )
            # 2) Valyuta bo'yicha JSON balansdan ham ayirish ✅ TUZATILDI
            _update_debt_balances_remove(db, supplier, debt_added, po_currency)

    # 4. Batch (FIFO) yozuvlaridan PO linkini uzish — FK constraint xatosini oldini olish
    batches = db.query(Batch).filter(Batch.po_id == po.id).all()
    for batch in batches:
        batch.quantity = 0       # Stock reversal bilan mos: batch ham tozalanadi
        batch.po_id = None       # FK constraint: purchase_orders.id ga bog'liqlikni uzish

    db.flush()

    # 5. PO o'chirish (POItem lar cascade="all, delete-orphan" bilan avtomatik o'chadi)
    db.delete(po)
    db.commit()



def update_purchase_order(db: Session, po_id: int, data, current_user: User) -> PurchaseOrder:
    """Draft yoki sent statusdagi PO ni yangilash. Mahsulot qoldiqlari o'zgartirilmaydi."""
    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if po.status in (POStatus.received, POStatus.cancelled):
        raise HTTPException(
            status_code=400,
            detail="Qabul qilingan yoki bekor qilingan buyurtmani tahrirlab bo'lmaydi"
        )

    from app.models.supplier import Supplier

    old_po_currency = (getattr(po, 'currency', 'UZS') or 'UZS').strip().upper()

    # 1. Eski ta'minotchi qarzini orqaga qaytarish ✅ TUZATILDI
    old_debt = Decimal(str(po.total_amount or 0)) - Decimal(str(po.discount_amount or 0)) - Decimal(str(po.paid_amount or 0))
    old_supplier = db.get(Supplier, po.supplier_id)
    if old_supplier and old_debt > Decimal("0"):
        # 1a) Agregat UZS
        old_supplier.debt_balance = float(
            max(Decimal("0"), Decimal(str(old_supplier.debt_balance or 0)) - old_debt)
        )
        # 1b) Valyuta bo'yicha JSON ✅ TUZATILDI
        _update_debt_balances_remove(db, old_supplier, old_debt, old_po_currency)

    # 2. Asosiy maydonlarni yangilash
    if data.supplier_id is not None:
        po.supplier_id = data.supplier_id
    if data.warehouse_id is not None:
        po.warehouse_id = data.warehouse_id
    if data.note is not None:
        po.note = data.note
    if data.expected_date is not None:
        po.expected_date = data.expected_date

    # Moliya tranzaksiyasini yangilash
    if data.paid_amount is not None:
        from app.models.moliya import Transaction, Wallet
        old_paid = po.paid_amount or Decimal("0")
        new_paid = Decimal(str(data.paid_amount))
        
        # Eski tranzaksiyani bekor qilish
        old_tx = db.query(Transaction).filter(
            Transaction.reference_type == "purchase_order",
            Transaction.reference_id == po.id,
            Transaction.type == "expense"
        ).first()
        
        orig_created_at = None
        if old_tx:
            orig_created_at = old_tx.created_at
            if old_tx.wallet_id:
                w = db.get(Wallet, old_tx.wallet_id)
                if w:
                    w.balance = float(w.balance) + float(old_tx.amount)
            db.delete(old_tx)
        
        # Yangi tranzaksiyani yozish (agar yangi summa > 0 bo'lsa)
        if new_paid > 0:
            wallet_id = getattr(data, 'wallet_id', None)
            new_po_currency = (getattr(po, 'currency', 'UZS') or 'UZS').strip().upper()
            tx = Transaction(
                branch_id=current_user.branch_id if current_user.branch_id else po.warehouse_id,
                company_id=current_user.company_id,
                type="expense",
                amount=new_paid,
                wallet_id=wallet_id,
                currency_code=new_po_currency,
                payment_type=getattr(data, 'payment_type', 'cash') or 'cash',
                reference_type="purchase_order",
                reference_id=po.id,
                description=f"Ta'minotchi to'lovi #{po.number} (tahrirlangan)",
                user_id=current_user.id,
                created_at=orig_created_at if orig_created_at else None,
            )
            db.add(tx)
            if wallet_id:
                w = db.get(Wallet, wallet_id)
                if w:
                    w.balance = float(w.balance) - float(new_paid)

        po.paid_amount = new_paid

    if data.discount_amount is not None:
        po.discount_amount = data.discount_amount

    # 3. Mahsulotlarni yangilash (agar berilgan bo'lsa)
    if data.items is not None:
        # Eski itemlarni o'chirish
        for old_item in list(po.items):
            db.delete(old_item)
        db.flush()

        total = Decimal("0")
        for item_data in data.items:
            # Narxlarni yangilash
            if item_data.new_sale_price is not None or item_data.new_wholesale_price is not None:
                prod = db.query(Product).filter(
                    Product.id == item_data.product_id,
                    Product.company_id == current_user.company_id,
                ).first()
                if prod:
                    if item_data.new_sale_price is not None:
                        prod.sale_price = item_data.new_sale_price
                    if item_data.new_wholesale_price is not None:
                        prod.wholesale_price = item_data.new_wholesale_price

            item = POItem(
                po_id=po.id,
                product_id=item_data.product_id,
                qty_ordered=item_data.qty_ordered,
                qty_received=Decimal("0"),
                unit_cost=item_data.unit_cost,
                cost_currency=getattr(item_data, 'cost_currency', 'UZS') or 'UZS',
                original_unit_cost=getattr(item_data, 'original_unit_cost', None) or item_data.unit_cost,
            )
            db.add(item)
            total += item_data.qty_ordered * item_data.unit_cost

        po.total_amount = total
    db.flush()

    # 4. Yangi ta'minotchi qarzini hisoblash ✅ TUZATILDI
    new_po_currency = (getattr(po, 'currency', 'UZS') or 'UZS').strip().upper()
    new_supplier = db.get(Supplier, po.supplier_id)
    if new_supplier:
        new_debt = Decimal(str(po.total_amount or 0)) - Decimal(str(po.discount_amount or 0)) - Decimal(str(po.paid_amount or 0))
        if new_debt > Decimal("0"):
            # 4a) Agregat UZS
            new_supplier.debt_balance = float(
                Decimal(str(new_supplier.debt_balance or 0)) + new_debt
            )
            # 4b) Valyuta bo'yicha JSON ✅ TUZATILDI
            _update_debt_balances_add(db, new_supplier, new_debt, new_po_currency)

    db.flush()
    return po
