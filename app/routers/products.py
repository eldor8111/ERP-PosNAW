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
from app.schemas.product import ProductCreate, ProductListOut, ProductOut, ProductStatusUpdate, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)

from app.utils.product_filters import name_filter as _name_filter  # noqa: E402


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


@router.get("/barcode/{barcode}", response_model=ProductOut)
def get_by_barcode(
    barcode: str,
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
            .filter(*base_filter, Product.extra_barcodes.ilike(f'%"{barcode}"%'))
            .first()
        )

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

    # Serialize extra_barcodes list → JSON string
    if "extra_barcodes" in update_data:
        ebc = update_data["extra_barcodes"]
        update_data["extra_barcodes"] = json.dumps([b.strip() for b in ebc if b.strip()]) if ebc else None

    # Serialize extra_product_codes list → JSON string
    if "extra_product_codes" in update_data:
        epc = update_data["extra_product_codes"]
        update_data["extra_product_codes"] = json.dumps([c.strip() for c in epc if c.strip()]) if epc else None

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
    return _attach_stock(product)


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
