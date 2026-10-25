import json
import random
import string
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action
from app.core.branch_context import BranchContext, get_branch_context, warehouse_ids_for_ctx
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.inventory import StockLevel
from app.models.product import Product, ProductConversion, ProductStatus
from app.models.user import User, UserRole
from app.schemas.product import ProductCreate, ProductListOut, ProductOut, ProductStatusUpdate, ProductUpdate
from app.services.pharmacy import pharmacy_context, pharmacy_enabled
from app.utils.image_pipeline import reconcile_product

router = APIRouter(prefix="/products", tags=["Products"])

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)

from app.utils.product_filters import name_filter as _name_filter  # noqa: E402


def _load_pharma_map(db: Session, company_id, product_ids) -> dict:
    """D2.1: mahsulotlarning dori bloklarini (moddalari bilan) bitta-ikkita so'rovda yuklaydi — N+1 yo'q.
    Faqat dorixona rejimi yoqilgan korxona uchun chaqiriladi. {product_id: PharmaOut}."""
    from collections import defaultdict
    from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
    from app.schemas.product import PharmaOut, PharmaSubstanceOut
    ids = list(product_ids)
    if not ids:
        return {}
    rows = db.query(ProductPharma).filter(
        ProductPharma.company_id == company_id, ProductPharma.product_id.in_(ids),
    ).all()
    if not rows:
        return {}
    subs = defaultdict(list)
    for pid, sub in (
        db.query(ProductSubstance.product_id, PharmaSubstance)
        .join(PharmaSubstance, PharmaSubstance.id == ProductSubstance.substance_id)
        .filter(ProductSubstance.product_id.in_([r.product_id for r in rows]))
        .order_by(PharmaSubstance.name_uz)
        .all()
    ):
        subs[pid].append(PharmaSubstanceOut.model_validate(sub))
    result = {}
    for r in rows:
        out = PharmaOut.model_validate(r)
        out.substances = subs.get(r.product_id, [])
        result[r.product_id] = out
    return result


def _assert_max_markup(settings: dict, cost_price, sale_price) -> None:
    """CD.1: dorixona — sotuv narxi `max_markup_pct` ustamadan oshmasin. Faqat dorixona rejimida chaqiriladi;
    chegara 0 yoki tannarx 0 bo'lsa o'tkazib yuboriladi."""
    max_pct = int((settings or {}).get("max_markup_pct") or 0)
    cost = Decimal(str(cost_price or 0))
    sale = Decimal(str(sale_price or 0))
    if max_pct <= 0 or cost <= 0 or sale <= 0:
        return
    if sale > cost * (Decimal(100) + Decimal(max_pct)) / Decimal(100):
        raise HTTPException(
            status_code=400, detail=f"Sotuv narxi ruxsat etilgan ustamadan ({max_pct}%) oshib ketdi",
        )


def _save_pharma(db: Session, company_id, product_id: int, pharma_in) -> None:
    """D2.1: mahsulotning dori blokini saqlaydi (faqat dorixona rejimida chaqiriladi).
    Faqat yuborilgan maydonlar yangilanadi; substance_ids berilsa moddalar to'liq almashtiriladi."""
    from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
    fields = pharma_in.model_dump(exclude_unset=True)
    raw_ids = fields.pop("substance_ids", None)
    if fields.get("is_rx", True) is None:
        fields.pop("is_rx")
    if "control_class" in fields and fields["control_class"] is None:
        fields["control_class"] = "none"

    new_ids = None
    if raw_ids is not None:
        new_ids = list(dict.fromkeys(raw_ids))
        if new_ids:
            # umumiy (company_id NULL) yoki o'z korxonasi moddalari; begonasi ko'rinmaydi
            found = {
                sid for (sid,) in db.query(PharmaSubstance.id).filter(
                    PharmaSubstance.id.in_(new_ids),
                    (PharmaSubstance.company_id.is_(None)) | (PharmaSubstance.company_id == company_id),
                ).all()
            }
            missing = [i for i in new_ids if i not in found]
            if missing:
                raise HTTPException(status_code=404, detail=f"Modda topilmadi: {missing[0]}")

    row = db.query(ProductPharma).filter(ProductPharma.product_id == product_id).first()
    if row is None:
        row = ProductPharma(product_id=product_id, company_id=company_id)
        db.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    db.flush()

    if new_ids is not None:
        existing = {
            ps.substance_id: ps
            for ps in db.query(ProductSubstance).filter(ProductSubstance.product_id == product_id).all()
        }
        for sid, ps in existing.items():
            if sid not in new_ids:
                db.delete(ps)
        for sid in new_ids:
            if sid not in existing:
                db.add(ProductSubstance(product_id=product_id, substance_id=sid))
        db.flush()



# ── P.1: qadoq tuzilmasi (ProductUnit) va boshlang'ich qoldiq seriyasi — faqat dorixona rejimida ──
def _load_units_map(db: Session, company_id, product_ids) -> dict:
    """P.1: mahsulotlarning qadoq birliklarini BITTA so'rovda yuklaydi (N+1 yo'q), ratio o'sish tartibida.
    Faqat dorixona rejimi yoqilgan korxona uchun chaqiriladi. {product_id: [ProductUnitOut]}."""
    from collections import defaultdict
    from app.models.product_units import ProductUnit
    from app.schemas.product import ProductUnitOut
    ids = list(product_ids)
    if not ids:
        return {}
    result = defaultdict(list)
    for u in db.query(ProductUnit).filter(
        ProductUnit.company_id == company_id, ProductUnit.product_id.in_(ids),
    ).order_by(ProductUnit.product_id, ProductUnit.ratio, ProductUnit.id).all():
        result[u.product_id].append(ProductUnitOut(
            id=u.id, name=u.name, ratio=int(u.ratio),
            sale_price=float(u.sale_price) if u.sale_price is not None else None, barcode=u.barcode,
        ))
    return dict(result)


def _clean_units(units_in) -> list:
    """P.1: yuborilgan birliklarni tekshiradi (400, o'zbekcha) va [{name, ratio:int, sale_price, barcode}] qaytaradi,
    ratio o'sish tartibida. Nomlar va nisbatlar takrorlanmaydi, nisbat butun son > 1, narx >= 0."""
    out: list = []
    names: set = set()
    ratios: set = set()
    barcodes: set = set()
    for u in units_in or []:
        name = " ".join((u.name or "").split())
        if not name:
            raise HTTPException(status_code=400, detail="Qadoq birligi nomi bo'sh bo'lmasligi kerak")
        if len(name) > 50:
            raise HTTPException(status_code=400, detail=f"Qadoq nomi 50 belgidan oshmasligi kerak: {name[:20]}...")
        ratio = Decimal(str(u.ratio))
        if not ratio.is_finite() or ratio != ratio.to_integral_value() or ratio <= 1:
            raise HTTPException(status_code=400, detail=f"'{name}': nisbat 1 dan katta butun son bo'lishi kerak")
        if ratio > Decimal("1000000"):
            raise HTTPException(status_code=400, detail=f"'{name}': nisbat juda katta")
        if name.casefold() in names:
            raise HTTPException(status_code=400, detail=f"'{name}' qadoq nomi takrorlangan")
        if int(ratio) in ratios:
            raise HTTPException(status_code=400, detail=f"Bir xil nisbatli ({int(ratio)}) ikkita qadoq bo'lishi mumkin emas")
        price = None
        if u.sale_price is not None:
            price = Decimal(str(u.sale_price))
            if not price.is_finite() or price < 0:
                raise HTTPException(status_code=400, detail=f"'{name}': narx manfiy bo'lishi mumkin emas")
        barcode = (u.barcode or "").strip() or None
        if barcode:
            if len(barcode) > 100:
                raise HTTPException(status_code=400, detail=f"'{name}': shtrix-kod 100 belgidan oshmasligi kerak")
            if barcode in barcodes:
                raise HTTPException(status_code=400, detail=f"Shtrix-kod {barcode} qadoqlarda takrorlangan")
            barcodes.add(barcode)
        names.add(name.casefold())
        ratios.add(int(ratio))
        out.append({"name": name, "ratio": int(ratio), "sale_price": price, "barcode": barcode})
    out.sort(key=lambda x: x["ratio"])
    return out


def _check_unit_barcodes(db: Session, company_id, units: list, product_id: Optional[int] = None,
                         own_barcodes=()) -> None:
    """P.1: birlik shtrix-kodi korxona ichida noyob: mahsulotlarning asosiy shtrix-kodlari (shu mahsulotniki ham) va
    boshqa mahsulotlar birliklari bilan to'qnashmasin. `product_id` berilsa, uning o'z birliklari tekshirilmaydi
    (ular almashtiriladi). `own_barcodes` — hali saqlanmagan shu mahsulotning shtrix-kodlari (yaratishda)."""
    from app.models.product_units import ProductUnit
    own = {b for b in own_barcodes if b}
    for u in units:
        bc = u["barcode"]
        if not bc:
            continue
        if bc in own or db.query(Product.id).filter(
            Product.company_id == company_id, Product.barcode == bc, Product.is_deleted == False,  # noqa: E712
        ).first():
            raise HTTPException(status_code=400, detail=f"Shtrix-kod {bc} mahsulot shtrix-kodi sifatida ishlatilgan")
        q = db.query(ProductUnit.id).filter(ProductUnit.company_id == company_id, ProductUnit.barcode == bc)
        if product_id:
            q = q.filter(ProductUnit.product_id != product_id)
        if q.first():
            raise HTTPException(status_code=400, detail=f"Shtrix-kod {bc} boshqa birlikda ishlatilgan")


def _sync_units(db: Session, company_id, product_id: int, units: list) -> None:
    """P.1: mahsulotning ProductUnit qatorlarini `units` (`_clean_units` natijasi) ga TO'LIQ almashtiradi:
    yo'qlari o'chiriladi, borlari nomi bo'yicha yangilanadi, yangilari qo'shiladi."""
    from app.models.product_units import ProductUnit
    existing = db.query(ProductUnit).filter(ProductUnit.product_id == product_id).all()
    by_name = {e.name.casefold(): e for e in existing}
    keep = {u["name"].casefold() for u in units}
    for e in existing:
        if e.name.casefold() not in keep:
            db.delete(e)
        elif e.barcode:
            e.barcode = None   # shtrix-kod almashinuvida (uq cheklovi) vaqtinchalik to'qnashuv bo'lmasin
    db.flush()
    for idx, u in enumerate(units):
        row = by_name.get(u["name"].casefold())
        if row is None:
            row = ProductUnit(product_id=product_id, company_id=company_id)
            db.add(row)
        row.name, row.ratio, row.sale_price, row.barcode, row.sort_order = (
            u["name"], u["ratio"], u["sale_price"], u["barcode"], idx,
        )
    db.flush()


def _fill_pack_qty(db: Session, company_id, product_id: int, units: list) -> None:
    """P.1: `pharma.pack_qty` bo'sh bo'lsa eng katta qadoq nisbati bilan to'ldiriladi (quti = shuncha dona)."""
    if not units:
        return
    from app.models.product_pharma import ProductPharma
    from app.schemas.product import PharmaIn
    cur = db.query(ProductPharma.pack_qty).filter(ProductPharma.product_id == product_id).scalar()
    if cur and int(cur) > 0:
        return
    _save_pharma(db, company_id, product_id, PharmaIn(pack_qty=max(u["ratio"] for u in units)))


def _initial_batch_dates(data, pharmacy_on: bool) -> dict:
    """P.1: boshlang'ich qoldiq Batch'iga muddat/ishlab chiqarilgan sana (faqat dorixonada; oddiy korxonada muddatsiz)."""
    if not pharmacy_on:
        return {}
    from datetime import datetime as _dt
    return {
        "expiry_date": _dt.combine(data.initial_expiry_date, _dt.min.time()) if data.initial_expiry_date else None,
        "manufacture_date": (
            _dt.combine(data.initial_manufacture_date, _dt.min.time()) if data.initial_manufacture_date else None
        ),
    }


def _validate_initial_lot(data) -> None:
    """P.1: dorixonada boshlang'ich qoldiq bo'lsa yaroqlilik muddati (bugundan keyin) majburiy.
    P.5: seriya raqami ixtiyoriy (bo'sh bo'lsa partiya `initial-<id>` nomini oladi)."""
    if data.initial_expiry_date is None:
        raise HTTPException(status_code=400, detail="Dorixona rejimida boshlang'ich qoldiq uchun yaroqlilik muddati majburiy")
    from app.services.batch_allocator import tashkent_today
    if data.initial_expiry_date <= tashkent_today():
        raise HTTPException(status_code=400, detail="Yaroqlilik muddati bugundan keyingi sana bo'lishi kerak")
    if data.initial_manufacture_date and data.initial_manufacture_date >= data.initial_expiry_date:
        raise HTTPException(status_code=400, detail="Ishlab chiqarilgan sana yaroqlilik muddatidan oldin bo'lishi kerak")


def _attach_stock(product: Product, db: Session = None, warehouse_id: int = None, wh_scope=None) -> ProductOut:
    """`wh_scope` (T2.3): ko'rinadigan omborlar to'plami (filialga biriktirilgan xodim uchun o'z filiali
    omborlari); `None` — cheklov yo'q, bo'sh to'plam — hech narsa (qoldiq 0)."""
    out = ProductOut.model_validate(product)
    if product.category:
        out.category_name = product.category.name

    out.stock_quantity = Decimal("0")
    if db:
        from app.models.inventory import StockLevel
        from sqlalchemy import func
        from app.models.warehouse import Warehouse
        q = db.query(func.coalesce(func.sum(StockLevel.quantity), 0)).outerjoin(
            Warehouse, Warehouse.id == StockLevel.warehouse_id,
        ).filter(
            StockLevel.product_id == product.id,
            # T1.12: arxivlangan (nofaol) ombor qoldig'i jamga qo'shilmaydi
            StockLevel.warehouse_id.is_(None) | Warehouse.is_active.isnot(False),
        )
        if warehouse_id:
            q = q.filter(StockLevel.warehouse_id == warehouse_id)
        if wh_scope is not None:
            q = q.filter(StockLevel.warehouse_id.in_(list(wh_scope)))
        total_qty = q.scalar()
        if total_qty is not None:
            out.stock_quantity = Decimal(str(total_qty))
    elif product.stock_level:
        out.stock_quantity = product.stock_level.quantity

    
    if product.product_type == 'parent' and db:
        from app.models.product_variant import ProductVariant
        from app.models.attribute import AttributeValue, VariantAttributeValue
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
    # D2.1: dori bloki faqat dorixona rejimida; oddiy korxonada pharma = null
    if db and pharmacy_enabled(db, product.company_id):
        out.pharma = _load_pharma_map(db, product.company_id, [product.id]).get(product.id)
        out.units = _load_units_map(db, product.company_id, [product.id]).get(product.id, [])   # P.1
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

    # T3.8: barcha variantlar qoldig'i BITTA GROUP BY so'rovi bilan (sikl ichida so'rov yo'q)
    stock_by_variant: dict = {}
    if children:
        from sqlalchemy import func
        sq = db.query(StockLevel.variant_id, func.sum(StockLevel.quantity)).filter(
            StockLevel.variant_id.in_([c.id for c in children]),
            StockLevel.product_id == product_id,
        )
        if warehouse_id:
            sq = sq.filter(StockLevel.warehouse_id == warehouse_id)
        stock_by_variant = {vid: float(qty or 0) for vid, qty in sq.group_by(StockLevel.variant_id).all()}

    result = []
    for c in children:
        color = next((val.attribute_value.value for val in c.attribute_values
                      if val.attribute_value.attribute.name in ("Rang", "Color")), None)
        size = next((val.attribute_value.value for val in c.attribute_values
                     if val.attribute_value.attribute.name in ("O'lcham", "Size")), None)

        stock_qty = stock_by_variant.get(c.id, 0.0)

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
        page: Optional[int] = Query(None, ge=1, description="Sahifa raqami (berilsa skip = (page-1)*limit)"),
        limit: int = Query(50, ge=1, le=20000),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        ctx: BranchContext = Depends(get_branch_context),
):
    from app.models.inventory import StockLevel
    from app.models.warehouse import Warehouse
    from app.schemas.product import WarehouseStockOut

    if page is not None:
        skip = (page - 1) * limit

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
        # Only products that have stock in this warehouse (EXISTS: variantli mahsulot qatorlari ko'paymasin)
        from sqlalchemy import exists
        q = q.filter(exists().where(StockLevel.product_id == Product.id, StockLevel.warehouse_id == warehouse_id))

    products = q.order_by(Product.name).offset(skip).limit(limit).all()

    # D2.1: dori bloklari faqat dorixona rejimida va bitta so'rovda (N+1 yo'q)
    pharma_on = bool(products) and pharmacy_enabled(db, current_user.company_id)
    pharma_map = _load_pharma_map(db, current_user.company_id, [p.id for p in products]) if pharma_on else {}
    units_map = _load_units_map(db, current_user.company_id, [p.id for p in products]) if pharma_on else {}   # P.1

    # T1.1: ko'rinadigan omborlar yagona filial kontekstidan (None → cheklov yo'q)
    branch_wh_set = warehouse_ids_for_ctx(db, ctx)

    # P.10: dorixonada muddat ma'lumoti (POS desktop shu ro'yxatdan oladi) — web kassa (pos-list) bilan bir xil hisob
    expiry_map: dict = {}
    if pharma_on:
        from app.models.warehouse import Warehouse as _Wh
        from app.routers.product_search import _pharmacy_pos_extras
        if warehouse_id:
            _wh_ids = [warehouse_id]
        else:
            _whq = db.query(_Wh.id).filter(_Wh.company_id == current_user.company_id, _Wh.is_active.isnot(False))
            _wh_ids = [w for (w,) in _whq.all() if branch_wh_set is None or w in branch_wh_set]
        _, _ph_settings = pharmacy_context(db, current_user.company_id)
        expiry_map = _pharmacy_pos_extras(db, [p.id for p in products], _wh_ids, _ph_settings)

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

    result = []
    for p in products:
        item = ProductListOut.model_validate(p)
        if pharma_map:
            item.pharma = pharma_map.get(p.id)
        if units_map:
            item.units = units_map.get(p.id, [])
        if pharma_on and p.id in expiry_map:   # P.10
            _ex = expiry_map[p.id]
            item.nearest_expiry = _ex.get("nearest_expiry")
            item.expiry_warn = bool(_ex.get("expiry_warn"))
            item.expired_qty = float(_ex.get("expired_qty") or 0)

        all_stocks = stock_by_product[p.id]  # bazaga murojaat yo'q, xotiradan olamiz

        # Filter stocks to branch warehouses for non-admins
        visible_stocks = all_stocks
        if branch_wh_set is not None:
            visible_stocks = [s for s in all_stocks if s.warehouse_id in branch_wh_set]  # type: ignore[operator]

        # Variantli mahsulotda har bir variant alohida StockLevel qatoriga ega,
        # shuning uchun bir xil ombor bo'yicha miqdorlarni yig'ib ko'rsatamiz
        # (aks holda bitta ombor bir nechta variant sonicha takrorlanib ko'rinadi)
        wh_totals: dict = defaultdict(lambda: Decimal("0"))
        for s in visible_stocks:
            if s.warehouse_id is not None:
                wh_totals[s.warehouse_id] += s.quantity

        item.warehouse_stocks = [
            WarehouseStockOut(
                warehouse_id=wh_id,
                warehouse_name=warehouses.get(wh_id, f"Ombor#{wh_id}"),
                quantity=qty,
            )
            for wh_id, qty in wh_totals.items()
        ]

        # stock_quantity: if warehouse_id filter active → show that warehouse's qty, else sum visible
        if warehouse_id:
            # variantli mahsulot: tanlangan ombordagi barcha variantlar yig'indisi
            item.stock_quantity = sum((s.quantity for s in all_stocks if s.warehouse_id == warehouse_id), Decimal("0"))
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


@router.get("/barcode-limit")
def get_barcode_limit_stats(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """Kompaniya shtrix-kod limiti va ishlatilganlik ko'rsatkichi (used / limit)."""
    from app.services.tariff_guard import get_company_barcode_stats
    return get_company_barcode_stats(db, current_user.company_id)


@router.get("/barcode/{barcode}", response_model=ProductOut)
def get_by_barcode(
        barcode: str,
        warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filter (ixtiyoriy)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        ctx: BranchContext = Depends(get_branch_context),
):
    base_filter = [
        Product.is_deleted == False,
        Product.status == ProductStatus.active,
        Product.company_id == current_user.company_id,
    ]
    # Asosiy barcode bo'yicha qidirish
    product = db.query(Product).filter(*base_filter, Product.barcode == barcode).first()
    # T3.12: tarozi PLU kodi (<=5 raqam) — indeksli qidiruv (korxona ichida unikal plu_code)
    if not product and barcode.isdigit() and len(barcode) <= 5 and int(barcode) > 0:
        product = db.query(Product).filter(*base_filter, Product.plu_code == int(barcode)).first()
    # Topilmasa extra_barcodes JSON ichida qidirish (%"{barcode}"%)
    if not product:
        product = (
            db.query(Product)
            .filter(*base_filter, Product.extra_barcodes.ilike(f'%"{barcode}"%'))
            .first()
        )
    # Topilmasa mahsulot variantlari shtrix-kodi bo'yicha qidirish
    if not product:
        from app.models.product_variant import ProductVariant
        variant = (
            db.query(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(*base_filter, ProductVariant.barcode == barcode)
            .first()
        )
        if variant:
            product = variant.product
    # Topilmasa SKU bo'yicha qidirish
    if not product:
        product = db.query(Product).filter(*base_filter, Product.sku == barcode).first()
    # Topilmasa SKU leading zeros olib qidirish (masalan '00001' => '1' yoki aksi)
    if not product:
        stripped = barcode.lstrip('0')
        if stripped:
            product = db.query(Product).filter(*base_filter, Product.sku == stripped).first()
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

    return _attach_stock(product, db=db, warehouse_id=warehouse_id, wh_scope=warehouse_ids_for_ctx(db, ctx))


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
        product_id: int,
        warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha filter (ixtiyoriy)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        ctx: BranchContext = Depends(get_branch_context),
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
    return _attach_stock(product, db=db, warehouse_id=warehouse_id, wh_scope=warehouse_ids_for_ctx(db, ctx))


def _generate_sku(db: Session) -> str:
    for _ in range(20):
        sku = "SKU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        q = db.query(Product).filter(Product.sku == sku)
        if q.first():
            continue
        return sku
    return "SKU-" + "".join(random.choices(string.digits, k=8))


# T3.12: tarozi (tortiladigan) birliklari va PLU diapazoni
SCALE_UNITS = ("kg", "g")
PLU_MIN, PLU_MAX = 1, 99999


def _assign_plu(db: Session, company_id, product: Product, requested: Optional[int] = None) -> Optional[int]:
    """Mahsulotga tarozi PLU kodini beradi (korxona ichida unikal, 1..99999).

    - `requested` berilsa: band bo'lsa 409, aks holda shu raqam beriladi.
    - berilmasa va birligi kg/g bo'lib `plu_code` bo'sh bo'lsa: korxonadagi eng kichik bo'sh raqam.
    O'chirilgan mahsulotlar PLU ni band qilmaydi (unikal indeks ham faqat faollar uchun)."""
    own_id = getattr(product, "id", None)
    base = db.query(Product).filter(Product.company_id == company_id, Product.is_deleted == False)  # noqa: E712
    if own_id is not None:
        base = base.filter(Product.id != own_id)

    if requested is not None:
        if requested < PLU_MIN or requested > PLU_MAX:
            raise HTTPException(status_code=400, detail=f"PLU kodi {PLU_MIN}-{PLU_MAX} oralig'ida bo'lishi kerak")
        busy = base.filter(Product.plu_code == requested).first()
        if busy:
            raise HTTPException(status_code=409, detail=f"PLU kodi band: {busy.name}")
        product.plu_code = requested
        return requested

    if product.plu_code or (product.unit or "").strip().lower() not in SCALE_UNITS:
        return product.plu_code

    taken = [r[0] for r in base.filter(Product.plu_code.isnot(None))
             .with_entities(Product.plu_code).order_by(Product.plu_code).all()]
    free = PLU_MIN
    for code in taken:
        if code < free:
            continue
        if code == free:
            free += 1
        else:
            break
    if free > PLU_MAX:
        raise HTTPException(status_code=409, detail="Bo'sh PLU kodi qolmadi (1-99999)")
    product.plu_code = free
    return free


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
        data: ProductCreate,
        request: Request,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),  # T1.5: X-Branch-Id -> boshlang'ich qoldiq filiali (db.info)
):
    # D2.1: dorixona rejimida MXIK kodi majburiy (oddiy korxonada o'zgarishsiz)
    pharmacy_on, _ph_settings = pharmacy_context(db, current_user.company_id)
    if pharmacy_on and not (data.mxik_code or "").strip():
        raise HTTPException(status_code=400, detail="Dorixona rejimida MXIK kodi majburiy")
    if pharmacy_on:
        _assert_max_markup(_ph_settings, data.cost_price, data.sale_price)   # CD.1: ustama chegarasi

    extra_count = len([b.strip() for b in (data.extra_barcodes or []) if b.strip()])
    variant_count = len([v for v in (data.variants or []) if getattr(v, 'barcode', None) and v.barcode.strip()])
    total_new_barcodes = 1 + extra_count + variant_count
    from app.services.tariff_guard import check_product_limit
    check_product_limit(db, current_user.company_id, count_to_add=total_new_barcodes)

    # Extract non-model fields before dump
    initial_stock = data.initial_stock or Decimal("0")
    initial_warehouse_id = data.initial_warehouse_id
    conversion_data = data.conversion
    product_data = data.model_dump(exclude={
        "initial_stock", "initial_warehouse_id", "conversion", "variants", "pharma",
        "units", "initial_lot_number", "initial_expiry_date", "initial_manufacture_date",   # P.1
    })

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
    requested_plu = product_data.pop("plu_code", None)  # T3.12: _assign_plu orqali beriladi

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

    # T1.5: boshlang'ich qoldiq ombori — berilgan ombor korxona/filial bo'yicha tekshiriladi (404/403),
    # berilmasa filialning default ombori (resolve_warehouse); qoldiq kerak, ammo ombor aniqlanmasa 409/400.
    _variants_in = data.variants if (data.variants and product_type in ("stock", "variant")) else []
    _needs_stock = (
        (not _variants_in and product_type in ("stock", "simple") and initial_stock > 0)
        or any((v.quantity if v.quantity is not None else initial_stock) > 0 for v in _variants_in)
    )
    if initial_warehouse_id or _needs_stock:
        from app.services.warehouse_resolver import resolve_warehouse
        initial_warehouse_id = resolve_warehouse(
            db, current_user.company_id, requested_id=initial_warehouse_id, purpose="receive", user=current_user,
        )

    # P.1: dorixonada qadoq birliklari tekshiriladi (saqlashdan oldin) va boshlang'ich qoldiqqa seriya/muddat majburiy.
    # Oddiy korxonada bu maydonlar e'tiborsiz (hozirgi xatti-harakat).
    units_clean = None
    if pharmacy_on:
        if data.units is not None:
            units_clean = _clean_units(data.units)
            _check_unit_barcodes(
                db, current_user.company_id, units_clean,
                own_barcodes=[data.barcode, *[b.strip() for b in (data.extra_barcodes or [])]],
            )
        if _needs_stock:
            _validate_initial_lot(data)

    product_data.pop("variants", None)
    # attributes va tags None bo'lsa bo'sh list bilan almashtir
    if product_data.get("attributes") is None:
        product_data["attributes"] = []
    if product_data.get("tags") is None:
        product_data["tags"] = []
    product = Product(**product_data)
    # T3.12: kg/g mahsulotga tarozi PLU kodi (berilgan band bo'lsa 409, berilmasa eng kichik bo'sh)
    _assign_plu(db, current_user.company_id, product, requested_plu)
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
                        lot_number=(((data.initial_lot_number or "").strip() or f"initial-variant-{child.id}") if pharmacy_on else f"initial-variant-{child.id}"),
                        initial_quantity=variant_stock_qty,
                        quantity=variant_stock_qty,
                        purchase_price=child.cost_price or product.cost_price or 0,
                        company_id=current_user.company_id,
                        **_initial_batch_dates(data, pharmacy_on),
                    ))

    elif product_type in ("stock", "simple"):
        if initial_warehouse_id and initial_stock > 0:
            stock = StockLevel(product_id=product.id, quantity=initial_stock, warehouse_id=initial_warehouse_id)
            db.add(stock)
            # Batch yozuvi (FIFO uchun)
            from app.models.batch import Batch
            db.add(Batch(
                product_id=product.id,
                warehouse_id=initial_warehouse_id,
                lot_number=(((data.initial_lot_number or "").strip() or f"initial-{product.id}") if pharmacy_on else f"initial-{product.id}"),
                initial_quantity=initial_stock,
                quantity=initial_stock,
                purchase_price=product.cost_price or 0,
                company_id=current_user.company_id,
                **_initial_batch_dates(data, pharmacy_on),
            ))

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

    if pharmacy_on and data.pharma is not None:
        _save_pharma(db, current_user.company_id, product.id, data.pharma)
    if pharmacy_on and units_clean is not None:   # P.1
        _sync_units(db, current_user.company_id, product.id, units_clean)
        _fill_pack_qty(db, current_user.company_id, product.id, units_clean)

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
    if reconcile_product(db.get_bind(), product):  # fon olib tashlash natijasi saqlashdan oldin tayyor bo'lgan
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
    
    # Qoldiq PUT orqali O'ZGARTIRILMAYDI (STOCK-01): eski klientlar yuborgan
    # initial_stock / initial_warehouse_id e'tiborsiz qoldiriladi. Qoldiqni
    # tuzatish faqat inventarizatsiya yoki /inventory/adjust (StockMovement bilan).
    if "initial_stock" in fields_set or "initial_warehouse_id" in fields_set:
        import logging
        logging.getLogger(__name__).warning(
            "PUT /products/%s: initial_stock/initial_warehouse_id e'tiborsiz qoldirildi (user=%s)",
            product_id, current_user.id,
        )

    update_data = data.model_dump(exclude_none=True, exclude={
        "conversion", "initial_stock", "initial_warehouse_id", "variants", "pharma",
        "units", "initial_lot_number", "initial_expiry_date", "initial_manufacture_date",   # P.1
    })

    # D2.1: dorixona rejimida tahrirlanayotgan mahsulotda MXIK kodi majburiy (oddiy korxonada o'zgarishsiz)
    pharmacy_on, _ph_settings = pharmacy_context(db, current_user.company_id)
    if pharmacy_on:
        eff_mxik = update_data["mxik_code"] if "mxik_code" in update_data else product.mxik_code
        if not (eff_mxik or "").strip():
            raise HTTPException(status_code=400, detail="Dorixona rejimida MXIK kodi majburiy")
        # CD.1: faqat sotuv narxi o'zgarganda ustama chegarasi tekshiriladi
        if "sale_price" in update_data and Decimal(str(update_data["sale_price"] or 0)) != Decimal(str(product.sale_price or 0)):
            _assert_max_markup(
                _ph_settings, update_data["cost_price"] if "cost_price" in update_data else product.cost_price,
                update_data["sale_price"],
            )

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

    # P.1: dorixonada qadoq birliklari (berilsa to'liq almashtiriladi) saqlashdan oldin tekshiriladi
    units_clean = None
    if pharmacy_on and data.units is not None:
        units_clean = _clean_units(data.units)
        eff_barcode = update_data["barcode"] if "barcode" in update_data else product.barcode
        eff_extra = update_data["extra_barcodes"] if "extra_barcodes" in update_data else product.extra_barcodes
        if isinstance(eff_extra, str):
            try:
                eff_extra = json.loads(eff_extra)
            except Exception:
                eff_extra = []
        _check_unit_barcodes(
            db, current_user.company_id, units_clean, product_id=product.id,
            own_barcodes=[eff_barcode, *[str(b).strip() for b in (eff_extra or [])]],
        )

    # Serialize images list → JSON string for DB storage
    if "images" in update_data:
        imgs = update_data["images"]
        update_data["images"] = json.dumps(imgs) if imgs is not None else None
        if imgs and not update_data.get("image_url"):
            update_data["image_url"] = imgs[0]

    # Serialize extra_barcodes list → JSON string and check limit delta
    if "extra_barcodes" in update_data:
        ebc = update_data["extra_barcodes"]
        new_ebc_list = [b.strip() for b in ebc if b.strip()] if ebc else []
        old_ebc_list = []
        if product.extra_barcodes:
            try:
                old_ebc_list = json.loads(product.extra_barcodes) if isinstance(product.extra_barcodes, str) else product.extra_barcodes
                if not isinstance(old_ebc_list, list):
                    old_ebc_list = []
            except Exception:
                old_ebc_list = []
        delta_bc = len(new_ebc_list) - len(old_ebc_list)
        if delta_bc > 0:
            from app.services.tariff_guard import check_product_limit
            check_product_limit(db, current_user.company_id, count_to_add=delta_bc)
        update_data["extra_barcodes"] = json.dumps(new_ebc_list) if new_ebc_list else None

    # Serialize extra_product_codes list → JSON string
    if "extra_product_codes" in update_data:
        epc = update_data["extra_product_codes"]
        update_data["extra_product_codes"] = json.dumps([c.strip() for c in epc if c.strip()]) if epc else None

    update_data.pop("variants", None)
    requested_plu = update_data.pop("plu_code", None)  # T3.12
    for field, value in update_data.items():
        setattr(product, field, value)
    # T3.12: PLU — berilgan band bo'lsa 409; birligi kg/g ga o'zgargan va PLU yo'q bo'lsa avtomatik
    _assign_plu(db, current_user.company_id, product, requested_plu)

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

    if pharmacy_on and data.pharma is not None:
        _save_pharma(db, current_user.company_id, product.id, data.pharma)
    if units_clean is not None:   # P.1
        _sync_units(db, current_user.company_id, product.id, units_clean)
        _fill_pack_qty(db, current_user.company_id, product.id, units_clean)

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
    if reconcile_product(db.get_bind(), product):
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


# Mahsulotning ichki `unit` maydoni bilan MXIK paketining unit_name'ini
# moslashtirish uchun (vazn/hajm bo'yicha bir nechta birlik varianti bo'lganda)
_MXIK_UNIT_NAME_MAP = {
    "dona": "дона", "kg": "килограмм", "g": "грамм", "gramm": "грамм",
    "litr": "литр", "l": "литр", "tonna": "тонна", "sentner": "центнер",
    "mg": "миллиграмм",
}


@router.post("/mxik-sync-bulk", status_code=status.HTTP_200_OK)
async def mxik_sync_bulk(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    """
    Kompaniyaning barcha (o'chirilmagan) mahsulotlarini shtrix kodi bo'yicha
    MXIK bilan taqqoslaydi: avval tezkor lokal tovarlar_catalog jadvalidan,
    topilmasa tasnif.soliq.uz ochiq qidiruv API'sidan qidiradi. Topilgan
    mxik_code asosida to'liq ma'lumot (birlik, QQS) bilan boyitishga harakat
    qiladi. mxik_sync_status:
      unknown  — shtrix kodi yo'q, tekshirilmadi
      active   — mxik_code topildi (lokal katalog yoki tasnif qidiruvi orqali)
      disabled — shtrix kod na lokal katalogda, na tasnifda topilmadi
      error    — qidiruv/tasnif so'rovida tarmoq xatoligi yuz berdi
    """
    from datetime import datetime, timezone

    from app.config import settings
    from app.models.mxik import MxikPackage
    from app.models.tovarlar_catalog import TovarlarCatalog
    from app.services.tasnif_service import sync_mxik, search_mxik_by_barcode

    terminal_id = settings.DEFAULT_TERMINAL_ID

    products = db.query(Product).filter(
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,
        Product.barcode.isnot(None),
        Product.barcode != "",
    ).all()

    summary = {"total": len(products), "active": 0, "disabled": 0, "error": 0}
    now = datetime.now(timezone.utc)

    for product in products:
        catalog_entry = db.query(TovarlarCatalog).filter(
            TovarlarCatalog.barcode == product.barcode
        ).first()
        mxik_code = catalog_entry.mxik_code if catalog_entry else None

        if not mxik_code:
            try:
                found = await search_mxik_by_barcode(product.barcode)
            except Exception:
                product.mxik_sync_status = "error"
                product.mxik_synced_at = now
                summary["error"] += 1
                continue
            mxik_code = found.get("mxikCode") if found else None

        if not mxik_code:
            product.mxik_sync_status = "disabled"
            product.mxik_synced_at = now
            summary["disabled"] += 1
            continue

        product.mxik_code = mxik_code
        product.mxik_sync_status = "active"
        summary["active"] += 1

        # Qo'shimcha ma'lumot (birlik, QQS) — muvaffaqiyatsiz bo'lsa ham
        # mxik_code allaqachon yozilgan, shuning uchun status "active" qoladi.
        try:
            ref = await sync_mxik(
                db=db,
                mxik_code=mxik_code,
                terminal_id=terminal_id,
                force_refresh=False,
            )
            unit_candidates = db.query(MxikPackage).filter(
                MxikPackage.mxik_reference_id == ref.id,
                MxikPackage.is_unit_package == 1,
            ).all()

            unit_pkg = None
            if len(unit_candidates) == 1:
                unit_pkg = unit_candidates[0]
            elif unit_candidates:
                # Vazn/hajm bo'yicha bir nechta birlik variant mavjud (gramm,
                # kg, tonna...) — mahsulotning o'z birligiga mos kelganini tanlaymiz.
                wanted = _MXIK_UNIT_NAME_MAP.get((product.unit or "").strip().lower())
                unit_pkg = next(
                    (c for c in unit_candidates if wanted and c.unit_name and wanted in c.unit_name.lower()),
                    unit_candidates[0],
                )

            product.mxik_reference_id = ref.id
            # Frontend "O'lchov kod" maydoni parent_code'dan o'qiydi (GET /mxik/barcode
            # bilan bir xil konventsiya) — package'ning o'z kodi shu yerga yoziladi.
            product.parent_code = unit_pkg.code if unit_pkg else None
            product.package_code = unit_pkg.code if unit_pkg else None
            product.unit_id = unit_pkg.unit_id if unit_pkg else None
            product.vat_rate_type = ref.vat_rate_type
            product.vat_lgota_id = ref.lgota_id
            product.vat_lgota_name = ref.lgota_name
            product.vat_checked_at = now
        except Exception:
            pass

        product.mxik_synced_at = now

    db.commit()
    return summary


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
    ).order_by(Product.plu_code.asc().nulls_last(), Product.id.asc()).all()

    lines = []
    for prod in products:
        # T3.12: kod — tarozi PLU kodi (yo'q bo'lsa eski qoida: SKU raqamlarining oxirgi 5 tasi)
        if prod.plu_code:
            code = str(prod.plu_code)
        else:
            raw_code = prod.sku or str(prod.id)
            code = str(int(''.join(filter(str.isdigit, raw_code))[-5:] or prod.id))

        name = (prod.name or 'NOMSIZ').upper().strip()
        price = int(prod.sale_price or 0)
        
        # 13 field format (Foydalanuvchi talabi):
        # CODE;NAME;;PRICE;0;0;0;CODE;0;0;0;01.01.01;0
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


@router.get("/export/scale")
def export_scale_products(
    branch_id: Optional[int] = Query(None, description="Filial bo'yicha (shu filial omborlarida qoldig'i bor tovarlar)"),
    only_in_stock: bool = Query(False, description="Faqat qoldig'i > 0 bo'lgan tovarlar"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(
        UserRole.admin, UserRole.director, UserRole.manager,
        UserRole.warehouse, UserRole.super_admin
    )),
    ctx: BranchContext = Depends(get_branch_context),
):
    """T3.12: tarozi fayllari (Shtrix-M, TMA, Rongta) uchun kg/g mahsulotlar — sahifalashsiz,
    ixtiyoriy filial kesimida. Filial berilmasa va xodim filialga biriktirilgan bo'lsa, o'z filiali majburlanadi."""
    from sqlalchemy import exists
    from app.models.branch import Branch
    from app.models.warehouse import Warehouse

    scope = None  # None — filial cheklovi yo'q
    if branch_id is not None:
        if not db.query(Branch.id).filter(Branch.id == branch_id,
                                          Branch.company_id == current_user.company_id).first():
            raise HTTPException(status_code=404, detail="Filial topilmadi")
        if ctx.allowed_branch_ids is not None and branch_id not in ctx.allowed_branch_ids:
            raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
        scope = {branch_id}
    elif ctx.scope_ids() is not None:
        scope = set(ctx.scope_ids())

    q = db.query(Product).filter(
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,  # noqa: E712
        Product.status == ProductStatus.active,
        Product.unit.in_(list(SCALE_UNITS)),
    )

    if scope is not None or only_in_stock:
        wh_q = db.query(Warehouse.id).filter(
            Warehouse.company_id == current_user.company_id,
            Warehouse.is_active.isnot(False),
        )
        if scope is not None:
            wh_q = wh_q.filter(Warehouse.branch_id.in_(list(scope)))
        cond = [StockLevel.product_id == Product.id, StockLevel.warehouse_id.in_(wh_q.scalar_subquery())]
        if only_in_stock:
            cond.append(StockLevel.quantity > 0)
        q = q.filter(exists().where(*cond))

    rows = q.order_by(Product.plu_code.asc().nulls_last(), Product.id.asc()).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "plu_code": p.plu_code,
            "barcode": p.barcode,
            "product_code": p.product_code,
            "sale_price": float(p.sale_price or 0),
            "unit": p.unit,
        }
        for p in rows
    ]
