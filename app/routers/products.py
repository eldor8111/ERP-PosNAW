import json
import random
import string
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.inventory import StockLevel
from app.models.product import Product, ProductStatus
from app.models.user import User, UserRole
from app.schemas.product import ProductCreate, ProductListOut, ProductOut, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _attach_stock(product: Product) -> ProductOut:
    out = ProductOut.model_validate(product)
    if product.stock_level:
        out.stock_quantity = product.stock_level.quantity
    else:
        out.stock_quantity = Decimal("0")
    return out


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

    q = db.query(Product).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)

    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )
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
    all_stock_rows = (
        db.query(StockLevel)
        .filter(StockLevel.product_id.in_(product_ids))
        .all()
    )
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

        result.append(item)
    return result


@router.get("/pos-list")
def list_products_for_pos(
    search: Optional[str] = Query(None),
    limit: Optional[int] = Query(50),
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    POS uchun yengil endpoint — faqat kerakli maydonlar.
    /products/?limit=10000 o'rniga shu endpoint ishlatilsin.
    Javob hajmi 3-5x kichik → POS tezroq yuklanadi.
    """
    from sqlalchemy import func as sqlfunc
    from collections import defaultdict

    q = db.query(
        Product.id,
        Product.name,
        Product.barcode,
        Product.sku,
        Product.sale_price,
        Product.wholesale_price,
        Product.cost_price,
        Product.min_stock,
        Product.unit,
        Product.status,
        Product.category_id,
        Product.image_url,
    ).filter(
        Product.is_deleted == False,
        Product.company_id == current_user.company_id,
        Product.status == ProductStatus.active,
    )

    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )

    q = q.order_by(Product.name)

    if limit:
        q = q.limit(limit)

    products_raw = q.all()
    if not products_raw:
        return []
    product_ids = [p.id for p in products_raw]

    # Stock levels — bitta so'rovda
    stock_q = db.query(
        StockLevel.product_id,
        sqlfunc.coalesce(sqlfunc.sum(StockLevel.quantity), 0).label("total_qty"),
    ).filter(
        StockLevel.product_id.in_(product_ids),
    )
    if warehouse_id:
        stock_q = stock_q.filter(StockLevel.warehouse_id == warehouse_id)
    stock_rows = stock_q.group_by(StockLevel.product_id).all()

    stock_map = {r.product_id: float(r.total_qty) for r in stock_rows}

    return [
        {
            "id": p.id,
            "name": p.name,
            "barcode": p.barcode,
            "sku": p.sku,
            "sale_price": float(p.sale_price),
            "wholesale_price": float(p.wholesale_price) if p.wholesale_price else None,
            "cost_price": float(p.cost_price),
            "min_stock": p.min_stock,
            "unit": p.unit,
            "status": p.status,
            "category_id": p.category_id,
            "image_url": p.image_url,
            "stock_quantity": stock_map.get(p.id, 0.0),
        }
        for p in products_raw
    ]


@router.get("/paginated")
def list_products_paginated(
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

    q = db.query(Product).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)

    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if status:
        q = q.filter(Product.status == status)
    if warehouse_id:
        q = q.join(StockLevel, (StockLevel.product_id == Product.id) & (StockLevel.warehouse_id == warehouse_id))

    # ── Bitta so'rovda 3 ta COUNT: total, active, out_of_stock ──
    from sqlalchemy import case, func as f2
    branch_wh_set = None
    ADMIN_ROLES_P = (UserRole.admin, UserRole.director)
    if current_user.role not in ADMIN_ROLES_P and current_user.branch_id:
        from app.models.warehouse import Warehouse
        branch_wh_set = {
            wh.id for wh in db.query(Warehouse.id).filter(
                Warehouse.branch_id == current_user.branch_id
            ).all()
        }

    stock_subq = db.query(
        StockLevel.product_id,
        f2.sum(StockLevel.quantity).label("total_stock")
    )
    if warehouse_id:
        stock_subq = stock_subq.filter(StockLevel.warehouse_id == warehouse_id)
    elif branch_wh_set:
        stock_subq = stock_subq.filter(StockLevel.warehouse_id.in_(branch_wh_set))
    stock_subq = stock_subq.group_by(StockLevel.product_id).subquery()

    stats = q.outerjoin(stock_subq, Product.id == stock_subq.c.product_id).with_entities(
        f2.count(Product.id).label("total"),
        f2.sum(case((Product.status == ProductStatus.active, 1), else_=0)).label("active"),
        f2.sum(case((f2.coalesce(stock_subq.c.total_stock, 0) <= Product.min_stock, 1), else_=0)).label("low"),
    ).one()
    total_count    = int(stats.total or 0)
    total_active   = int(stats.active or 0)
    out_of_stock   = int(stats.low or 0)

    products = q.order_by(Product.name).offset(skip).limit(limit).all()

    wh_q = db.query(Warehouse).filter(Warehouse.company_id == current_user.company_id)
    warehouses = {w.id: w.name for w in wh_q.all()}

    from collections import defaultdict
    product_ids = [p.id for p in products]
    all_stock_rows = (
        db.query(StockLevel).filter(StockLevel.product_id.in_(product_ids)).all()
    ) if product_ids else []
    
    stock_by_product: dict = defaultdict(list)
    for s in all_stock_rows:
        stock_by_product[s.product_id].append(s)

    items = []
    for p in products:
        item = ProductListOut.model_validate(p)
        all_stocks = stock_by_product[p.id]

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

        if warehouse_id:
            wh_stock = next((s for s in all_stocks if s.warehouse_id == warehouse_id), None)
            item.stock_quantity = wh_stock.quantity if wh_stock else Decimal("0")
        else:
            item.stock_quantity = sum((s.quantity for s in visible_stocks), Decimal("0"))
        items.append(item.model_dump())

    return {"items": items, "total": total_count, "total_active": total_active, "out_of_stock": out_of_stock}


@router.get("/ids", response_model=List[int])
def list_product_ids(
    search: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    status: Optional[ProductStatus] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.inventory import StockLevel
    q = db.query(Product.id).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)

    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if status:
        q = q.filter(Product.status == status)
    if warehouse_id:
        q = q.join(StockLevel, (StockLevel.product_id == Product.id) & (StockLevel.warehouse_id == warehouse_id))

    rows = q.order_by(Product.name).all()
    return [r[0] for r in rows]
@router.get("/barcode/{barcode}", response_model=ProductOut)
def get_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Product).filter(
        Product.barcode == barcode,
        Product.is_deleted == False,
        Product.status == ProductStatus.active,
    )
    q = q.filter(Product.company_id == current_user.company_id)
    product = q.first()

    if not product:
        raise HTTPException(status_code=404, detail=f"Barcode '{barcode}' bo'yicha mahsulot topilmadi")

    return _attach_stock(product)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Product).filter(Product.id == product_id, Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    product = q.first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return _attach_stock(product)


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
    product_data = data.model_dump(exclude={"initial_stock"})

    # Serialize images list → JSON string for DB storage
    if product_data.get("images") is not None:
        imgs = product_data["images"]
        product_data["images"] = json.dumps(imgs)
        # Auto-set primary image_url from first image if not provided
        if not product_data.get("image_url") and imgs:
            product_data["image_url"] = imgs[0]

    # Auto-generate SKU if not provided
    if not product_data.get("sku"):
        product_data["sku"] = _generate_sku(db)

    product_data["company_id"] = current_user.company_id
    
    dup_q = db.query(Product).filter(Product.is_deleted == False)
    dup_q = dup_q.filter(Product.company_id == current_user.company_id)

    if dup_q.filter(Product.sku == product_data["sku"]).first():
        raise HTTPException(status_code=400, detail=f"SKU '{product_data['sku']}' allaqachon mavjud")
    if dup_q.filter(Product.barcode == data.barcode).first():
        raise HTTPException(status_code=400, detail=f"Shtrix kod '{data.barcode}' allaqachon mavjud — boshqa mahsulotda ishlatilgan")
    if dup_q.filter(Product.name == product_data["name"]).first():
        raise HTTPException(status_code=400, detail=f"'{product_data['name']}' nomli mahsulot allaqachon mavjud")

    product = Product(**product_data)
    db.add(product)
    db.flush()

    # Boshlang'ich qoldiq yozuvi yaratish
    stock = StockLevel(product_id=product.id, quantity=initial_stock)
    db.add(stock)

    log_action(
        db=db,
        action="CREATE",
        entity_type="product",
        entity_id=product.id,
        user_id=current_user.id,
        new_values={"name": product.name, "sku": product.sku, "barcode": product.barcode},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(product)
    return _attach_stock(product)


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

    update_data = data.model_dump(exclude_none=True)

    # Duplicate checks (exclude current product)
    dup_q = db.query(Product).filter(Product.is_deleted == False, Product.id != product_id)
    dup_q = dup_q.filter(Product.company_id == current_user.company_id)

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

    for field, value in update_data.items():
        setattr(product, field, value)

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
    return _attach_stock(product)


@router.post("/bulk-import")
def bulk_import_products(
    rows: List[dict],
    allow_update: bool = Query(False),
    search_by_sku: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    """Excel fayldan ko'plab mahsulotlarni yuklash yoki yangilash.
    allow_update=True bo'lsa, mavjud mahsulotni topib, faqat yuborilgan maydonlarni yangilaydi.
    """
    # Mapping: row key from frontend → Product field and type
    FIELD_MAP = {
        "Nomi":          ("name",             str),
        "Barkod":        ("barcode",          str),
        "SKU":           ("sku",              str),
        "O'lchov":       ("unit",             str),
        "Tan narxi":     ("cost_price",       Decimal),
        "Chakana narxi": ("sale_price",       Decimal),
        "Ulgurji narxi": ("wholesale_price",  Decimal),
        "Min. qoldiq":   ("min_stock",        Decimal),
        "Qoldiq":        ("_stock",           Decimal),   # special: update stock_level
        "Holat":         ("status",           str),
        "Brand":         ("brand",            str),
    }

    STATUS_MAP = {
        "faol": "active", "active": "active",
        "nofaol": "inactive", "inactive": "inactive",
        "arxiv": "archived", "archived": "archived",
    }

    created = 0
    updated = 0
    errors: list = []

    all_products = db.query(Product).filter(
        Product.is_deleted == False,
        Product.company_id == current_user.company_id,
    ).all()
    
    name_map = {p.name: p for p in all_products if p.name}
    barcode_map = {p.barcode: p for p in all_products if p.barcode}
    sku_map = {p.sku: p for p in all_products if p.sku}

    db_skus = set(sku_map.keys())
    db_barcodes = set(barcode_map.keys())

    for idx, row in enumerate(rows):
        row_num = row.get("__row_index", idx + 2)
        name = str(row.get("Nomi") or "").strip()
        barcode = str(row.get("Barkod") or "").strip()
        sku_val = str(row.get("SKU") or "").strip() or None

        if not name and not barcode:
            errors.append({"row": row_num, "error": "Mahsulot nomi yoki barkod majburiy"})
            continue

        # ── Find existing product ──────────────────────────────────
        existing = None
        if name and name in name_map:
            existing = name_map[name]
        if not existing and barcode and barcode in barcode_map:
            existing = barcode_map[barcode]
        if not existing and search_by_sku and sku_val and sku_val in sku_map:
            existing = sku_map[sku_val]

        # ── UPDATE MODE ────────────────────────────────────────────
        if existing:
            if not allow_update:
                errors.append({
                    "row": row_num, "name": name or barcode,
                    "error": f"'{name or barcode}' nomli mahsulot allaqachon mavjud — o'tkazib yuborildi"
                })
                continue

            stock_val = None
            for row_key, (field, cast) in FIELD_MAP.items():
                raw = row.get(row_key)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    if field == "_stock":
                        stock_val = Decimal(str(raw))
                    elif cast == Decimal:
                        setattr(existing, field, Decimal(str(raw)))
                    elif field == "status":
                        mapped = STATUS_MAP.get(str(raw).strip().lower())
                        if mapped:
                            setattr(existing, field, mapped)
                    else:
                        val = str(raw).strip()
                        if val:
                            setattr(existing, field, val)
                except Exception:
                    errors.append({"row": row_num, "name": name, "error": f"'{row_key}' qiymati noto'g'ri"})
                    continue

            if stock_val is not None:
                if existing.stock_level:
                    existing.stock_level.quantity = stock_val
                else:
                    existing.stock_level = StockLevel(quantity=stock_val)

            updated += 1
            continue

        # ── CREATE MODE ────────────────────────────────────────────
        if not name:
            errors.append({"row": row_num, "error": "Yangi mahsulot uchun Nomi majburiy"})
            continue

        cost_price = row.get("Tan narxi") or 0
        sale_price = row.get("Chakana narxi") or 0
        wholesale_price = row.get("Ulgurji narxi") or None
        initial_stock = row.get("Qoldiq") or 0
        min_stock_val = row.get("Min. qoldiq") or 0
        unit = str(row.get("O'lchov") or "dona").strip()
        brand = str(row.get("Brand") or "").strip() or None
        status_raw = str(row.get("Holat") or "active").strip().lower()
        status_val = STATUS_MAP.get(status_raw, "active")

        try:
            cost_price = Decimal(str(cost_price))
            sale_price = Decimal(str(sale_price))
            wholesale_price = Decimal(str(wholesale_price)) if wholesale_price else None
            initial_stock = Decimal(str(initial_stock))
            min_stock_val = Decimal(str(min_stock_val))
        except Exception:
            errors.append({"row": row_num, "name": name, "error": "Narx/qoldiq qiymatlari noto'g'ri"})
            continue

        if barcode and barcode in db_barcodes:
            errors.append({"row": row_num, "name": name, "error": f"Barkod '{barcode}' allaqachon mavjud"})
            continue

        sku_final = sku_val
        if not sku_final or sku_final in db_skus:
            while True:
                s = f"{random.randint(10000, 99999)}"
                if s not in db_skus:
                    sku_final = s
                    break

        if not barcode:
            while True:
                b = str(random.randint(10000000, 99999999))
                if b not in db_barcodes:
                    barcode = b
                    break

        # DB field uzunlik chegarasi: barcode va sku max 50 ta belgi
        barcode = barcode[:50]
        sku_final = sku_final[:50]

        product = Product(
            name=name[:255], barcode=barcode, sku=sku_final, unit=unit[:20] if unit else "dona",
            cost_price=cost_price, sale_price=sale_price,
            wholesale_price=wholesale_price, min_stock=min_stock_val,
            status=status_val, brand=brand[:100] if brand else None,
            company_id=current_user.company_id, images="[]",
        )
        product.stock_level = StockLevel(quantity=initial_stock)
        db.add(product)

        # O(1) in-memory state tracking to avoid DB flush/queries inside loop
        db_barcodes.add(barcode)
        db_skus.add(sku_final)
        name_map[name] = product
        barcode_map[barcode] = product
        sku_map[sku_final] = product

        created += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append({"row": 0, "error": f"Saqlashda xato: {str(exc)[:300]}"})
        created = 0
        updated = 0

    total_errors = len(errors)
    return {
        "created": created,
        "updated": updated,
        "skipped": total_errors,
        "errors": errors[:200],          # max 200 ta xato qaytariladi
        "total_errors": total_errors,    # haqiqiy jami xato soni
    }


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


from fastapi import APIRouter, Depends, HTTPException, Query, Request, status, Body

# ... (rest of imports remain intact, but we'll just fix the endpoint signature below) ...

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
