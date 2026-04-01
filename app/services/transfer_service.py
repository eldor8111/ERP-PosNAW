from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.inventory import MovementType, StockMovement
from app.models.transfer import StockTransfer, StockTransferItem, TransferStatus
from app.models.warehouse import Warehouse
from app.services.inventory_service import deduct_stock, get_or_create_stock


def generate_transfer_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"TR{today}"
    count = db.query(StockTransfer).filter(StockTransfer.number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}"


def create_transfer(db: Session, data, user_id: int) -> StockTransfer:
    from datetime import datetime
    if data.from_warehouse_id == data.to_warehouse_id:
        raise HTTPException(status_code=400, detail="Manba va maqsad ombor bir xil bo'lmasligi kerak")

    for wh_id in [data.from_warehouse_id, data.to_warehouse_id]:
        wh = db.query(Warehouse).filter(Warehouse.id == wh_id, Warehouse.is_active == True).first()
        if not wh:
            raise HTTPException(status_code=404, detail=f"Ombor ID={wh_id} topilmadi")

    transfer = StockTransfer(
        number=generate_transfer_number(db),
        from_warehouse_id=data.from_warehouse_id,
        to_warehouse_id=data.to_warehouse_id,
        note=data.note,
        created_by=user_id,
        status=TransferStatus.pending,
    )
    db.add(transfer)
    db.flush()

    for item_data in data.items:
        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=item_data.product_id,
            quantity=item_data.quantity,
        )
        db.add(item)

    db.flush()

    # ── Auto-confirm: deduct from source, add to destination immediately ──
    for item in transfer.items:
        from_stock = get_or_create_stock(db, item.product_id, transfer.from_warehouse_id)
        if from_stock.quantity < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Mahsulot ID={item.product_id}: manba omborida yetarli qoldiq yo'q "
                       f"(mavjud: {from_stock.quantity}, kerak: {item.quantity})"
            )
        qty_before_from = from_stock.quantity
        from_stock.quantity -= item.quantity
        db.add(StockMovement(
            product_id=item.product_id,
            type=MovementType.TRANSFER_OUT,
            qty_before=qty_before_from,
            qty_after=from_stock.quantity,
            quantity=item.quantity,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=user_id,
            reason=f"Transfer #{transfer.number} chiqim",
        ))

        to_stock = get_or_create_stock(db, item.product_id, transfer.to_warehouse_id)
        qty_before_to = to_stock.quantity
        to_stock.quantity += item.quantity
        db.add(StockMovement(
            product_id=item.product_id,
            type=MovementType.TRANSFER_IN,
            qty_before=qty_before_to,
            qty_after=to_stock.quantity,
            quantity=item.quantity,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=user_id,
            reason=f"Transfer #{transfer.number} kirim",
        ))

    transfer.status = TransferStatus.received
    transfer.confirmed_by = user_id
    transfer.confirmed_at = datetime.now(timezone.utc)
    db.flush()
    return transfer


def confirm_transfer(db: Session, transfer_id: int, user_id: int) -> StockTransfer:
    transfer = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")
    if transfer.status != TransferStatus.pending:
        raise HTTPException(status_code=400, detail=f"Transfer holati '{transfer.status}' — tasdiqlab bo'lmaydi")

    for item in transfer.items:
        # Deduct from source warehouse
        from_stock = get_or_create_stock(db, item.product_id, transfer.from_warehouse_id)
        if from_stock.quantity < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Mahsulot ID={item.product_id}: manba omborida yetarli qoldiq yo'q "
                       f"(mavjud: {from_stock.quantity}, kerak: {item.quantity})"
            )
        qty_before_from = from_stock.quantity
        from_stock.quantity -= item.quantity
        db.add(StockMovement(
            product_id=item.product_id,
            type=MovementType.TRANSFER_OUT,
            qty_before=qty_before_from,
            qty_after=from_stock.quantity,
            quantity=item.quantity,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=user_id,
            reason=f"Transfer #{transfer.number} chiqim",
        ))

        # Add to destination warehouse
        to_stock = get_or_create_stock(db, item.product_id, transfer.to_warehouse_id)
        qty_before_to = to_stock.quantity
        to_stock.quantity += item.quantity
        db.add(StockMovement(
            product_id=item.product_id,
            type=MovementType.TRANSFER_IN,
            qty_before=qty_before_to,
            qty_after=to_stock.quantity,
            quantity=item.quantity,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=user_id,
            reason=f"Transfer #{transfer.number} kirim",
        ))

    transfer.status = TransferStatus.received
    transfer.confirmed_by = user_id
    transfer.confirmed_at = datetime.now(timezone.utc)
    db.flush()
    return transfer


def delete_transfer(db: Session, transfer_id: int, current_user) -> None:
    """Transfer o'chirish: tarixdagi StockMovement'larni o'chirish va qoldiqlarni qaytarish"""
    from app.models.inventory import StockLevel

    transfer = db.query(StockTransfer).filter(StockTransfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer topilmadi")

    # 1. Tarixdagi StockMovement yozuvlarini o'chirish (oldingi holatga qaytarish)
    old_movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "stock_transfer",
        StockMovement.reference_id == transfer.id
    ).all()

    # Har bir harakatni teskari yo'nalishda bekor qilamiz
    for movement in old_movements:
        # Qoldiqni oldingi holatga qaytaramiz
        if movement.type == MovementType.TRANSFER_OUT:
            # FROM warehouse uchun - qoldiqni qaytaramiz
            stock = db.query(StockLevel).filter(
                StockLevel.product_id == movement.product_id,
                StockLevel.warehouse_id == transfer.from_warehouse_id
            ).first()
            if stock:
                stock.quantity = movement.qty_before
        elif movement.type == MovementType.TRANSFER_IN:
            # TO warehouse uchun - qoldiqni kamaytamiz
            stock = db.query(StockLevel).filter(
                StockLevel.product_id == movement.product_id,
                StockLevel.warehouse_id == transfer.to_warehouse_id
            ).first()
            if stock:
                stock.quantity = movement.qty_before

        # Eski harakatni o'chiramiz
        db.delete(movement)

    # 2. Transfer'ni o'chirish
    db.delete(transfer)
    db.commit()
