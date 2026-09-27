from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.inventory import StockLevel
from app.models.inventory_count import CountStatus, InventoryCount, InventoryCountItem
from app.models.product import Product, ProductConversion
from app.models.warehouse import Warehouse
from app.services.inventory_service import adjust_stock


def generate_count_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"IC{today}"
    count = db.query(InventoryCount).filter(InventoryCount.number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}"


def create_inventory_count(db: Session, data, user_id: int) -> InventoryCount:
    wh = db.query(Warehouse).filter(Warehouse.id == data.warehouse_id, Warehouse.is_active == True).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")

    count = InventoryCount(
        number=generate_count_number(db),
        warehouse_id=data.warehouse_id,
        note=data.note,
        created_by=user_id,
        status=CountStatus.draft,
    )
    db.add(count)
    db.flush()

    # Load ALL active (non-deleted) products; filter by category if partial count
    products_q = db.query(Product).filter(
        Product.is_deleted == False,
        Product.status == "active",
        Product.product_type != "sell",
        Product.company_id == wh.company_id,
    )
    if data.category_ids:
        products_q = products_q.filter(Product.category_id.in_(data.category_ids))
    products = products_q.order_by(Product.name).all()
    product_ids = [p.id for p in products]

    # Variantli mahsulotlarda har bir variant alohida sanaladi
    from app.models.product_variant import ProductVariant
    variants_by_product: dict = {}
    if product_ids:
        for v in db.query(ProductVariant).filter(ProductVariant.product_id.in_(product_ids)).all():
            variants_by_product.setdefault(v.product_id, []).append(v)

    # Build a map of existing stock levels for this warehouse, keyed by (product_id, variant_id)
    stock_map = {
        (s.product_id, s.variant_id): s.quantity
        for s in db.query(StockLevel).filter(StockLevel.warehouse_id == data.warehouse_id).all()
    }

    items_to_insert = []
    for product in products:
        variants = variants_by_product.get(product.id)
        if variants:
            for v in variants:
                items_to_insert.append({
                    "count_id": count.id,
                    "product_id": product.id,
                    "variant_id": v.id,
                    "system_qty": stock_map.get((product.id, v.id), 0),
                    "counted_qty": None,
                    "variance": None,
                })
        else:
            items_to_insert.append({
                "count_id": count.id,
                "product_id": product.id,
                "variant_id": None,
                "system_qty": stock_map.get((product.id, None), 0),
                "counted_qty": None,
                "variance": None,
            })
    if items_to_insert:
        db.execute(InventoryCountItem.__table__.insert(), items_to_insert)

    return count


def start_inventory_count(db: Session, count_id: int) -> InventoryCount:
    count = db.query(InventoryCount).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    if count.status != CountStatus.draft:
        raise HTTPException(status_code=400, detail="Faqat draft holatdagi inventarizatsiyani boshlash mumkin")
    count.status = CountStatus.in_progress
    count.started_at = datetime.now(timezone.utc)
    db.flush()
    return count


def update_count_items(db: Session, count_id: int, items_data: list, user_id: int) -> InventoryCount:
    count = db.query(InventoryCount).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    if count.status not in (CountStatus.draft, CountStatus.in_progress):
        raise HTTPException(status_code=400, detail="Bu holатdagi inventarizatsiyani o'zgartirib bo'lmaydi")

    items_map = {(item.product_id, item.variant_id): item for item in count.items}

    # Block sell products
    product_ids = [item.product_id for item in items_data]
    if product_ids:
        from app.models.product import Product
        sell_product = db.query(Product).filter(
            Product.id.in_(product_ids),
            Product.product_type == 'sell'
        ).first()
        if sell_product:
            raise HTTPException(status_code=400, detail="Tarkibiy (Kalkulyatsiya) mahsulotni revizya qilib bo'lmaydi")

    for item_data in items_data:
        variant_id = getattr(item_data, 'variant_id', None)
        count_item = items_map.get((item_data.product_id, variant_id))
        if not count_item:
            # Add new item if not in list
            system_qty = 0
            stock = db.query(StockLevel).filter(
                StockLevel.product_id == item_data.product_id,
                StockLevel.warehouse_id == count.warehouse_id,
            )
            stock = stock.filter(StockLevel.variant_id == variant_id) if variant_id is not None \
                else stock.filter(StockLevel.variant_id.is_(None))
            stock_row = stock.first()
            if stock_row:
                system_qty = stock_row.quantity
            count_item = InventoryCountItem(
                count_id=count_id,
                product_id=item_data.product_id,
                variant_id=variant_id,
                system_qty=system_qty,
            )
            db.add(count_item)
            db.flush()
        count_item.counted_qty = item_data.counted_qty
        count_item.variance = item_data.counted_qty - count_item.system_qty
        count_item.variance_reason = getattr(item_data, 'variance_reason', None)

    db.flush()
    return count


def finalize_inventory_count(db: Session, count_id: int, user_id: int) -> InventoryCount:
    from decimal import Decimal
    from app.models.inventory import MovementType, StockMovement

    count = db.query(InventoryCount).filter(InventoryCount.id == count_id).first()
    if not count:
        raise HTTPException(status_code=404, detail="Inventarizatsiya topilmadi")
    if count.status != CountStatus.in_progress:
        raise HTTPException(status_code=400, detail="Faqat jarayondagi inventarizatsiyani yakunlash mumkin")

    for item in count.items:
        if item.counted_qty is None:
            continue

        prod = db.query(Product).filter(Product.id == item.product_id).first()
        if prod and (prod.product_type == "sell" or db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == item.product_id
        ).first()):
            continue  # Tarkibiy mahsulot qoldig'i reviziya qilinmaydi

        # Find the EXACT StockLevel for this product + variant + warehouse,
        # bloklab olamiz — parallel sotuv/prixod bilan to'qnashmasligi uchun
        stock_q = db.query(StockLevel).filter(
            StockLevel.product_id == item.product_id,
            StockLevel.warehouse_id == count.warehouse_id,
        )
        stock_q = stock_q.filter(StockLevel.variant_id == item.variant_id) if item.variant_id is not None \
            else stock_q.filter(StockLevel.variant_id.is_(None))
        stock = stock_q.with_for_update().first()
        if stock is None:
            # No record yet for this warehouse — create one starting at 0
            stock = StockLevel(
                product_id=item.product_id,
                variant_id=item.variant_id,
                warehouse_id=count.warehouse_id,
                quantity=Decimal("0"),
            )
            db.add(stock)
            db.flush()

        qty_before = stock.quantity
        diff = item.counted_qty - qty_before
        stock.quantity = item.counted_qty

        # Record the movement with the real previous balance
        movement = StockMovement(
            product_id=item.product_id,
            variant_id=item.variant_id,
            type=MovementType.ADJUST,
            qty_before=qty_before,
            qty_after=item.counted_qty,
            quantity=abs(diff),
            user_id=user_id,
            reference_type="revision",
            reference_id=count.id,
            reason=f"Revizya #{count.number}",
        )
        db.add(movement)
        db.flush()

    count.status = CountStatus.completed
    count.finished_at = datetime.now(timezone.utc)
    db.flush()
    return count

