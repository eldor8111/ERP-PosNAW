from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.bom import BOM, BOMItem
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.production_order import ProductionOrder, ProductionOrderCost, ProductionOrderStatus
from app.models.warehouse import Warehouse
from app.services import supplier_ledger as ledger
from app.services.inventory_service import deduct_stock, receive_stock, get_or_create_stock, _deduct_batches_fifo


def _cost_in_uzs(db: Session, product: Product, company_id: int) -> Decimal:
    """Xom ashyo tannarxini so'mga o'giradi (tannarx valyutada saqlanishi mumkin)."""
    if not product or not product.cost_price:
        return Decimal("0")
    cost = Decimal(str(product.cost_price))
    cur = (product.cost_currency or "UZS").strip().upper() or "UZS"
    return cost if cur == "UZS" else cost * ledger.currency_rate(db, company_id, cur)


def generate_production_number(db: Session) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"MO{today}"
    count = db.query(ProductionOrder).filter(ProductionOrder.number.like(f"{prefix}%")).count()
    return f"{prefix}{count + 1:04d}"


def _validate_warehouse(db: Session, warehouse_id: int, company_id: int) -> Warehouse:
    wh = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id, Warehouse.is_active == True
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail=f"Ombor ID={warehouse_id} topilmadi")
    return wh


def calculate_shortages(db: Session, bom: BOM, planned_quantity: Decimal, warehouse_id: int) -> List[dict]:
    """MRP'ning soddalashtirilgan birinchi versiyasi: BOM asosida kerakli
    xom ashyo miqdorini hisoblab, ombordagi qoldiq bilan solishtiradi.
    Faqat ma'lumot uchun — buyurtma yaratishni bloklamaydi."""
    shortages = []
    for item in bom.items:
        required = item.quantity_per_unit * planned_quantity
        stock = get_or_create_stock(db, item.component_product_id, warehouse_id, item.component_variant_id)
        available = stock.quantity
        if available < required:
            shortages.append({
                "component_product_id": item.component_product_id,
                "component_product_name": item.component_product.name,
                "required_quantity": required,
                "available_quantity": available,
                "shortage": required - available,
            })
    return shortages


def create_production_order(db: Session, data, user_id: int, company_id: int) -> ProductionOrder:
    bom = db.query(BOM).filter(BOM.id == data.bom_id, BOM.company_id == company_id, BOM.is_active == True).first()
    if not bom:
        raise HTTPException(status_code=404, detail="Retseptura (BOM) topilmadi yoki faol emas")
    if not bom.items:
        raise HTTPException(status_code=400, detail="Bu retsepturada xom ashyo tarkibi kiritilmagan")

    if data.warehouse_id == data.target_warehouse_id:
        raise HTTPException(status_code=400, detail="Xom ashyo va tayyor mahsulot ombori bir xil bo'lmasligi kerak")

    _validate_warehouse(db, data.warehouse_id, company_id)
    _validate_warehouse(db, data.target_warehouse_id, company_id)

    if data.planned_quantity <= 0:
        raise HTTPException(status_code=400, detail="Rejalashtirilgan miqdor 0 dan katta bo'lishi kerak")

    order = ProductionOrder(
        number=generate_production_number(db),
        bom_id=bom.id,
        product_id=bom.product_id,
        variant_id=bom.variant_id,
        planned_quantity=data.planned_quantity,
        warehouse_id=data.warehouse_id,
        target_warehouse_id=data.target_warehouse_id,
        status=ProductionOrderStatus.draft,
        note=data.note,
        created_by=user_id,
        company_id=company_id,
    )
    db.add(order)
    db.flush()
    return order


def start_production_order(db: Session, order_id: int, company_id: int) -> ProductionOrder:
    order = db.query(ProductionOrder).filter(
        ProductionOrder.id == order_id, ProductionOrder.company_id == company_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Ishlab chiqarish buyurtmasi topilmadi")
    if order.status != ProductionOrderStatus.draft:
        raise HTTPException(status_code=400, detail="Faqat qoralama (draft) buyurtmani boshlash mumkin")

    order.status = ProductionOrderStatus.in_progress
    order.started_at = datetime.now(timezone.utc)
    db.flush()
    return order


def complete_production_order(db: Session, order_id: int, user_id: int, company_id: int, data) -> ProductionOrder:
    """Xom ashyoni BOM asosida hisobdan chiqaradi, tannarxni (xom ashyo real
    narxi + qo'lda kiritilgan xarajatlar) hisoblab, tayyor mahsulotni shu
    tannarx bilan yangi partiya (Batch) sifatida kiritadi. Hammasi bitta
    tranzaksiyada — birortasi xato bersa, hech narsa commit bo'lmaydi."""
    order = db.query(ProductionOrder).filter(
        ProductionOrder.id == order_id, ProductionOrder.company_id == company_id
    ).with_for_update().first()
    if not order:
        raise HTTPException(status_code=404, detail="Ishlab chiqarish buyurtmasi topilmadi")
    if order.status != ProductionOrderStatus.in_progress:
        raise HTTPException(status_code=400, detail="Faqat jarayondagi buyurtmani yakunlash mumkin")

    if data.produced_quantity <= 0:
        raise HTTPException(status_code=400, detail="Ishlab chiqarilgan miqdor 0 dan katta bo'lishi kerak")

    bom = db.query(BOM).filter(BOM.id == order.bom_id).first()

    raw_material_cost = Decimal("0")
    for item in bom.items:
        required = item.quantity_per_unit * data.produced_quantity
        component = db.query(Product).filter(Product.id == item.component_product_id).first()

        deduct_stock(
            db, item.component_product_id, required, user_id,
            reason=f"Ishlab chiqarish #{order.number} uchun xom ashyo",
            reference_type="production_order",
            reference_id=order.id,
            warehouse_id=order.warehouse_id,
            variant_id=item.component_variant_id,
        )
        # Partiya (lot/FEFO) qoldiqlarini ham kamaytiramiz. strict=False: narxsiz
        # kirim qilingan xom ashyoning partiyasi bo'lmaydi — asosiy tekshiruv
        # yuqoridagi deduct_stock (StockLevel) orqali allaqachon o'tdi
        _deduct_batches_fifo(
            db, item.component_product_id, required, order.warehouse_id, company_id,
            variant_id=item.component_variant_id, strict=False,
        )

        raw_material_cost += _cost_in_uzs(db, component, company_id) * required

    extra_cost = Decimal("0")
    for cost_in in data.costs:
        cost_row = ProductionOrderCost(
            production_order_id=order.id,
            cost_type=cost_in.cost_type,
            amount=cost_in.amount,
            note=cost_in.note,
        )
        db.add(cost_row)
        extra_cost += cost_in.amount

    total_cost = raw_material_cost + extra_cost
    unit_cost = (total_cost / data.produced_quantity) if data.produced_quantity else Decimal("0")

    receive_stock(
        db, order.product_id, data.produced_quantity, user_id,
        reason=f"Ishlab chiqarish #{order.number} — tayyor mahsulot",
        reference_type="production_order",
        reference_id=order.id,
        warehouse_id=order.target_warehouse_id,
        purchase_price=unit_cost,
        company_id=company_id,
        variant_id=order.variant_id,
        production_order_id=order.id,
    )

    # Tayyor mahsulot tannarxi — xariddagi kabi oxirgi kirim narxi
    # (mahsulot tannarx valyutasida)
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if product and unit_cost > 0:
        cur = (product.cost_currency or "UZS").strip().upper() or "UZS"
        product.cost_price = (
            round(unit_cost, 4) if cur == "UZS"
            else round(unit_cost / ledger.currency_rate(db, company_id, cur), 4)
        )

    order.produced_quantity = data.produced_quantity
    order.defect_quantity = data.defect_quantity
    order.unit_cost = unit_cost
    order.total_cost = total_cost
    order.status = ProductionOrderStatus.completed
    order.completed_at = datetime.now(timezone.utc)
    db.flush()
    return order


def cancel_production_order(db: Session, order_id: int, company_id: int) -> ProductionOrder:
    """draft yoki in_progress'dan bekor qilish — xom ashyo hali hisobdan
    chiqmagani uchun (faqat completed'da chiqadi) qoldiqni qaytarish shart
    emas."""
    order = db.query(ProductionOrder).filter(
        ProductionOrder.id == order_id, ProductionOrder.company_id == company_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Ishlab chiqarish buyurtmasi topilmadi")
    if order.status not in (ProductionOrderStatus.draft, ProductionOrderStatus.in_progress):
        raise HTTPException(status_code=400, detail="Yakunlangan yoki bekor qilingan buyurtmani qayta bekor qilib bo'lmaydi")

    order.status = ProductionOrderStatus.cancelled
    db.flush()
    return order
