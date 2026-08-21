import json
import random
import string
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.inventory import StockLevel
from app.models.product import Product, ProductConversion, ProductStatus
from app.models.user import User, UserRole
from app.schemas.product import ProductCreate, ProductListOut, ProductOut, ProductStatusUpdate, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)

from app.utils.product_filters import name_filter as _name_filter  # noqa: E402


def _attach_stock(product: Product, db: Session = None, warehouse_id: int = None) -> ProductOut:
    out = ProductOut.model_validate(product)
    if product.category:
        out.category_name = product.category.name

    out.stock_quantity = Decimal("0")
    if db:
        from app.models.inventory import StockLevel
        from sqlalchemy import func
        q = db.query(func.coalesce(func.sum(StockLevel.quantity), 0)).filter(StockLevel.product_id == product.id)
        if warehouse_id:
            q = q.filter(StockLevel.warehouse_id == warehouse_id)
        total_qty = q.scalar()
        if total_qty is not None:
            out.stock_quantity = Decimal(str(total_qty))
    elif product.stock_level:
        out.stock_quantity = product.stock_level.quantity

    
    if product.product_type == 'parent' and db:
        from app.models.product_variant import ProductVariant
        from app.schemas.product_variant import ProductVariantOut
        children = db.query(ProductVariant).filter(ProductVariant.product_id == product.id).options(joinedload(ProductVariant.attribute_values).joinedload(VariantAttributeValue.attribute_value).joinedload(AttributeValue.attribute)).all()
        v_out = []
        for c in children:
            color = next((val.attribute_value.value for val in c.attribute_values if val.attribute_value.attribute.name in ("Rang", "Color")), None)
            size = next((val.attribute_value.value for val in c.attribute_values if val.attribute_value.attribute.name in ("O'lcham", "Size")), None)
            v_out.append(ProductVariantOut(
                id=c.id,
                product_id=product.id,
                name=c.name,
                sku=c.sku,
                barcode=c.barcode,
                color=color,
                size=size,
                cost_price=c.cost_price,
                sale_price=c.sale_price,
                wholesale_price=c.wholesale_price,
            ))
        out.variants = v_out

    if product.conversion:
        from app.schemas.product import ProductConversionOut
        src = product.conversion.source_product
        out.conversion = ProductConversionOut(
            id=product.conversion.id,
            sell_product_id=product.conversion.sell_product_id,
            source_product_id=product.conversion.source_product_id,
            source_product_name=src.name if src else None,
            ratio=product.conversion.ratio,
        )
        out.product_type = "sell"
        # Mijoz talabiga ko'ra virtual mahsulot qoldig'i har doim 0 bo'lib turishi kerak
        out.stock_quantity = Decimal("0")

    # Tarkibiy qismlarni (sell_conversions) ulash
    if getattr(product, 'sell_conversions', None):
        from app.schemas.product import ProductConversionReverseOut
        out.sell_conversions = []
        for conv in product.sell_conversions:
            sell_p = conv.sell_product
            if sell_p and not sell_p.is_deleted:
                out.sell_conversions.append(ProductConversionReverseOut(
                    id=conv.id,
                    sell_product_id=conv.sell_product_id,
                    sell_product_name=sell_p.name,
                    ratio=conv.ratio,
                ))
    return out


@router.get("/{product_id}/variants")
def get_product_variants(
    product_id: int,
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parent mahsulotning barcha variantlarini stock bilan qaytaradi."""
    from app.models.product_variant import ProductVariant
    from app.models.inventory import StockLevel
    from app.models.attribute import AttributeValue, VariantAttributeValue, Attribute
    from sqlalchemy.orm import joinedload

    product = db.query(Product).filter(
        Product.id == product_id,
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,
    ).first()
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    children = db.query(ProductVariant).filter(
        ProductVariant.product_id == product_id
    ).options(
        joinedload(ProductVariant.attribute_values)
            .joinedload(VariantAttributeValue.attribute_value)
            .joinedload(AttributeValue.attribute)
    ).all()

    result = []
    for c in children:
        color = next((val.attribute_value.value for val in c.attribute_values
                      if val.attribute_value.attribute.name in ("Rang", "Color")), None)
        size = next((val.attribute_value.value for val in c.attribute_values
                     if val.attribute_value.attribute.name in ("O'lcham", "Size")), None)

        sq = db.query(StockLevel).filter(
            StockLevel.variant_id == c.id,
            StockLevel.product_id == product_id,
        )
        if warehouse_id:
            sq = sq.filter(StockLevel.warehouse_id == warehouse_id)
        stock_qty = sum(float(s.quantity) for s in sq.all())

        result.append({
            "id": c.id,
            "product_id": product_id,
            "name": c.name,
            "sku": c.sku,
            "barcode": c.barcode,
            "color": color,
            "size": size,
            "cost_price": float(c.cost_price or 0),
            "sale_price": float(c.sale_price or product.sale_price or 0),
            "wholesale_price": float(c.wholesale_price or product.wholesale_price or 0),
            "stock_quantity": stock_qty,
            "unit": product.unit or "dona",
        })
    return result


@router.get("/", response_model=List[ProductListOut])
def list_products(
        search: Optional[str] = Query(None, description="Nomi yoki SKU bo'yicha qidiruv"),
        category_id: Optional[int] = Query(None),
        status: Optional[ProductStatus] = Query(None),
        warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filter"),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=20000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    from app.models.inventory import StockLevel
    from app.models.warehouse import Warehouse
    from app.schemas.product import WarehouseStockOut

    from sqlalchemy.orm import joinedload

    q = db.query(Product).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    # conversion va sell_conversions ni eager load qilamiz (lazy loading xatosi oldini olish)
    q = q.options(
        joinedload(Product.conversion).joinedload(ProductConversion.source_product),
        joinedload(Product.sell_conversions).joinedload(ProductConversion.sell_product),
        joinedload(Product.variants),
        joinedload(Product.category),
    )

    if search:
        q = q.filter(_name_filter(search))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if status:
        q = q.filter(Product.status == status)
    if warehouse_id:
        # Only products that have stock in this warehouse
        q = q.join(StockLevel, (StockLevel.product_id == Product.id) & (StockLevel.warehouse_id == warehouse_id))

    products = q.order_by(Product.name).offset(skip).limit(limit).all()

    # Determine branch warehouse IDs for non-admin users
    ADMIN_ROLES_P = (UserRole.admin, UserRole.director)
    branch_wh_set = None
    if current_user.role not in ADMIN_ROLES_P and current_user.branch_id:
        branch_wh_set = {
            wh.id for wh in db.query(Warehouse.id).filter(
                Warehouse.branch_id == current_user.branch_id
            ).all()
        }

    # Preload warehouse names (only current company's warehouses)
    wh_q = db.query(Warehouse)
    wh_q = wh_q.filter(Warehouse.company_id == current_user.company_id)
    warehouses = {w.id: w.name for w in wh_q.all()}

    # N+1 muammosini oldini olish: barcha stock levellarni BITTA so'rovda olamiz
    from collections import defaultdict
    product_ids = [p.id for p in products]

    # Virtual mahsulotlarning asosiy mahsulot (source_product) IDlarini qo'shamiz
    source_ids = set()
    for p in products:
        if getattr(p, "product_type", "stock") == "sell" and getattr(p, "conversion", None):
            source_ids.add(p.conversion.source_product_id)

    all_needed_ids = set(product_ids) | source_ids

    all_stock_rows = (
        db.query(StockLevel)
        .filter(StockLevel.product_id.in_(all_needed_ids))
        .all()
    ) if all_needed_ids else []

    stock_by_product: dict = defaultdict(list)
    for s in all_stock_rows:
        stock_by_product[s.product_id].append(s)

    result = []
    for p in products:
        item = ProductListOut.model_validate(p)

        all_stocks = stock_by_product[p.id]  # bazaga murojaat yo'q, xotiradan olamiz

        # Filter stocks to branch warehouses for non-admins
        visible_stocks = all_stocks
        if branch_wh_set is not None:
            visible_stocks = [s for s in all_stocks if s.warehouse_id in branch_wh_set]  # type: ignore[operator]

        item.warehouse_stocks = [
            WarehouseStockOut(
                warehouse_id=s.warehouse_id,
                warehouse_name=warehouses.get(s.warehouse_id, f"Ombor#{s.warehouse_id}"),
                quantity=s.quantity,
            )
            for s in visible_stocks if s.warehouse_id is not None
        ]

        # stock_quantity: if warehouse_id filter active → show that warehouse's qty, else sum visible
        if warehouse_id:
            wh_stock = next((s for s in all_stocks if s.warehouse_id == warehouse_id), None)
            item.stock_quantity = wh_stock.quantity if wh_stock else Decimal("0")
        else:
            item.stock_quantity = sum((s.quantity for s in visible_stocks), Decimal("0"))

        # conversion (sell mahsulot → asosiy mahsulot)
        if p.conversion:
            from app.schemas.product import ProductConversionOut
            src = p.conversion.source_product
            item.conversion = ProductConversionOut(
                id=p.conversion.id,
                sell_product_id=p.conversion.sell_product_id,
                source_product_id=p.conversion.source_product_id,
                source_product_name=src.name if src else None,
                ratio=p.conversion.ratio,
            )
            item.product_type = "sell"

            # Mijoz talabiga ko'ra virtual mahsulot qoldig'i har doim 0 bo'lib turishi kerak
            item.stock_quantity = Decimal("0")
            item.warehouse_stocks = []

        # sell_conversions (asosiy mahsulot → uning tarkibiy qismlari)
        if getattr(p, 'sell_conversions', None):
            from app.schemas.product import ProductConversionReverseOut
            item.sell_conversions = []
            for conv in p.sell_conversions:
                sell_p = conv.sell_product
                if sell_p and not sell_p.is_deleted:
                    item.sell_conversions.append(ProductConversionReverseOut(
                        id=conv.id,
                        sell_product_id=conv.sell_product_id,
                        sell_product_name=sell_p.name,
                        ratio=conv.ratio,
                    ))

        result.append(item)
    return result


@router.get("/barcode/{barcode}", response_model=ProductOut)
def get_by_barcode(
        barcode: str,
        warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filter (ixtiyoriy)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    base_filter = [
        Product.is_deleted == False,
        Product.status == ProductStatus.active,
        Product.company_id == current_user.company_id,
    ]
    # Asosiy barcode bo'yicha qidirish
    product = db.query(Product).filter(*base_filter, Product.barcode == barcode).first()
    # Topilmasa extra_barcodes JSON ichida qidirish (LIKE tekshiruvi)
    if not product:
        product = (
            db.query(Product)
            .filter(*base_filter, Product.extra_barcodes.ilike(f'"%{barcode}"'))
            .first()
        )
    # Topilmasa SKU bo'yicha qidirish (TM-A tarozi PLU kodi)
    if not product:
        product = db.query(Product).filter(*base_filter, Product.sku == barcode).first()
    # Topilmasa SKU leading zeros olib qidirish (masalan '00001' => '1' yoki aksi)
    if not product:
        stripped = barcode.lstrip('0')
        if stripped:
            product = db.query(Product).filter(*base_filter, Product.sku == stripped).first()
    # Topilmasa SKU ning oxirgi N raqami bilan qidirish
    # (TM-A tarozi faqat 5 ta raqamni barcodedan yuboradi, SKU esa ko'proq bo'lishi mumkin)
    if not product:
        from sqlalchemy import func
        stripped_code = barcode.lstrip('0') or barcode
        products_found = db.query(Product).filter(
            *base_filter,
            Product.sku.isnot(None),
            Product.sku != ''
        ).all()
        for p in products_found:
            if p.sku:
                sku_digits = ''.join(filter(str.isdigit, p.sku))
                if sku_digits.endswith(stripped_code) or sku_digits.endswith(barcode):
                    product = p
                    break
    # Topilmasa ID bo'yicha qidirish (tarozi PLU = mahsulot ID)
    if not product:
        try:
            pid = int(barcode.lstrip('0') or '0')
            if pid > 0:
                product = db.query(Product).filter(*base_filter, Product.id == pid).first()
        except ValueError:
            pass

    if not product:
        raise HTTPException(status_code=404, detail=f"Barcode '{barcode}' bo'yicha mahsulot topilmadi")

    return _attach_stock(product, db=db, warehouse_id=warehouse_id)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
        product_id: int,
        warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filter (ixtiyoriy)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    q = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    q = q.options(
        joinedload(Product.conversion).joinedload(ProductConversion.source_product).joinedload(Product.stock_level),
        joinedload(Product.sell_conversions).joinedload(ProductConversion.sell_product),
        joinedload(Product.variants),
        joinedload(Product.category),
    )
    product = q.first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return _attach_stock(product, db=db, warehouse_id=warehouse_id)


def _generate_sku(db: Session) -> str:
    for _ in range(20):
        sku = "SKU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        q = db.query(Product).filter(Product.sku == sku)
        if q.first():
            continue
        return sku
    return "SKU-" + "".join(random.choices(string.digits, k=8))


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
        data: ProductCreate,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    # Extract non-model fields before dump
    initial_stock = data.initial_stock or Decimal("0")
    initial_warehouse_id = data.initial_warehouse_id
    conversion_data = data.conversion
    product_data = data.model_dump(exclude={"initial_stock", "initial_warehouse_id", "conversion", "variants"})

    # Serialize images list → JSON string for DB storage
    if product_data.get("images") is not None:
        imgs = product_data["images"]
        product_data["images"] = json.dumps(imgs)
        # Auto-set primary image_url from first image if not provided
        if not product_data.get("image_url") and imgs:
            product_data["image_url"] = imgs[0]

    # Serialize extra_barcodes list → JSON string
    extra_bc = product_data.get("extra_barcodes")
    if extra_bc is not None:
        product_data["extra_barcodes"] = json.dumps([b.strip() for b in extra_bc if b.strip()])
    else:
        product_data["extra_barcodes"] = None

    # Serialize extra_product_codes list → JSON string
    extra_pc = product_data.get("extra_product_codes")
    if extra_pc is not None:
        product_data["extra_product_codes"] = json.dumps([c.strip() for c in extra_pc if c.strip()])
    else:
        product_data["extra_product_codes"] = None

    # Auto-generate SKU if not provided
    if not product_data.get("sku"):
        product_data["sku"] = _generate_sku(db)

    product_data["company_id"] = current_user.company_id

    dup_q = db.query(Product).filter(Product.is_deleted == False)
    dup_q = dup_q.filter(Product.company_id == current_user.company_id)

    if dup_q.filter(Product.sku == product_data["sku"]).first():
        raise HTTPException(status_code=400, detail=f"SKU '{product_data['sku']}' allaqachon mavjud")
    if dup_q.filter(Product.barcode == data.barcode).first():
        raise HTTPException(status_code=400,
                            detail=f"Shtrix kod '{data.barcode}' allaqachon mavjud — boshqa mahsulotda ishlatilgan")
    if dup_q.filter(Product.name == product_data["name"]).first():
        raise HTTPException(status_code=400, detail=f"'{product_data['name']}' nomli mahsulot allaqachon mavjud")

    # Konversiya berilsa — avtomatik sell turiga o'tkazamiz
    product_type = product_data.get("product_type", "stock")
    if conversion_data is not None:
        product_type = "sell"
        product_data["product_type"] = "sell"
    if product_type == "sell" and not conversion_data:
        raise HTTPException(status_code=400,
                            detail="Virtual (sell) mahsulot uchun asosiy mahsulot va nisbatni kiriting")

    product_data.pop("variants", None)
    # attributes va tags None bo'lsa bo'sh list bilan almashtir
    if product_data.get("attributes") is None:
        product_data["attributes"] = []
    if product_data.get("tags") is None:
        product_data["tags"] = []
    product = Product(**product_data)
    db.add(product)
    db.flush()

    # Variantlarni saqlash
    if getattr(data, "variants", None) and len(data.variants) > 0 and product_type in ["stock", "variant"]:
        product.product_type = "parent" # Asosiy mahsulot 'parent' turiga o'tadi
        db.flush()
        
        # Har bir variantni alohida tovar sifatida saqlaymiz
        import time
        from app.models.product_variant import ProductVariant
        for idx, v in enumerate(data.variants):
            child_sku = v.sku or f"{product.sku}-{idx+1}"
            child_barcode = v.barcode or f"200{int(time.time())}{idx}"[-13:]
            
            child = ProductVariant(
                product_id=product.id,
                name=f"{product.name} ({v.size or ''} {v.color or ''})".strip(),
                sku=child_sku,
                barcode=child_barcode,
                cost_price=v.cost_price if v.cost_price is not None else product.cost_price,
                sale_price=v.sale_price if v.sale_price is not None else product.sale_price,
                wholesale_price=v.wholesale_price if v.wholesale_price is not None else product.wholesale_price,
            )
            db.add(child)
            db.flush()
            
            # Create attributes
            from app.models.attribute import Attribute, AttributeValue, VariantAttributeValue
            if v.color:
                attr = db.query(Attribute).filter(Attribute.name == "Rang", Attribute.company_id == current_user.company_id).first()
                if not attr:
                    attr = Attribute(name="Rang", company_id=current_user.company_id)
                    db.add(attr)
                    db.flush()
                val = db.query(AttributeValue).filter(AttributeValue.attribute_id == attr.id, AttributeValue.value == v.color).first()
                if not val:
                    val = AttributeValue(attribute_id=attr.id, value=v.color)
                    db.add(val)
                    db.flush()
                db.add(VariantAttributeValue(variant_id=child.id, attribute_value_id=val.id))
            if v.size:
                attr = db.query(Attribute).filter(Attribute.name == "O'lcham", Attribute.company_id == current_user.company_id).first()
                if not attr:
                    attr = Attribute(name="O'lcham", company_id=current_user.company_id)
                    db.add(attr)
                    db.flush()
                val = db.query(AttributeValue).filter(AttributeValue.attribute_id == attr.id, AttributeValue.value == v.size).first()
                if not val:
                    val = AttributeValue(attribute_id=attr.id, value=v.size)
                    db.add(val)
                    db.flush()
                db.add(VariantAttributeValue(variant_id=child.id, attribute_value_id=val.id))
            
            if not initial_warehouse_id:
                from app.models.warehouse import Warehouse
                first_wh = db.query(Warehouse).filter(Warehouse.company_id == current_user.company_id).order_by(Warehouse.id.asc()).first()
                if first_wh:
                    initial_warehouse_id = first_wh.id
            if initial_warehouse_id:
                # Razmer matritsasidan kelgan miqdor (v.quantity) ustunlik qiladi
                variant_stock_qty = v.quantity if v.quantity is not None else initial_stock
                if variant_stock_qty > 0:
                    stock = StockLevel(
                        product_id=product.id,
                        variant_id=child.id,
                        quantity=variant_stock_qty,
                        warehouse_id=initial_warehouse_id
                    )
                    db.add(stock)
                    # Batch ham yaratamiz (FIFO uchun)
                    from app.models.batch import Batch
                    db.add(Batch(
                        product_id=product.id,
                        variant_id=child.id,
                        warehouse_id=initial_warehouse_id,
                        lot_number=f"initial-variant-{child.id}",
                        initial_quantity=variant_stock_qty,
                        quantity=variant_stock_qty,
                        purchase_price=child.cost_price or product.cost_price or 0,
                        company_id=current_user.company_id,
                    ))

    elif product_type == "stock":
        if not initial_warehouse_id:
            from app.models.warehouse import Warehouse
            first_wh = db.query(Warehouse).filter(Warehouse.company_id == current_user.company_id).order_by(
                Warehouse.id.asc()).first()
            if first_wh:
                initial_warehouse_id = first_wh.id
        if initial_warehouse_id:
            stock = StockLevel(product_id=product.id, quantity=initial_stock, warehouse_id=initial_warehouse_id)
            db.add(stock)

    # Virtual mahsulot uchun ProductConversion yozuvi
    if product_type == "sell" and conversion_data:
        # Asosiy mahsulot shu korxonadami tekshirish
        src_product = db.query(Product).filter(
            Product.id == conversion_data.source_product_id,
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
        ).first()
        if not src_product:
            raise HTTPException(status_code=404, detail="Asosiy mahsulot topilmadi")
        if src_product.product_type == "sell":
            raise HTTPException(status_code=400, detail="Asosiy mahsulot 'sell' turida bo'lishi mumkin emas")
        conv = ProductConversion(
            sell_product_id=product.id,
            source_product_id=conversion_data.source_product_id,
            ratio=conversion_data.ratio,
        )
        db.add(conv)

    log_action(
        db=db,
        action="CREATE",
        entity_type="product",
        entity_id=product.id,
        user_id=current_user.id,
        new_values={"name": product.name, "sku": product.sku, "barcode": product.barcode, "product_type": product_type},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(product)
    return _attach_stock(product, db=db)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(
        product_id: int,
        data: ProductUpdate,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    q = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    product = q.first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    old = {"name": product.name, "cost_price": str(product.cost_price), "sale_price": str(product.sale_price)}

    fields_set = data.model_dump(exclude_unset=True)
    conversion_sent = "conversion" in fields_set
    conversion_data = data.conversion if conversion_sent else None
    
    initial_stock_sent = "initial_stock" in fields_set
    initial_stock_val = data.initial_stock
    initial_wh_id = data.initial_warehouse_id
    
    update_data = data.model_dump(exclude_none=True, exclude={"conversion", "initial_stock", "initial_warehouse_id", "variants"})

    # Stock update logic
    if initial_stock_sent and product.product_type == 'stock':
        from app.models.inventory import StockLevel
        # If warehouse not sent, try to find an existing one or use first
        if not initial_wh_id:
            sl_existing = db.query(StockLevel).filter(StockLevel.product_id == product_id).first()
            if sl_existing:
                initial_wh_id = sl_existing.warehouse_id
            else:
                from app.models.warehouse import Warehouse
                wh = db.query(Warehouse).filter(Warehouse.company_id == current_user.company_id).first()
                if wh: initial_wh_id = wh.id
        
        if initial_wh_id:
            sl = db.query(StockLevel).filter(StockLevel.product_id == product_id, StockLevel.warehouse_id == initial_wh_id).first()
            if sl:
                sl.quantity = initial_stock_val if initial_stock_val is not None else 0
            else:
                db.add(StockLevel(product_id=product_id, warehouse_id=initial_wh_id, quantity=initial_stock_val or 0))

    # Duplicate checks (exclude current product)
    dup_q = db.query(Product).filter(Product.is_deleted == False, Product.id != product_id)
    dup_q = dup_q.filter(Product.company_id == current_user.company_id)

    if "sku" in update_data and update_data["sku"] != product.sku:
        if dup_q.filter(Product.sku == update_data["sku"]).first():
            raise HTTPException(status_code=400, detail=f"SKU '{update_data['sku']}' allaqachon mavjud")

    if "barcode" in update_data and update_data["barcode"] != product.barcode:
        if dup_q.filter(Product.barcode == update_data["barcode"]).first():
            raise HTTPException(status_code=400, detail=f"Shtrix kod '{update_data['barcode']}' allaqachon mavjud")
    if "name" in update_data and update_data["name"] != product.name:
        if dup_q.filter(Product.name == update_data["name"]).first():
            raise HTTPException(status_code=400, detail=f"'{update_data['name']}' nomli mahsulot allaqachon mavjud")

    # Serialize images list → JSON string for DB storage
    if "images" in update_data:
        imgs = update_data["images"]
        update_data["images"] = json.dumps(imgs) if imgs is not None else None
        if imgs and not update_data.get("image_url"):
            update_data["image_url"] = imgs[0]

    # Serialize extra_barcodes list → JSON string
    if "extra_barcodes" in update_data:
        ebc = update_data["extra_barcodes"]
        update_data["extra_barcodes"] = json.dumps([b.strip() for b in ebc if b.strip()]) if ebc else None

    # Serialize extra_product_codes list → JSON string
    if "extra_product_codes" in update_data:
        epc = update_data["extra_product_codes"]
        update_data["extra_product_codes"] = json.dumps([c.strip() for c in epc if c.strip()]) if epc else None

    update_data.pop("variants", None)
    for field, value in update_data.items():
        setattr(product, field, value)

    product_type = product.product_type or "stock"

    # Variantlarni yangilash
    if product_type == "parent" and "variants" in fields_set:
        from app.models.product_variant import ProductVariant
        from app.models.inventory import StockLevel
        from sqlalchemy import func
        from app.models.attribute import Attribute, AttributeValue, VariantAttributeValue
        
        existing_variants = db.query(ProductVariant).filter(ProductVariant.product_id == product_id).all()
        existing_by_id = {v.id: v for v in existing_variants}
        
        if data.variants:
            for idx, v in enumerate(data.variants):
                child_name = f"{product.name} ({v.size or ''} {v.color or ''})".strip()
                if v.id and v.id in existing_by_id:
                    child = existing_by_id[v.id]
                    child.name = child_name
                    child.sku = v.sku
                    child.barcode = v.barcode
                    child.cost_price = v.cost_price
                    child.wholesale_price = v.wholesale_price
                    child.sale_price = v.sale_price
                    db.query(VariantAttributeValue).filter(VariantAttributeValue.variant_id == child.id).delete()
                    existing_by_id.pop(v.id)
                else:
                    child = ProductVariant(
                        product_id=product_id,
                        name=child_name,
                        sku=v.sku,
                        barcode=v.barcode,
                        cost_price=v.cost_price,
                        wholesale_price=v.wholesale_price,
                        sale_price=v.sale_price,
                    )
                    db.add(child)
                
                db.flush()
                
                if v.color:
                    attr = db.query(Attribute).filter(Attribute.name == "Rang", Attribute.company_id == current_user.company_id).first()
                    if not attr:
                        attr = Attribute(name="Rang", company_id=current_user.company_id)
                        db.add(attr)
                        db.flush()
                    val = db.query(AttributeValue).filter(AttributeValue.attribute_id == attr.id, AttributeValue.value == v.color).first()
                    if not val:
                        val = AttributeValue(attribute_id=attr.id, value=v.color)
                        db.add(val)
                        db.flush()
                    db.add(VariantAttributeValue(variant_id=child.id, attribute_value_id=val.id))
                if v.size:
                    attr = db.query(Attribute).filter(Attribute.name == "O'lcham", Attribute.company_id == current_user.company_id).first()
                    if not attr:
                        attr = Attribute(name="O'lcham", company_id=current_user.company_id)
                        db.add(attr)
                        db.flush()
                    val = db.query(AttributeValue).filter(AttributeValue.attribute_id == attr.id, AttributeValue.value == v.size).first()
                    if not val:
                        val = AttributeValue(attribute_id=attr.id, value=v.size)
                        db.add(val)
                        db.flush()
                    db.add(VariantAttributeValue(variant_id=child.id, attribute_value_id=val.id))
        
        # Qolganlarini o'chirishga harakat qilamiz, agar qoldiq bo'lsa xato qaytaramiz
        for old_v in existing_by_id.values():
            stock_qty = db.query(func.coalesce(func.sum(StockLevel.quantity), 0)).filter(StockLevel.variant_id == old_v.id).scalar()
            if stock_qty > 0:
                raise HTTPException(status_code=400, detail=f"'{old_v.name}' variantida {stock_qty} ta qoldiq mavjud. Uni o'chirib bo'lmaydi.")
            db.delete(old_v)


    if conversion_sent and conversion_data is not None:
        product.product_type = "sell"
        product_type = "sell"
        src_product = db.query(Product).filter(
            Product.id == conversion_data.source_product_id,
            Product.company_id == current_user.company_id,
            Product.is_deleted == False,
        ).first()
        if not src_product:
            raise HTTPException(status_code=404, detail="Asosiy mahsulot topilmadi")
        if src_product.product_type == "sell":
            raise HTTPException(status_code=400, detail="Asosiy mahsulot 'sell' turida bo'lishi mumkin emas")
        existing_conv = db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == product_id
        ).first()
        if existing_conv:
            existing_conv.source_product_id = conversion_data.source_product_id
            existing_conv.ratio = conversion_data.ratio
        else:
            db.add(
                ProductConversion(
                    sell_product_id=product_id,
                    source_product_id=conversion_data.source_product_id,
                    ratio=conversion_data.ratio,
                )
            )
        db.query(StockLevel).filter(StockLevel.product_id == product_id).delete(
            synchronize_session=False
        )
    elif conversion_sent and conversion_data is None:
        product.product_type = "stock"
        db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == product_id
        ).delete(synchronize_session=False)
    elif product_type == "sell":
        existing_conv = db.query(ProductConversion).filter(
            ProductConversion.sell_product_id == product_id
        ).first()
        if not existing_conv:
            raise HTTPException(
                status_code=400,
                detail="Virtual (sell) mahsulot uchun asosiy mahsulot va nisbatni kiriting",
            )
        db.query(StockLevel).filter(StockLevel.product_id == product_id).delete(
            synchronize_session=False
        )

    log_action(
        db=db,
        action="UPDATE",
        entity_type="product",
        entity_id=product.id,
        user_id=current_user.id,
        old_values=old,
        new_values={k: str(v) for k, v in update_data.items()},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(product)
    return _attach_stock(product, db=db)


@router.patch("/{product_id}/status", response_model=ProductOut)
def toggle_product_status(
        product_id: int,
        data: ProductStatusUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    q = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    product = q.first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    product.status = data.status
    db.commit()
    db.refresh(product)
    return _attach_stock(product, db=db)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
        product_id: int,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    q = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    product = q.first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    product.is_deleted = True
    log_action(
        db=db,
        action="DELETE",
        entity_type="product",
        entity_id=product.id,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()


from pydantic import BaseModel


class BulkDeleteProductsRequest(BaseModel):
    product_ids: List[int]


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
def bulk_delete_products(
        request: Request,
        payload: BulkDeleteProductsRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    q = db.query(Product).filter(
        Product.id.in_(payload.product_ids),
        Product.is_deleted == False,
        Product.company_id == current_user.company_id
    )
    products = q.all()
    if not products:
        return {"deleted": 0}

    deleted_ids = [p.id for p in products]
    for p in products:
        p.is_deleted = True

    # Bitta bulk log yozamiz — har bir mahsulot uchun flush qilish o'rniga
    log_action(
        db=db,
        action="BULK_DELETE",
        entity_type="product",
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        new_values={"total": len(deleted_ids), "ids": deleted_ids[:50]},
    )
    db.commit()
    return {"deleted": len(products)}


from fastapi.responses import StreamingResponse
import io

@router.get("/export/rongta")
def export_rongta_txt(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(
        UserRole.admin, UserRole.director, UserRole.manager,
        UserRole.warehouse, UserRole.super_admin
    ))
):
    """
    Barcha aktiv mahsulotlarni Rongta tarozi uchun TXT formatda yuklab olish.
    Format: CODE;NAME;;PRICE;0;0;0;CODE;0;0;0;01.01.01;0
    """
    products = db.query(Product).filter(
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,
        Product.status != ProductStatus.inactive,
        Product.unit.in_(['kg', 'g'])
    ).order_by(Product.product_code.asc()).all()

    lines = []
    for p in products:
        # Kod: product_code bo'lsa uni ishlatamiz, bo'lmasa sku ni 5 xonali qilib
        code_raw = p.product_code or p.sku or str(p.id)
        try:
            code_int = int(code_raw)
            code = str(code_int).zfill(5)
        except (ValueError, TypeError):
            code = str(code_raw)[:5].zfill(5)

        name = (p.name or "").upper().strip()
        # Narx - butun son (so'm)
        try:
            price = int(float(p.sell_price or 0))
        except (ValueError, TypeError):
            price = 0

        # Rongta format: CODE;NAME;;PRICE;0;0;0;CODE;0;0;0;01.01.01;0
        line = f"{code};{name};;{price};0;0;0;{code};0;0;0;01.01.01;0"
        lines.append(line)

    txt_content = "\r\n".join(lines)

    return StreamingResponse(
        io.BytesIO(txt_content.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=RONGTA.txt"
        }
    )
