"""
Mahsulot qidiruvi endpointlari: POS uchun yengil ro'yxat, paginated, ids.
Katta hajmli qidiruv logikasi products.py dan ajratilgan.
"""
import json
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context, warehouse_ids_for_ctx
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
from app.services import stock_report
from app.services.warehouse_scope import (
    default_sale_warehouse_id, sellable_warehouses_query, sellable_warehouse_ids, stock_totals,
)
from app.utils.product_filters import name_filter
from app.utils.translit import translit_variants as _translit_variants

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("/pos-context")
def pos_context(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    """POS ombor tanlagichi uchun (T1.17): joriy filial, default sotuv ombori va
    sotiladigan (faol, xom ashyosiz) omborlar ro'yxati."""
    from app.core.branch_context import effective_branch_id
    from app.models.warehouse import Warehouse

    scope = ctx.scope_ids()
    q = sellable_warehouses_query(db, current_user.company_id, branch_ids=scope)
    whs = q.order_by(Warehouse.id).all()
    branch_id = ctx.branch_id if ctx.branch_id is not None else effective_branch_id(db, current_user)
    default_id = default_sale_warehouse_id(db, current_user.company_id, branch_id)
    # default ombor ko'rinadigan omborlar ichida bo'lsin (filial doirasidan tashqariga chiqmasin)
    if default_id is not None and default_id not in {w.id for w in whs}:
        default_id = None
    return {
        "branch_id": branch_id,
        "default_warehouse_id": default_id,
        "warehouses": [
            {"id": w.id, "name": w.name, "type": getattr(w.type, "value", w.type)} for w in whs
        ],
    }


@router.get("/pos-list")
def list_products_for_pos(
    search: Optional[str] = Query(None),
    limit: Optional[int] = Query(50, ge=1, le=5000),
    skip: int = Query(0, ge=0),
    warehouse_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None, description="Filial narxlari uchun filial (T4.3)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    """
    POS uchun yengil endpoint — faqat kerakli maydonlar.
    /products/?limit=10000 o'rniga shu endpoint ishlatilsin.
    Javob hajmi 3-5x kichik → POS tezroq yuklanadi.

    Qoldiq (`stock_quantity`): `warehouse_id` berilsa shu ombor (korxonaniki, faol va foydalanuvchi
    filialida bo'lishi shart), berilmasa joriy filialning sotiladigan omborlari (T1.17).

    Narx (T4.3): `branch_id` (yoki ombor filiali / joriy filial) uchun filial narxi bo'lsa `sale_price` /
    `wholesale_price` shu bilan almashtiriladi va `price_source="branch"`, aks holda `"product"` (korxona narxi).
    """
    from app.models.warehouse import Warehouse
    from app.services.tenant_guards import WAREHOUSE_NOT_FOUND, WAREHOUSE_OTHER_BRANCH

    scope = ctx.scope_ids()
    if warehouse_id:
        wh = db.query(Warehouse).filter(
            Warehouse.id == warehouse_id,
            Warehouse.company_id == current_user.company_id,
            Warehouse.is_active == True,  # noqa: E712
        ).first()
        if not wh:
            raise HTTPException(status_code=404, detail=WAREHOUSE_NOT_FOUND)
        if scope is not None and wh.branch_id not in scope:
            raise HTTPException(status_code=403, detail=WAREHOUSE_OTHER_BRANCH)
        wh_ids = [wh.id]
        _wh_branch_id = wh.branch_id
    else:
        wh_ids = sellable_warehouse_ids(db, current_user.company_id, branch_ids=scope)
        _wh_branch_id = None

    # T4.3: narx filiali — aniq branch_id (korxonaniki va ruxsat doirasida) > ombor filiali > joriy filial
    if branch_id is not None:
        from app.models.branch import Branch
        if not db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == current_user.company_id).first():
            raise HTTPException(status_code=404, detail="Filial topilmadi")
        if scope is not None and branch_id not in scope:
            raise HTTPException(status_code=403, detail=WAREHOUSE_OTHER_BRANCH)
        price_branch_id = branch_id
    else:
        from app.core.branch_context import effective_branch_id
        price_branch_id = _wh_branch_id or effective_branch_id(db, current_user)

    q = db.query(
        Product.id,
        Product.name,
        Product.barcode,
        Product.extra_barcodes,
        Product.sku,
        Product.plu_code,
        Product.product_code,
        Product.sale_price,
        Product.sale_currency,
        Product.wholesale_price,
        Product.wholesale_currency,
        Product.cost_price,
        Product.cost_currency,
        Product.min_stock,
        Product.unit,
        Product.status,
        Product.category_id,
        Product.image_url,
        Product.product_type,
        Product.mxik_code,
        Product.package_code,
        Product.parent_code,
        Product.requires_marking,
        Product.vat_rate_type,
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

    # Barqaror tartib (nom, id) — sahifalashda (skip/limit) qatorlar takrorlanmasin/tushib qolmasin
    q = q.order_by(Product.name, Product.id)

    if search:
        q_len = len(search.strip().replace(' ', ''))
        multiplier = 20 if q_len <= 3 else (12 if q_len <= 6 else 8)
        fetch_limit = min((limit or 50) * multiplier, 600)
    else:
        # T3.11: qidiruvsiz yo'lda sahifalash (butun katalogni POS ga yuklash uchun)
        fetch_limit = limit or 50
        q = q.offset(skip)
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
    # Qoldiq faqat tanlangan/joriy filial omborlaridan (NULL-ombor qatorlari va bo'sh omborlar -> 0)
    stock_map = {pid: float(qty) for pid, qty in stock_totals(db, all_needed_ids, wh_ids).items()}

    from app.services.branch_price_service import get_branch_prices
    branch_prices = get_branch_prices(db, current_user.company_id, price_branch_id, product_ids)

    def _price(p):
        """-> (sale_price, wholesale_price, price_source): filial narxi bo'lsa shu (NULL ustun korxona narxida qoladi)."""
        bp = branch_prices.get((p.id, None))
        sale = float(p.sale_price)
        wholesale = float(p.wholesale_price) if p.wholesale_price else None
        if bp is None:
            return sale, wholesale, "product"
        if bp.sale_price is not None:
            sale = float(bp.sale_price)
        if bp.wholesale_price is not None:
            wholesale = float(bp.wholesale_price)
        return sale, wholesale, "branch"

    def get_stock(p):
        if (p.product_type or 'stock') == 'sell':
            # Mijoz talabiga ko'ra virtual mahsulot qoldig'i har doim 0 bo'lib turishi kerak
            return 0.0
        return stock_map.get(p.id, 0.0)

    prices = {p.id: _price(p) for p in products_raw}  # C4.1: har mahsulot narxi bir marta hisoblanadi

    return [
        {
            "id": p.id,
            "name": p.name,
            "barcode": p.barcode,
            "extra_barcodes": json.loads(p.extra_barcodes) if p.extra_barcodes else [],
            "sku": p.sku,
            "plu_code": p.plu_code,
            "product_code": p.product_code,
            "extra_product_codes": [],
            "sale_price": prices[p.id][0],
            "sale_currency": p.sale_currency or "UZS",
            "wholesale_price": prices[p.id][1],
            "wholesale_currency": p.wholesale_currency or "UZS",
            "price_source": prices[p.id][2],
            "cost_price": float(p.cost_price),
            "cost_currency": p.cost_currency or "UZS",
            "min_stock": p.min_stock,
            "unit": p.unit,
            "status": p.status,
            "category_id": p.category_id,
            "image_url": p.image_url,
            "product_type": p.product_type or "stock",
            "stock_quantity": get_stock(p),
            "conversion": conversion_map.get(p.id),
            "mxik_code": p.mxik_code,
            "package_code": p.package_code,
            "parent_code": p.parent_code,
            "requires_marking": bool(p.requires_marking),
            "vat_rate_type": p.vat_rate_type.value if p.vat_rate_type else None,
        }
        for p in products_raw
    ]


@router.get("/paginated")
def list_products_paginated(
    search: Optional[str] = Query(None, description="Nomi yoki SKU bo'yicha qidiruv"),
    category_id: Optional[int] = Query(None),
    status: Optional[ProductStatus] = Query(None),
    warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filter"),
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha filter (shu filial omborlari qoldig'i)"),
    unit: Optional[str] = Query(None, description="O'lchov birligi bo'yicha filter (dona, kg, litr, metr, gramm)"),
    stock_status: Optional[str] = Query(None, description="Ombor holati bo'yicha filter (qolmagan, kam-qolgan, minusda)"),
    sort_by: Optional[str] = Query(None, description="Saralash maydoni: sale_price, wholesale_price, cost_price, profit"),
    sort_order: Optional[str] = Query(None, description="Saralash tartibi: asc, desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=20000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    from app.models.warehouse import Warehouse
    from sqlalchemy import case, func as f2, text
    from sqlalchemy.orm import joinedload

    q = db.query(Product).filter(Product.is_deleted == False)
    q = q.filter(Product.company_id == current_user.company_id)
    q = q.options(
        joinedload(Product.conversion).joinedload(ProductConversion.source_product),
        joinedload(Product.sell_conversions).joinedload(ProductConversion.sell_product),
        joinedload(Product.category),
    )

    if search:
        q = q.filter(name_filter(search))
    if category_id:
        q = q.filter(Product.category_id == category_id)
    if status:
        q = q.filter(Product.status == status)
    if unit:
        q = q.filter(Product.unit.ilike(unit))
    # T2.3: ombor korxonaniki (404), tanlangan filialniki (400) va ruxsat doirasida (403) bo'lishi shart.
    # Eslatma: ombor bo'yicha qoldiq `stock_subq` ichida filtrlanadi — StockLevel bilan to'g'ridan-to'g'ri
    # JOIN variantli mahsulotda qatorlarni ko'paytirib, jami va statistikani buzardi.
    if not warehouse_id and branch_id and ctx.allowed_branch_ids is not None \
            and branch_id not in ctx.allowed_branch_ids:
        branch_id = None  # ruxsatsiz filial parametri e'tiborsiz (xodim o'z doirasida qoladi)
    wh_scope = stock_report.resolve_wh_scope(db, current_user, current_user.company_id, branch_id, warehouse_id, ctx)

    # T1.1: ko'rinadigan omborlar (None → cheklov yo'q). Aniq ombor tanlanganda qatorlardagi
    # `warehouse_stocks` hamon filial kontekstidan, aks holda tanlangan doiradan olinadi.
    if warehouse_id:
        branch_wh_set = warehouse_ids_for_ctx(db, ctx)
    else:
        branch_wh_set = set(wh_scope) if wh_scope is not None else None

    stock_subq = db.query(
        StockLevel.product_id,
        f2.coalesce(f2.sum(StockLevel.quantity), 0).label("total_stock")
    ).outerjoin(Warehouse, Warehouse.id == StockLevel.warehouse_id).filter(
        # T1.12: arxivlangan (nofaol) ombor qoldig'i jamga qo'shilmaydi
        StockLevel.warehouse_id.is_(None) | Warehouse.is_active.isnot(False)
    )
    if warehouse_id:
        stock_subq = stock_subq.filter(StockLevel.warehouse_id == warehouse_id)
    elif branch_wh_set is not None:
        # MODEL-22: bo'sh to'plam ham filtr (in_([]) → 0), ko'rsatiladigan qoldiq bilan mos
        stock_subq = stock_subq.filter(StockLevel.warehouse_id.in_(list(branch_wh_set)))
    stock_subq = stock_subq.group_by(StockLevel.product_id).subquery()

    low_cond = (
        (Product.min_stock > 0)
        & (f2.coalesce(stock_subq.c.total_stock, 0) <= Product.min_stock)
        & (f2.coalesce(Product.product_type, "simple") != stock_report.VIRTUAL_PRODUCT_TYPE)
    )

    if stock_status:
        q = q.outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
        if stock_status == "qolmagan":
            q = q.filter(f2.coalesce(stock_subq.c.total_stock, 0) <= 0)
        elif stock_status == "kam-qolgan":
            # yagona ta'rif (stock_report): min_stock > 0 va jami qoldiq <= min_stock, virtual (sell) bo'lmagan
            q = q.filter(low_cond)
        elif stock_status == "minusda":
            q = q.filter(f2.coalesce(stock_subq.c.total_stock, 0) < 0)

    # Stats: jami mahsulotlar soni va qiymatlari (head panel uchun)
    # stats_q filterlardan o'tgan bo'lishi kerak, lekin limit/skip dan oldin
    stats_q = q if stock_status else q.outerjoin(stock_subq, Product.id == stock_subq.c.product_id)

    counts_row = stats_q.with_entities(
        f2.count(Product.id).label("total"),
        f2.sum(case((Product.status == ProductStatus.active, 1), else_=0)).label("active"),
        f2.sum(case((low_cond, 1), else_=0)).label("low"),
    ).first()

    total_count = int(counts_row.total or 0) if counts_row else 0
    total_active = int(counts_row.active or 0) if counts_row else 0
    out_of_stock = int(counts_row.low or 0) if counts_row else 0

    # Currency grouped values (Prices sum only as requested)
    sale_values_res = stats_q.with_entities(
        Product.sale_currency,
        f2.sum(f2.coalesce(stock_subq.c.total_stock, 0) * f2.coalesce(Product.sale_price, 0)).label("val")
    ).filter(f2.coalesce(stock_subq.c.total_stock, 0) > 0).group_by(Product.sale_currency).all()

    wholesale_values_res = stats_q.with_entities(
        case(
          (Product.wholesale_currency == 'UZS', Product.sale_currency),
          else_=Product.wholesale_currency
        ).label("cur"),
        f2.sum(f2.coalesce(stock_subq.c.total_stock, 0) * f2.coalesce(Product.wholesale_price, 0)).label("val")
    ).filter(f2.coalesce(stock_subq.c.total_stock, 0) > 0).group_by(text("cur")).all()

    cost_values_res = stats_q.with_entities(
        Product.cost_currency,
        f2.sum(f2.coalesce(stock_subq.c.total_stock, 0) * f2.coalesce(Product.cost_price, 0)).label("val")
    ).filter(f2.coalesce(stock_subq.c.total_stock, 0) > 0).group_by(Product.cost_currency).all()

    sale_values_dict = {r[0] or "UZS": float(r[1] or 0) for r in sale_values_res}
    wholesale_values_dict = {r[0] or "UZS": float(r[1] or 0) for r in wholesale_values_res}
    cost_values_dict = {r[0] or "UZS": float(r[1] or 0) for r in cost_values_res}

    # Backward compatibility sums (raw values)
    sale_value = sum(sale_values_dict.values())
    wholesale_value = sum(wholesale_values_dict.values())
    cost_value = sum(cost_values_dict.values())

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
        db.query(StockLevel)
        .outerjoin(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        # T1.12: arxivlangan (nofaol) ombor qoldig'i jamga qo'shilmaydi
        .filter(StockLevel.product_id.in_(all_needed_ids),
                StockLevel.warehouse_id.is_(None) | Warehouse.is_active.isnot(False))
        .all()
    ) if all_needed_ids else []

    stock_by_product: dict = defaultdict(list)
    for s in all_stock_rows:
        stock_by_product[s.product_id].append(s)

    items = []
    for p in products:
        item = ProductListOut.model_validate(p)
        item.category_name = p.category.name if p.category else None
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
            # variantli mahsulot: tanlangan ombordagi barcha variantlar yig'indisi
            raw_qty = sum((s.quantity for s in all_stocks if s.warehouse_id == warehouse_id), Decimal("0"))
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
        "cost_value": cost_value,
        "sale_values": sale_values_dict,
        "wholesale_values": wholesale_values_dict,
        "cost_values": cost_values_dict
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
        # EXISTS: variantli mahsulot (bir ombordagi bir nechta qator) id'ni takrorlamasin
        q = q.filter(exists().where(StockLevel.product_id == Product.id, StockLevel.warehouse_id == warehouse_id))

    return [r[0] for r in q.order_by(Product.name).all()]


class ProductIdsIn(BaseModel):
    product_ids: List[int]


@router.post("/by-ids")
def products_by_ids(
    payload: ProductIdsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tanlangan tovarlarning yorliq (shtrix-kod chop etish) uchun qisqa ma'lumoti — tanlangan tartibda.
    Ommaviy amallarda "hammasini tanlash" boshqa sahifadagi tovarlarni ham belgilaydi — ular ro'yxatda yuklanmagan."""
    ids = list(dict.fromkeys(payload.product_ids))[:5000]
    if not ids:
        return []
    rows = (
        db.query(Product.id, Product.name, Product.barcode, Product.sku, Product.plu_code, Product.product_code,
                 Product.sale_price, Product.sale_currency)
        .filter(Product.id.in_(ids), Product.company_id == current_user.company_id, Product.is_deleted == False)
        .all()
    )
    by_id = {r.id: r for r in rows}
    return [
        {"id": r.id, "name": r.name, "barcode": r.barcode, "sku": r.sku, "plu_code": r.plu_code, "product_code": r.product_code,
         "sale_price": float(r.sale_price or 0), "sale_currency": r.sale_currency}
        for r in (by_id.get(i) for i in ids) if r is not None
    ]
