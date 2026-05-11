"""
Mahsulot qidiruvi endpointlari: POS uchun yengil ro'yxat, paginated, ids.
Katta hajmli qidiruv logikasi products.py dan ajratilgan.
"""
import json
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.inventory import StockLevel
from app.models.product import Product, ProductStatus
from app.models.user import User, UserRole
from app.schemas.product import ProductListOut, WarehouseStockOut
from app.utils.product_filters import name_filter
from app.utils.translit import translit_variants as _translit_variants

router = APIRouter(prefix="/products", tags=["Products"])


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

    q = db.query(
        Product.id,
        Product.name,
        Product.barcode,
        Product.extra_barcodes,
        Product.sku,
        Product.product_code,
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
        try:
            q = q.filter(name_filter(search))
        except Exception:
            q = q.filter(Product.name.ilike(f"%{search}%"))

    q = q.order_by(Product.name)

    if search:
        q_len = len(search.strip().replace(' ', ''))
        multiplier = 20 if q_len <= 3 else (12 if q_len <= 6 else 8)
        fetch_limit = min((limit or 50) * multiplier, 600)
    else:
        fetch_limit = limit or 50
    q = q.limit(fetch_limit)

    products_raw = q.all()
    if not products_raw:
        return []

    if search:
        import re as _re
        query_words = [w for w in search.strip().split() if w]

        def _word_score(name: str, word: str) -> int:
            n = (name or '').lower()
            for v in _translit_variants(word):
                if not v:
                    continue
                if n == v:
                    return 5
                if n.startswith(v) and (len(n) == len(v) or n[len(v)] in (' ', '-')):
                    return 4
                try:
                    if _re.search(r'(?:^|[\s\-])' + _re.escape(v) + r'(?:$|[\s\-])', n):
                        return 3
                    if _re.search(r'(?:^|[\s\-])' + _re.escape(v), n):
                        return 2
                except Exception:
                    pass
                if v in n:
                    return 1
            return 0

        def _total_score(name: str) -> int:
            return sum(_word_score(name, w) for w in query_words)

        products_raw = sorted(products_raw, key=lambda p: (-_total_score(p.name), p.name or ''))
        products_raw = products_raw[:(limit or 50)]

    product_ids = [p.id for p in products_raw]

    stock_q = db.query(
        StockLevel.product_id,
        sqlfunc.coalesce(sqlfunc.sum(StockLevel.quantity), 0).label("total_qty"),
    ).filter(StockLevel.product_id.in_(product_ids))
    if warehouse_id:
        stock_q = stock_q.filter(StockLevel.warehouse_id == warehouse_id)
    stock_rows = stock_q.group_by(StockLevel.product_id).all()
    stock_map = {r.product_id: float(r.total_qty) for r in stock_rows}

    return [
        {
            "id": p.id,
            "name": p.name,
            "barcode": p.barcode,
            "extra_barcodes": json.loads(p.extra_barcodes) if p.extra_barcodes else [],
            "sku": p.sku,
            "product_code": p.product_code,
            "extra_product_codes": [],
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
    from app.models.warehouse import Warehouse
    from sqlalchemy import case, func as f2

    q = db.query(Product).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)

    if search:
        q = q.filter(name_filter(search))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if status:
        q = q.filter(Product.status == status)
    if warehouse_id:
        q = q.join(StockLevel, (StockLevel.product_id == Product.id) & (StockLevel.warehouse_id == warehouse_id))

    ADMIN_ROLES_P = (UserRole.admin, UserRole.director)
    branch_wh_set = None
    if current_user.role not in ADMIN_ROLES_P and current_user.branch_id:
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
    total_count  = int(stats.total or 0)
    total_active = int(stats.active or 0)
    out_of_stock = int(stats.low or 0)

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
            visible_stocks = [s for s in all_stocks if s.warehouse_id in branch_wh_set]

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
    q = db.query(Product.id).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)

    if search:
        q = q.filter(name_filter(search))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if status:
        q = q.filter(Product.status == status)
    if warehouse_id:
        q = q.join(StockLevel, (StockLevel.product_id == Product.id) & (StockLevel.warehouse_id == warehouse_id))

    return [r[0] for r in q.order_by(Product.name).all()]
