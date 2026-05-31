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

    from app.models.product import Product, ProductConversion
    for item_data in data.items:
        prod = db.query(Product).filter(Product.id == item_data.product_id).first()
        if not prod:
            raise HTTPException(status_code=404, detail=f"Mahsulot ID={item_data.product_id} topilmadi")

        # Maqsad mahsulotni tekshirish (agar ko'rsatilgan bo'lsa)
        target_product_id = getattr(item_data, 'target_product_id', None) or None
        if target_product_id:
            target_prod = db.query(Product).filter(Product.id == target_product_id).first()
            if not target_prod:
                raise HTTPException(status_code=404, detail=f"Maqsad mahsulot ID={target_product_id} topilmadi")

        item = StockTransferItem(
            transfer_id=transfer.id,
            product_id=item_data.product_id,
            target_product_id=target_product_id,
            quantity=item_data.quantity,
        )
        db.add(item)

    db.flush()

    # ── Auto-confirm: deduct from source, add to destination ──
    from app.models.product import Product, ProductConversion
    for item in transfer.items:
        prod = db.query(Product).filter(Product.id == item.product_id).first()

        # Tarkibiy (sell) mahsulot bo'lsa — manba (raw material) mahsulotidan yechish
        conversion = db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == item.product_id
        ).first()

        if conversion:
            # Masalan: 5 kg Dumba -> 5 * ratio kg Butun qo'ydan yechiladi
            src_product_id = conversion.source_product_id
            src_qty = float(item.quantity) * float(conversion.ratio)
        else:
            src_product_id = item.product_id
            src_qty = float(item.quantity)

        # Manba ombordan chiqim
        from_stock = get_or_create_stock(db, src_product_id, transfer.from_warehouse_id)
        if from_stock.quantity < src_qty:
            prod_name = prod.name if prod else f"ID={item.product_id}"
            raise HTTPException(
                status_code=400,
                detail=f"'{prod_name}': manba omborida yetarli qoldiq yo'q "
                       f"(mavjud: {float(from_stock.quantity):.3f}, kerak: {src_qty:.3f})"
            )
        qty_before_from = from_stock.quantity
        from_stock.quantity = float(from_stock.quantity) - src_qty
        db.add(StockMovement(
            product_id=src_product_id,
            type=MovementType.TRANSFER_OUT,
            qty_before=qty_before_from,
            qty_after=from_stock.quantity,
            quantity=src_qty,
            reference_type="stock_transfer",
            reference_id=transfer.id,
            user_id=user_id,
            reason=f"Transfer #{transfer.number} chiqim",
        ))

        # Maqsad ombor: target_product_id bo'lsa uni, aks holda source mahsulotni ishlatish
        dest_product_id = item.target_product_id or item.product_id
        to_stock = get_or_create_stock(db, dest_product_id, transfer.to_warehouse_id)
        qty_before_to = to_stock.quantity
        to_stock.quantity = float(to_stock.quantity) + float(item.quantity)
        db.add(StockMovement(
            product_id=dest_product_id,
            type=MovementType.TRANSFER_IN,
            qty_before=qty_before_to,
            qty_after=to_stock.quantity,
            quantity=float(item.quantity),
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

        # Add to destination warehouse (target_product_id bo'lsa uni ishlatish)
        dest_product_id = item.target_product_id or item.product_id
        to_stock = get_or_create_stock(db, dest_product_id, transfer.to_warehouse_id)
        qty_before_to = to_stock.quantity
        to_stock.quantity += item.quantity
        db.add(StockMovement(
            product_id=dest_product_id,
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

    # Transfer itemlarini id bo'yicha map qilish (target_product_id uchun)
    item_map = {item.product_id: item for item in transfer.items}

    # 1. Tarixdagi StockMovement yozuvlarini o'chirish (oldingi holatga qaytarish)
    old_movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "stock_transfer",
        StockMovement.reference_id == transfer.id
    ).all()

    # Har bir harakatni teskari yo'nalishda bekor qilamiz
    for movement in old_movements:
        if movement.type == MovementType.TRANSFER_OUT:
            # FROM warehouse uchun — manba mahsulot qoldiqini qaytaramiz
            stock = db.query(StockLevel).filter(
                StockLevel.product_id == movement.product_id,
                StockLevel.warehouse_id == transfer.from_warehouse_id
            ).first()
            if stock:
                stock.quantity = movement.qty_before
        elif movement.type == MovementType.TRANSFER_IN:
            # TO warehouse uchun — maqsad mahsulot qoldiqini kamaytamiz
            # (movement.product_id allaqachon dest_product_id bo'lib saqlanган)
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
