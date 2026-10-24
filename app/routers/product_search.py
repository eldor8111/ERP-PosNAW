"""
Mahsulot qidiruvi endpointlari: POS uchun yengil ro'yxat, paginated, ids.
Katta hajmli qidiruv logikasi products.py dan ajratilgan.
"""
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, exists, func, or_, select, true
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context, warehouse_ids_for_ctx
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.batch import Batch
from app.models.inventory import StockLevel
from app.models.product import Product, ProductStatus
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
from app.models.product_units import ProductUnit
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
from app.services.batch_allocator import expiry_cutoff, tashkent_today
from app.services.pharmacy import pharmacy_context
from app.services.sale_stock import loose_units_by_product, pack_unit_name, stock_display_of, unit_list_price
from app.utils.product_filters import _normalize, _word_condition, name_filter
from app.utils.translit import substance_variants as _substance_variants
from app.utils.translit import translit_variants as _translit_variants

router = APIRouter(prefix="/products", tags=["Products"])


def _substance_word_cond(word: str):
    """Bitta so'z moddaning uz/ru/lat nomlaridan birida (translit va imlo variantlari bilan)."""
    conds = []
    for v in _substance_variants(word):
        conds.extend(
            col.ilike(f"%{v}%")
            for col in (PharmaSubstance.name_uz, PharmaSubstance.name_ru, PharmaSubstance.name_lat)
        )
    return or_(*conds)


def product_search_filter(search: str, company_id: int, pharmacy: bool):
    """Mahsulot qidiruv sharti. Dorixona rejimida har bir so'z mahsulot maydonlari (nom, shtrix-kod, ...)
    YOKI bog'langan modda nomi (uz/ru/lat; umumiy yoki shu korxona moddasi) bo'yicha topiladi (D2.3).
    Oddiy korxonada — avvalgi `name_filter` (qo'shimcha so'rov/JOIN yo'q)."""
    if not pharmacy:
        return name_filter(search)
    words = [w for w in _normalize(search).split() if w]
    if not words:
        return true()
    conds = []
    for w in words:
        sub = (
            select(ProductSubstance.product_id)
            .join(PharmaSubstance, PharmaSubstance.id == ProductSubstance.substance_id)
            .where(
                or_(PharmaSubstance.company_id.is_(None), PharmaSubstance.company_id == company_id),
                _substance_word_cond(w),
            )
        )
        conds.append(or_(_word_condition(w), Product.id.in_(sub)))
    # D2.4: birlik (quti/blister) shtrix-kodi skanerlansa shu mahsulot topiladi
    unit_hit = Product.id.in_(
        select(ProductUnit.product_id).where(ProductUnit.company_id == company_id, ProductUnit.barcode == search.strip())
    )
    return or_(and_(*conds), unit_hit)


def _pharmacy_pos_extras(db: Session, product_ids, wh_ids, settings: dict) -> dict:
    """Dorixona rejimida POS qatorlari uchun qo'shimcha maydonlar — butun sahifa uchun 3 ta so'rov.
    -> {product_id: {substances, is_rx, control_class, nearest_expiry, expiry_warn, expired_qty}}
    P.7: expired_qty — shu omborlardagi muddati o'tgan (sotilmaydigan) partiyalar qoldig'i (kassada qizil miltillaydi)."""
    ids = list(product_ids)
    out = {
        pid: {"substances": [], "is_rx": False, "control_class": "none",
              "nearest_expiry": None, "expiry_warn": False, "expired_qty": 0.0}
        for pid in ids
    }
    if not ids:
        return out
    for pid, is_rx, control_class in db.query(
        ProductPharma.product_id, ProductPharma.is_rx, ProductPharma.control_class
    ).filter(ProductPharma.product_id.in_(ids)):
        out[pid]["is_rx"] = bool(is_rx)
        out[pid]["control_class"] = control_class or "none"
    for pid, sid, n_uz, n_ru, n_lat in (
        db.query(ProductSubstance.product_id, PharmaSubstance.id, PharmaSubstance.name_uz,
                 PharmaSubstance.name_ru, PharmaSubstance.name_lat)
        .join(PharmaSubstance, PharmaSubstance.id == ProductSubstance.substance_id)
        .filter(ProductSubstance.product_id.in_(ids))
        .order_by(PharmaSubstance.name_uz, PharmaSubstance.id)
    ):
        out[pid]["substances"].append({"id": sid, "name_uz": n_uz, "name_ru": n_ru, "name_lat": n_lat})
    nearest = _nearest_valid_expiry(db, ids, wh_ids, settings)
    warn_until = tashkent_today() + timedelta(days=int(settings.get("expiry_warn_days") or 0))
    for pid, d in nearest.items():
        out[pid]["nearest_expiry"] = d.isoformat()
        out[pid]["expiry_warn"] = d <= warn_until
    if wh_ids:
        today_start = datetime.combine(tashkent_today(), datetime.min.time())
        for pid, qty in (
            db.query(Batch.product_id, func.sum(Batch.quantity))
            .filter(Batch.product_id.in_(ids), Batch.warehouse_id.in_(list(wh_ids)), Batch.quantity > 0,
                    Batch.expiry_date.isnot(None), Batch.expiry_date < today_start)
            .group_by(Batch.product_id)
        ):
            out[pid]["expired_qty"] = float(qty or 0)
    return out


def _nearest_valid_expiry(db: Session, product_ids, wh_ids, settings: dict) -> dict:
    """{product_id: eng yaqin yaroqli muddat (date)} — berilgan omborlardagi qoldig'i bor, sotuvga yaroqli
    (muddati `expiry_block_days` dan keyin tugaydigan) partiyalar bo'yicha. Muddatsiz partiyalar hisobga olinmaydi."""
    ids, wh = list(product_ids), list(wh_ids)
    if not ids or not wh:
        return {}
    cutoff = expiry_cutoff(tashkent_today(), settings.get("expiry_block_days") or 0)
    rows = (
        db.query(Batch.product_id, func.min(Batch.expiry_date))
        .filter(Batch.product_id.in_(ids), Batch.warehouse_id.in_(wh), Batch.quantity > 0,
                Batch.expiry_date.isnot(None), Batch.expiry_date >= cutoff)
        .group_by(Batch.product_id)
        .all()
    )
    return {pid: (exp.date() if hasattr(exp, "date") else exp) for pid, exp in rows if exp is not None}


def _pharmacy_unit_extras(db: Session, company_id: int, products, prices: dict, stock_map: dict, wh_ids, search,
                          price_round=0) -> dict:
    """D2.4: dorixona rejimida POS qatorlari uchun qadoq birliklari — butun sahifa uchun 3 ta so'rov.
    -> {product_id: {units, pack_ratio, scanned_unit_id, stock_display, full_boxes, loose_units}}
    `scanned_unit_id` — qidiruv matni aynan birlik shtrix-kodi bo'lsa shu birlik (kassa mahsulot + birlikni qo'shadi)."""
    ids = [p.id for p in products]
    units_by = {pid: [] for pid in ids}
    if ids:
        for u in (
            db.query(ProductUnit)
            .filter(ProductUnit.product_id.in_(ids), ProductUnit.company_id == company_id)
            .order_by(ProductUnit.ratio.desc(), ProductUnit.sort_order.asc(), ProductUnit.id.asc())
        ):
            units_by[u.product_id].append(u)
    pack_qty = {}
    if ids:
        pack_qty = {pid: q for pid, q in db.query(ProductPharma.product_id, ProductPharma.pack_qty).filter(
            ProductPharma.product_id.in_(ids), ProductPharma.company_id == company_id) if q and int(q) > 0}
    packs = {}
    for pid in ids:
        if pid in pack_qty:
            packs[pid] = Decimal(int(pack_qty[pid]))
        elif units_by[pid]:
            packs[pid] = max(Decimal(str(u.ratio)) for u in units_by[pid])
    loose = loose_units_by_product(db, company_id, packs, wh_ids)
    code = (search or "").strip()
    out = {}
    for p in products:
        units = units_by[p.id]
        pack = packs.get(p.id)
        base_price = prices[p.id][0]
        disp = stock_display_of(
            stock_map.get(p.id, 0.0), loose.get(p.id, 0), pack, pack_unit_name(units, pack), p.unit or "dona",
        )
        out[p.id] = {
            "units": [
                {"id": u.id, "name": u.name, "ratio": float(u.ratio),
                 "sale_price": float(u.sale_price) if u.sale_price is not None else None,
                 "price": float(unit_list_price(u, units, base_price, pack, price_round)), "barcode": u.barcode}
                for u in units
            ],
            "pack_ratio": float(pack) if pack else None,
            "scanned_unit_id": next((u.id for u in units if code and u.barcode == code), None),
            **disp,
        }
    return out


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

    pharma_on, pharma_settings = pharmacy_context(db, current_user.company_id)  # D2.3
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
            q = q.filter(product_search_filter(search, current_user.company_id, pharma_on))
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
    pharma_extra = _pharmacy_pos_extras(db, product_ids, wh_ids, pharma_settings) if pharma_on else None
    if pharma_on:
        # D2.4: qadoq birliklari, birlik shtrix-kodi va "2 quti 5 dona" ko'rinishidagi qoldiq
        _unit_extra = _pharmacy_unit_extras(
            db, current_user.company_id, products_raw, prices, stock_map, wh_ids, search,
            price_round=pharma_settings.get("price_round") or 0)
        for _pid, _ex in _unit_extra.items():
            pharma_extra[_pid].update(_ex)

    result = [
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
    if pharma_extra is not None:
        # D2.3: faqat dorixona rejimida qo'shimcha maydonlar (oddiy korxonada javob o'zgarmaydi)
        for row in result:
            row.update(pharma_extra[row["id"]])
    return result


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
    substance_id: Optional[int] = Query(None, description="Dorixona: ta'sir etuvchi modda bo'yicha (oddiy korxonada e'tiborsiz)"),
    manufacturer: Optional[str] = Query(None, description="Dorixona: ishlab chiqaruvchi nomi bo'yicha (qismi, oddiy korxonada e'tiborsiz)"),
    is_rx: Optional[bool] = Query(None, description="Dorixona: retseptli/retseptsiz (oddiy korxonada e'tiborsiz)"),
    control_class: Optional[str] = Query(None, description="Dorixona: nazorat toifasi (oddiy korxonada e'tiborsiz)"),
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

    # D2.4: dorixona konteksti faqat kerak bo'lganda (qidiruv bor yoki natija bo'sh emas), bir marta olinadi
    pharma_ctx = None
    _ph_filters = substance_id is not None or bool((manufacturer or "").strip()) or is_rx is not None or bool(control_class)
    if search or _ph_filters:
        pharma_ctx = pharmacy_context(db, current_user.company_id)
    if search:
        q = q.filter(product_search_filter(search, current_user.company_id, pharma_ctx[0]))
    # CD.1: dorixona filtrlari — faqat modul yoqilgan korxonada qo'llanadi (oddiy korxonada e'tiborsiz)
    if _ph_filters and pharma_ctx[0]:
        _pc = [ProductPharma.product_id == Product.id, ProductPharma.company_id == current_user.company_id]
        if (manufacturer or "").strip():
            _pc.append(ProductPharma.manufacturer.ilike(f"%{manufacturer.strip()}%"))
        if is_rx is not None:
            _pc.append(ProductPharma.is_rx == is_rx)
        if control_class:
            _pc.append(ProductPharma.control_class == control_class)
        if substance_id is not None:
            q = q.filter(exists().where(
                ProductSubstance.product_id == Product.id, ProductSubstance.substance_id == substance_id,
            ))
        if len(_pc) > 2:
            q = q.filter(exists().where(*_pc))
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

    from sqlalchemy import or_ as _or_
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

    if items and pharma_ctx is None:
        pharma_ctx = pharmacy_context(db, current_user.company_id)
    pharma_on, pharma_settings = pharma_ctx if pharma_ctx is not None else (False, {})
    if pharma_on and items:
        # D2.4: dorixona rejimida qoldiq qadoq bo'yicha ("2 quti 5 dona"), full_boxes, loose_units va birliklar.
        # Oddiy korxonada javob o'zgarmaydi.
        _wh_for_loose = [warehouse_id] if warehouse_id else (
            list(branch_wh_set) if branch_wh_set is not None else list(warehouses.keys()))
        _extra = _pharmacy_unit_extras(
            db, current_user.company_id, products,
            {p.id: (float(p.sale_price or 0),) for p in products},
            {it["id"]: float(it.get("stock_quantity") or 0) for it in items},
            _wh_for_loose, None, price_round=pharma_settings.get("price_round") or 0)
        for it in items:
            it.update(_extra[it["id"]])
        # CD.1: dori bloki (moddalari bilan) — bitta-ikkita so'rovda, N+1 yo'q
        from app.routers.products import _load_pharma_map
        _pm = _load_pharma_map(db, current_user.company_id, [it["id"] for it in items])
        for it in items:
            _po = _pm.get(it["id"])
            it["pharma"] = _po.model_dump() if _po is not None else None
        # P.8: eng yaqin muddatli partiya (seriya, yaroqlilik muddati, ishlab chiqarilgan sana) — Excel'ga yuklab olish
        # uchun; bitta so'rov (N+1 yo'q), qoldig'i bor partiyalar, muddatsizlari oxirida
        _nb: dict = {}
        if _wh_for_loose:
            for pid, lot, exp, mfg in (
                db.query(Batch.product_id, Batch.lot_number, Batch.expiry_date, Batch.manufacture_date)
                .filter(Batch.product_id.in_([it["id"] for it in items]), Batch.quantity > 0,
                        Batch.warehouse_id.in_(list(_wh_for_loose)))
                .order_by(Batch.product_id, Batch.expiry_date.is_(None), Batch.expiry_date, Batch.id)
            ):
                _nb.setdefault(pid, {
                    "lot_number": lot,
                    "expiry_date": (exp.date() if hasattr(exp, "date") else exp).isoformat() if exp else None,
                    "manufacture_date": (mfg.date() if hasattr(mfg, "date") else mfg).isoformat() if mfg else None,
                })
        for it in items:
            it["nearest_batch"] = _nb.get(it["id"])

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
        q = q.filter(product_search_filter(
            search, current_user.company_id, pharmacy_context(db, current_user.company_id)[0]))
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


def _norm_strength(v) -> Optional[str]:
    """Doza solishtirish uchun: '500 mg' == '500MG' == '500mg'; bo'sh -> None."""
    t = re.sub(r"\s+", "", (v or "").lower())
    return t or None


@router.get("/{product_id}/analogs")
def product_analogs(
    product_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Dori analoglari (D2.3): ta'sir etuvchi moddalar to'plami AYNAN bir xil, dori shakli va dozasi mos
    faol mahsulotlar (shu korxonaniki). Joriy filial omborlarida yaroqli qoldig'i borlar avval, keyin arzonlari.

    Faqat dorixona rejimida; modul o'chiq korxonada 404 qaytadi. Mahsulot topilmasa / boshqa korxonaniki — 404.
    Moddasi bog'lanmagan mahsulotda analog yo'q (bo'sh ro'yxat).
    Har bir element: `stock_quantity` (joriy filial omborlari qoldig'i), `valid_quantity` (muddati o'tgan/bloklangan
    partiyalarsiz), `in_stock`, `sale_price` (filial narxi bo'lsa shu), `nearest_expiry`, `expiry_warn`.
    """
    from app.core.branch_context import effective_branch_id
    from app.services.branch_price_service import get_branch_prices

    company_id = current_user.company_id
    enabled, settings = pharmacy_context(db, company_id)
    if not enabled:
        raise HTTPException(status_code=404, detail="Dorixona rejimi yoqilmagan")
    product = db.query(Product.id).filter(
        Product.id == product_id, Product.company_id == company_id, Product.is_deleted == False,  # noqa: E712
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")

    sub_ids = [r[0] for r in db.query(ProductSubstance.substance_id).filter(ProductSubstance.product_id == product_id)]
    if not sub_ids:
        return []
    target = db.query(ProductPharma.dosage_form, ProductPharma.strength).filter(
        ProductPharma.product_id == product_id).first()
    t_form = target[0] if target else None
    t_strength = _norm_strength(target[1]) if target else None

    # moddalar to'plami aynan teng: soni teng va hammasi maqsad to'plamida (juftlik UNIQUE) — bitta so'rov
    same_set = (
        select(ProductSubstance.product_id)
        .group_by(ProductSubstance.product_id)
        .having(
            func.count() == len(sub_ids),
            func.sum(case((ProductSubstance.substance_id.in_(sub_ids), 1), else_=0)) == len(sub_ids),
        )
    )
    cand_q = (
        db.query(Product, ProductPharma)
        .outerjoin(ProductPharma, ProductPharma.product_id == Product.id)
        .filter(
            Product.company_id == company_id, Product.is_deleted == False,  # noqa: E712
            Product.status == ProductStatus.active, Product.id != product_id,
            Product.id.in_(same_set),
        )
    )
    cand_q = cand_q.filter(ProductPharma.dosage_form == t_form) if t_form else cand_q.filter(
        ProductPharma.dosage_form.is_(None))
    cands = [(p, ph) for p, ph in cand_q.all() if _norm_strength(ph.strength if ph else None) == t_strength]
    if not cands:
        return []

    ids = [p.id for p, _ in cands]
    wh_ids = sellable_warehouse_ids(db, company_id, branch_ids=ctx.scope_ids())
    stock_map = stock_totals(db, ids, wh_ids)
    cutoff = expiry_cutoff(tashkent_today(), settings.get("expiry_block_days") or 0)
    expired_map = {}
    if wh_ids:
        expired_map = {
            pid: Decimal(str(q or 0))
            for pid, q in db.query(Batch.product_id, func.sum(Batch.quantity))
            .filter(Batch.product_id.in_(ids), Batch.warehouse_id.in_(wh_ids), Batch.quantity > 0,
                    Batch.expiry_date.isnot(None), Batch.expiry_date < cutoff)
            .group_by(Batch.product_id)
        }
    nearest = _nearest_valid_expiry(db, ids, wh_ids, settings)
    warn_until = tashkent_today() + timedelta(days=int(settings.get("expiry_warn_days") or 0))
    price_branch_id = effective_branch_id(db, current_user)
    branch_prices = get_branch_prices(db, company_id, price_branch_id, ids)

    items = []
    for p, ph in cands:
        stock = stock_map.get(p.id, Decimal("0"))
        valid = max(stock - expired_map.get(p.id, Decimal("0")), Decimal("0"))
        bp = branch_prices.get((p.id, None))
        sale = float(bp.sale_price) if bp is not None and bp.sale_price is not None else float(p.sale_price or 0)
        exp = nearest.get(p.id)
        items.append({
            "id": p.id,
            "name": p.name,
            "barcode": p.barcode,
            "unit": p.unit,
            "sale_price": sale,
            "sale_currency": p.sale_currency or "UZS",
            "price_source": "branch" if bp is not None else "product",
            "stock_quantity": float(stock),
            "valid_quantity": float(valid),
            "in_stock": valid > 0,
            "nearest_expiry": exp.isoformat() if exp else None,
            "expiry_warn": bool(exp and exp <= warn_until),
            "dosage_form": ph.dosage_form if ph else None,
            "strength": ph.strength if ph else None,
            "manufacturer": ph.manufacturer if ph else None,
            "is_rx": bool(ph.is_rx) if ph else False,
            "control_class": (ph.control_class if ph else None) or "none",
        })
    # yaroqli qoldig'i borlar avval, keyin arzonlari (barqaror: nom, id)
    items.sort(key=lambda i: (0 if i["in_stock"] else 1, i["sale_price"], i["name"] or "", i["id"]))
    return items[:limit]
