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
from app.models.product import ProductConversion
from app.schemas.product import (
    ProductConversionOut,
    ProductConversionReverseOut,
    ProductListOut,
    WarehouseStockOut,
)
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
        Product.product_type,
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

    # sell tipli mahsulotlar uchun konversiya ma'lumotini olish
    from app.models.product import ProductConversion
    sell_ids = [p.id for p in products_raw if (p.product_type or 'stock') == 'sell']
    conversion_map = {}
    source_ids_to_fetch = set()
    if sell_ids:
        convs = db.query(ProductConversion).filter(
            ProductConversion.sell_product_id.in_(sell_ids)
        ).all()
        for c in convs:
            conversion_map[c.sell_product_id] = {
                "source_product_id": c.source_product_id,
                "ratio": float(c.ratio),
            }
            if c.source_product_id not in product_ids:
                source_ids_to_fetch.add(c.source_product_id)

    # StockLevel ma'lumotlarini olish (products_raw + source_product_id lari)
    all_needed_ids = set(product_ids) | source_ids_to_fetch
    stock_q = db.query(
        StockLevel.product_id,
        sqlfunc.coalesce(sqlfunc.sum(StockLevel.quantity), 0).label("total_qty"),
    ).filter(StockLevel.product_id.in_(all_needed_ids))
    if warehouse_id:
        stock_q = stock_q.filter(StockLevel.warehouse_id == warehouse_id)
    stock_rows = stock_q.group_by(StockLevel.product_id).all()
    stock_map = {r.product_id: float(r.total_qty) for r in stock_rows}

    def get_stock(p):
        if (p.product_type or 'stock') == 'sell':
            # Mijoz talabiga ko'ra virtual mahsulot qoldig'i har doim 0 bo'lib turishi kerak
            return 0.0
        return stock_map.get(p.id, 0.0)

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
            "product_type": p.product_type or "stock",
            "stock_quantity": get_stock(p),
            "conversion": conversion_map.get(p.id),
        }
        for p in products_raw
    ]


@router.get("/paginated")
def list_products_paginated(
    search: Optional[str] = Query(None, description="Nomi yoki SKU bo'yicha qidiruv"),
    category_id: Optional[int] = Query(None),
    status: Optional[ProductStatus] = Query(None),
    warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filter"),
    unit: Optional[str] = Query(None, description="O'lchov birligi bo'yicha filter (dona, kg, litr, metr, gramm)"),
    stock_status: Optional[str] = Query(None, description="Ombor holati bo'yicha filter (qolmagan, kam-qolgan, minusda)"),
    sort_by: Optional[str] = Query(None, description="Saralash maydoni: sale_price, wholesale_price, cost_price, profit"),
    sort_order: Optional[str] = Query(None, description="Saralash tartibi: asc, desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=20000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.warehouse import Warehouse
    from sqlalchemy import case, func as f2
    from sqlalchemy.orm import joinedload

    q = db.query(Product).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    q = q.options(
        joinedload(Product.conversion).joinedload(ProductConversion.source_product),
        joinedload(Product.sell_conversions).joinedload(ProductConversion.sell_product),
    )

    if search:
        q = q.filter(name_filter(search))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if status:
        q = q.filter(Product.status == status)
    if unit:
        q = q.filter(Product.unit.ilike(unit))
    if warehouse_id:
        # Ombor bo'yicha filter: OUTER JOIN ishlatamiz, shunda 0 qoldiqli/recordi yo'q mahsulotlar ham chiqadi
        q = q.outerjoin(StockLevel, (StockLevel.product_id == Product.id) & (StockLevel.warehouse_id == warehouse_id))

    ADMIN_ROLES_P = (UserRole.admin, UserRole.director, UserRole.super_admin)
    branch_wh_set = None
    if current_user.role not in ADMIN_ROLES_P and current_user.branch_id:
        branch_wh_set = {
            wh.id for wh in db.query(Warehouse.id).filter(
                Warehouse.branch_id == current_user.branch_id
            ).all()
        }

    stock_subq = db.query(
        StockLevel.product_id,
        f2.coalesce(f2.sum(StockLevel.quantity), 0).label("total_stock")
    )
    if warehouse_id:
        stock_subq = stock_subq.filter(StockLevel.warehouse_id == warehouse_id)
    elif branch_wh_set:
        stock_subq = stock_subq.filter(StockLevel.warehouse_id.in_(branch_wh_set))
    stock_subq = stock_subq.group_by(StockLevel.product_id).subquery()

    if stock_status:
        q = q.outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
        if stock_status == "qolmagan":
            q = q.filter(f2.coalesce(stock_subq.c.total_stock, 0) <= 0)
        elif stock_status == "kam-qolgan":
            q = q.filter(f2.coalesce(stock_subq.c.total_stock, 0) <= Product.min_stock)
        elif stock_status == "minusda":
            q = q.filter(f2.coalesce(stock_subq.c.total_stock, 0) < 0)

    # Stats: jami mahsulotlar soni va qiymatlari (head panel uchun)
    # stats_q filterlardan o'tgan bo'lishi kerak, lekin limit/skip dan oldin
    stats_q = q if stock_status else q.outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
    
    stats_row = stats_q.with_entities(
        f2.count(Product.id).label("total"),
        f2.sum(case((Product.status == ProductStatus.active, 1), else_=0)).label("active"),
        f2.sum(case((f2.coalesce(stock_subq.c.total_stock, 0) <= Product.min_stock, 1), else_=0)).label("low"),
        f2.sum(f2.coalesce(stock_subq.c.total_stock, 0) * f2.coalesce(Product.sale_price, 0)).label("sale_value"),
        f2.sum(f2.coalesce(stock_subq.c.total_stock, 0) * f2.coalesce(Product.wholesale_price, 0)).label("wholesale_value"),
        f2.sum(f2.coalesce(stock_subq.c.total_stock, 0) * f2.coalesce(Product.cost_price, 0)).label("cost_value"),
    ).first()
    if stats_row:
        total_count  = int(stats_row.total or 0)
        total_active = int(stats_row.active or 0)
        out_of_stock = int(stats_row.low or 0)
        sale_value = float(stats_row.sale_value or 0)
        wholesale_value = float(stats_row.wholesale_value or 0)
        cost_value = float(stats_row.cost_value or 0)
    else:
        total_count = total_active = out_of_stock = 0
        sale_value = wholesale_value = cost_value = 0.0

    # Saralash tartibi
    ALLOWED_SORT_FIELDS = ('sale_price', 'wholesale_price', 'cost_price', 'profit')
    if sort_by in ALLOWED_SORT_FIELDS and sort_order in ('asc', 'desc'):
        from sqlalchemy import asc as _asc, desc as _desc
        dir_fn = _asc if sort_order == 'asc' else _desc
        if sort_by == 'profit':
            # Foyda marjasi = chakana narx - kirim narx
            products = q.order_by(dir_fn(Product.sale_price - Product.cost_price)).offset(skip).limit(limit).all()
        elif sort_by == 'sale_price':
            products = q.order_by(dir_fn(Product.sale_price)).offset(skip).limit(limit).all()
        elif sort_by == 'wholesale_price':
            products = q.order_by(dir_fn(Product.wholesale_price)).offset(skip).limit(limit).all()
        elif sort_by == 'cost_price':
            products = q.order_by(dir_fn(Product.cost_price)).offset(skip).limit(limit).all()
        else:
            products = q.order_by(Product.name).offset(skip).limit(limit).all()
    else:
        products = q.order_by(Product.name).offset(skip).limit(limit).all()

    wh_q = db.query(Warehouse).filter(Warehouse.company_id == current_user.company_id)
    warehouses = {w.id: w.name for w in wh_q.all()}

    from collections import defaultdict
    product_ids = [p.id for p in products]

    # Virtual mahsulotlarning asosiy mahsulot (source_product) IDlarini qo'shamiz
    source_ids = set()
    for p in products:
        if getattr(p, "product_type", "stock") == "sell" and getattr(p, "conversion", None):
            source_ids.add(p.conversion.source_product_id)

    all_needed_ids = set(product_ids) | source_ids

    all_stock_rows = (
        db.query(StockLevel).filter(StockLevel.product_id.in_(all_needed_ids)).all()
    ) if all_needed_ids else []

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
            raw_qty = wh_stock.quantity if wh_stock else Decimal("0")
        else:
            raw_qty = sum((s.quantity for s in visible_stocks), Decimal("0"))
        # Manfiy qoldiqni ham ko'rsatamiz (clamp yo'q)
        item.stock_quantity = raw_qty

        if p.conversion:
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


        if getattr(p, "sell_conversions", None):
            item.sell_conversions = []
            for conv in p.sell_conversions:
                sell_p = conv.sell_product
                if sell_p and not sell_p.is_deleted:
                    item.sell_conversions.append(
                        ProductConversionReverseOut(
                            id=conv.id,
                            sell_product_id=conv.sell_product_id,
                            sell_product_name=sell_p.name,
                            ratio=conv.ratio,
                        )
                    )

        items.append(item.model_dump())

    return {
        "items": items,
        "total": total_count,
        "total_active": total_active,
        "out_of_stock": out_of_stock,
        "sale_value": sale_value,
        "wholesale_value": wholesale_value,
        "cost_value": cost_value
    }


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
