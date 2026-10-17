from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.bom import BOM, BOMItem
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.production_order import ProductionOrder, ProductionOrderCost, ProductionOrderStatus
from app.models.warehouse import Warehouse
from app.services import supplier_ledger as ledger
from app.services.document_numbers import next_document_number
from app.services.inventory_service import deduct_stock, receive_stock, get_or_create_stock, _deduct_batches_fifo


def _cost_in_uzs(db: Session, product: Product, company_id: int) -> Decimal:
    """Xom ashyo tannarxini so'mga o'giradi (tannarx valyutada saqlanishi mumkin)."""
    if not product or not product.cost_price:
        return Decimal("0")
    cost = Decimal(str(product.cost_price))
    cur = (product.cost_currency or "UZS").strip().upper() or "UZS"
    return cost if cur == "UZS" else cost * ledger.currency_rate(db, company_id, cur)


# BOM da tayyor mahsulot/komponent bo'la olmaydigan turlar (xizmat va virtual mahsulot)
_BOM_BAD_TYPES = ("service", "sell")


def validate_bom_refs(db: Session, company_id: int, product_id: int, variant_id, items) -> None:
    """BOM yaratish/tahrirlashda tayyor mahsulot, variant va komponentlar shu
    korxonaniki, o'chirilmagan va mos turdagi ekanini tekshiradi (STOCK-16)."""
    product = db.query(Product).filter(
        Product.id == product_id, Product.company_id == company_id,
        Product.is_deleted == False, Product.product_type.notin_(_BOM_BAD_TYPES),
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Tayyor mahsulot topilmadi")
    if variant_id is not None:
        ok = db.query(ProductVariant.id).filter(
            ProductVariant.id == variant_id, ProductVariant.product_id == product_id
        ).first()
        if not ok:
            raise HTTPException(status_code=400, detail="Variant mahsulotga tegishli emas")

    seen = set()
    for item in items:
        cid = item.component_product_id
        comp = db.query(Product.id).filter(
            Product.id == cid, Product.company_id == company_id,
            Product.is_deleted == False, Product.product_type.notin_(_BOM_BAD_TYPES),
        ).first()
        if not comp:
            raise HTTPException(status_code=404, detail=f"Xom ashyo ID={cid} topilmadi")
        if cid == product_id:
            raise HTTPException(status_code=400, detail="Mahsulot o'zining komponenti bo'la olmaydi")
        if item.component_variant_id is not None:
            ok = db.query(ProductVariant.id).filter(
                ProductVariant.id == item.component_variant_id, ProductVariant.product_id == cid
            ).first()
            if not ok:
                raise HTTPException(status_code=400, detail="Komponent varianti xom ashyoga tegishli emas")
        if item.quantity_per_unit is None or item.quantity_per_unit <= 0:
            raise HTTPException(status_code=400, detail="Sarf me'yori 0 dan katta bo'lishi kerak")
        key = (cid, item.component_variant_id)
        if key in seen:
            raise HTTPException(status_code=400, detail="Komponent takrorlangan")
        seen.add(key)


def generate_production_number(db: Session, company_id: int, branch_id=None) -> str:
    """Ishlab chiqarish raqami (T1.14): `MO{YYYYMMDD}-{korxona}-{filial}-{NNNN}`, atomar hisoblagich bilan."""
    return next_document_number(db, company_id=company_id, branch_id=branch_id, doc_type="MO")


def _validate_warehouse(db: Session, warehouse_id: int, company_id: int) -> Warehouse:
    wh = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id, Warehouse.is_active == True
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail=f"Ombor ID={warehouse_id} topilmadi")
    return wh


def _assert_warehouse_branch_access(db: Session, wh: Warehouse, user_id) -> None:
    """T1.1: filialga biriktirilgan xodim boshqa filial omboridan ishlab chiqarishni boshlay olmaydi (403).
    Ruxsat doirasi — joriy BranchContext (`db.info["branch_ctx"]`, shu foydalanuvchi uchun), bo'lmasa
    foydalanuvchi uchun qurilgan kontekst. Cheklanmagan (admin/director) yoki filialsiz ombor — o'tadi."""
    if user_id is None or wh.branch_id is None:
        return
    from app.core.branch_context import BRANCH_FORBIDDEN, BranchContext, build_branch_context
    from app.models.user import User

    ctx = db.info.get("branch_ctx") if hasattr(db, "info") else None
    if not (isinstance(ctx, BranchContext) and ctx.user_id == user_id):
        user = db.get(User, user_id)
        if user is None:
            return
        ctx = build_branch_context(db, user)
    ids = ctx.scope_ids()
    if ids is not None and wh.branch_id not in ids:
        raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)


def calculate_shortages(db: Session, bom: BOM, planned_quantity: Decimal, warehouse_id: int) -> List[dict]:
    """MRP'ning soddalashtirilgan birinchi versiyasi: BOM asosida kerakli
    xom ashyo miqdorini hisoblab, ombordagi qoldiq bilan solishtiradi.
    Faqat ma'lumot uchun — buyurtma yaratishni bloklamaydi."""
    # Faqat o'qish: qulf (FOR UPDATE) olinmaydi va StockLevel yaratilmaydi (GET so'rovida yozish yo'q).
    # Barcha komponentlar qoldig'i bitta so'rov bilan olinadi; qator yo'q bo'lsa qoldiq 0.
    pids = {item.component_product_id for item in bom.items}
    on_hand: dict = {}
    if pids:
        for pid, vid, qty in db.query(
            StockLevel.product_id, StockLevel.variant_id, StockLevel.quantity
        ).filter(
            StockLevel.product_id.in_(pids), StockLevel.warehouse_id == warehouse_id
        ).all():
            on_hand[(pid, vid)] = on_hand.get((pid, vid), Decimal("0")) + Decimal(str(qty or 0))

    shortages = []
    for item in bom.items:
        required = item.quantity_per_unit * planned_quantity
        available = on_hand.get((item.component_product_id, item.component_variant_id), Decimal("0"))
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

    # Eski ifloslangan BOM lardan himoya: BOM mahsuloti shu korxonaniki bo'lishi shart
    own_product = db.query(Product.id).filter(
        Product.id == bom.product_id, Product.company_id == company_id
    ).first()
    if not own_product:
        raise HTTPException(status_code=400, detail="Retseptura mahsuloti korxonaga tegishli emas")

    if data.warehouse_id == data.target_warehouse_id:
        raise HTTPException(status_code=400, detail="Xom ashyo va tayyor mahsulot ombori bir xil bo'lmasligi kerak")

    src_wh = _validate_warehouse(db, data.warehouse_id, company_id)
    dst_wh = _validate_warehouse(db, data.target_warehouse_id, company_id)
    _assert_warehouse_branch_access(db, src_wh, user_id)  # T1.1: ombor filiali xodim doirasida bo'lsin
    _assert_warehouse_branch_access(db, dst_wh, user_id)

    if data.planned_quantity <= 0:
        raise HTTPException(status_code=400, detail="Rejalashtirilgan miqdor 0 dan katta bo'lishi kerak")

    order = ProductionOrder(
        number=generate_production_number(db, company_id, src_wh.branch_id),
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

    bom = db.query(BOM).filter(BOM.id == order.bom_id, BOM.company_id == company_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="Retseptura (BOM) topilmadi")

    # ── Tekshiruvlar (deduct_stock dan OLDIN — xato bo'lsa hech narsa o'zgarmaydi) ──
    product = db.query(Product).filter(
        Product.id == order.product_id, Product.company_id == company_id
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Tayyor mahsulot topilmadi")
    _validate_warehouse(db, order.warehouse_id, company_id)
    _validate_warehouse(db, order.target_warehouse_id, company_id)

    components = {}
    for item in bom.items:
        if item.quantity_per_unit is None or item.quantity_per_unit <= 0:
            raise HTTPException(status_code=400, detail="Retseptura sarf me'yori noto'g'ri (<=0). Retseptura tuzatilsin")
        component = db.query(Product).filter(
            Product.id == item.component_product_id, Product.company_id == company_id
        ).first()
        if not component:
            raise HTTPException(
                status_code=400,
                detail=f"Retseptura komponenti ID={item.component_product_id} korxonaga tegishli emas. Retseptura tuzatilsin",
            )
        components[item.id] = component

    raw_material_cost = Decimal("0")
    for item in bom.items:
        required = item.quantity_per_unit * data.produced_quantity
        component = components[item.id]

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
        taken = _deduct_batches_fifo(
            db, item.component_product_id, required, order.warehouse_id, company_id,
            variant_id=item.component_variant_id, strict=False,
        )

        # Tannarx — haqiqiy yechilgan partiyalar narxi (Batch.purchase_price, UZS) yig'indisi.
        # Partiya topilmagan (narxsiz kirim) yoki narxi 0 bo'lgan qism uchun zaxira:
        # mahsulotning joriy tannarxi (_cost_in_uzs).
        fallback_price = _cost_in_uzs(db, component, company_id)
        covered = Decimal("0")
        for batch, take in taken:
            take = Decimal(str(take))
            price = Decimal(str(batch.purchase_price or 0))
            raw_material_cost += take * (price if price > 0 else fallback_price)
            covered += take
        if required > covered:
            raw_material_cost += (required - covered) * fallback_price

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
    if unit_cost > 0:
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
