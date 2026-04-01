from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.batch import Batch
from app.models.warehouse import Warehouse
from app.services.inventory_service import receive_stock


def generate_po_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"PO{today}"
    count = db.query(PurchaseOrder).filter(PurchaseOrder.number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}"


from app.models.user import User
from app.models.product import Product

def create_purchase_order(db: Session, data, current_user: User) -> PurchaseOrder:
    warehouse = db.query(Warehouse).filter(Warehouse.id == data.warehouse_id, Warehouse.is_active == True).first()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")

    po = PurchaseOrder(
        number=generate_po_number(db),
        supplier_id=data.supplier_id,
        warehouse_id=data.warehouse_id,
        note=data.note,
        expected_date=data.expected_date,
        created_by=current_user.id,
        company_id=current_user.company_id,
        status=data.status if getattr(data, 'status', None) else POStatus.draft,
    )
    # Add optional payment fields directly to the object since they were added to DB
    if hasattr(data, 'paid_amount'): po.paid_amount = data.paid_amount
    if hasattr(data, 'discount_amount'): po.discount_amount = data.discount_amount
    if hasattr(data, 'payment_type'): po.payment_type = data.payment_type

    db.add(po)
    db.flush()

    total = Decimal("0")
    for item_data in data.items:
        # Update product prices if requested
        if item_data.new_sale_price is not None or item_data.new_wholesale_price is not None:
            prod = db.query(Product).filter(Product.id == item_data.product_id).first()
            if prod:
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
            # Make sure we import Batch if not already imported (wait, it's already imported at the top of the file)
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

    # Apply the total to the PO
    po.total_amount = total
    
    # Financial Transaction generation
    if hasattr(data, 'paid_amount') and data.paid_amount > 0:
        from app.models.moliya import Transaction
        tx = Transaction(
            branch_id=current_user.branch_id if current_user.branch_id else po.warehouse_id, # Fallback branch
            company_id=current_user.company_id,
            type="expense",
            amount=data.paid_amount,
            reference_type="purchase_order",
            reference_id=po.id,
            description=f"Ta'minotchi to'lovi #{po.number}"
        )
        db.add(tx)

    db.flush()
    return po


def receive_purchase_order(db: Session, po_id: int, data, current_user: User) -> PurchaseOrder:
    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    if current_user.role != "super_admin":
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
    from app.models.moliya import Transaction
    from app.models.inventory import StockMovement, StockLevel
    from decimal import Decimal

    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    if current_user.role != "super_admin":
        q = q.filter(PurchaseOrder.company_id == current_user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    if po.status == POStatus.cancelled:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon bekor qilingan")

    # 1. Tarixdagi StockMovement yozuvlarini o'chirish (oldingi holatga qaytarish)
    old_movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "purchase_order",
        StockMovement.reference_id == po.id
    ).all()

    # Har bir harakatni teskari yo'nalishda bekor qilamiz
    for movement in old_movements:
        # Qoldiqni oldingi holatga qaytaramiz
        stock = db.query(StockLevel).filter(
            StockLevel.product_id == movement.product_id,
            StockLevel.warehouse_id == po.warehouse_id
        ).first()

        if stock:
            # Xaridda IN harakati bo'lgan, shuning uchun qoldiqni kamaytamiz
            stock.quantity = movement.qty_before

        # Eski harakatni o'chiramiz
        db.delete(movement)

    # 2. Moliya tranzaksiyasini qaytarish (agar to'lov qilingan bo'lsa)
    # Xarid buyurtmasi uchun to'lov tranzaksiyasini topish
    old_transaction = db.query(Transaction).filter(
        Transaction.reference_type == "purchase_order",
        Transaction.reference_id == po.id,
        Transaction.type == "expense"
    ).first()

    if old_transaction:
        # Eski tranzaksiyani o'chiramiz
        db.delete(old_transaction)

    # 3. Buyurtmani o'chirish
    db.delete(po)
    db.commit()
