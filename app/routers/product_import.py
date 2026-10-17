"""
Mahsulotlarni Excel/JSON dan ommaviy yuklash endpointi.
bulk_import_products products.py dan ajratilgan.
"""
import random
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User, UserRole
from app.routers.products import _assign_plu
from app.services.inventory_service import get_or_create_stock, receive_stock

router = APIRouter(prefix="/products", tags=["Products"])

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)

FIELD_MAP = {
    "Nomi":          ("name",             str),
    "Barkod":        ("barcode",          str),
    "SKU":           ("sku",              str),
    "Kod":           ("product_code",     str),
    "O'lchov":       ("unit",             str),
    "Tan narxi":     ("cost_price",       Decimal),
    "Chakana narxi": ("sale_price",       Decimal),
    "Ulgurji narxi": ("wholesale_price",  Decimal),
    "Min. qoldiq":   ("min_stock",        Decimal),
    "Qoldiq":        ("_stock",           Decimal),
    "Holat":         ("status",           str),
    "Brand":         ("brand",            str),
    "Kategoriya":    ("category_id",      int),
    # T4.5: qator bo'yicha ombor (nom) - so'rov parametridagi omborga nisbatan ustun
    "Ombor":         ("_warehouse",       str),
    # Valyuta maydonlari — frontend __cur_ prefiksi bilan yuboradi
    "__cur_Tan narxi":     ("cost_currency",      str),
    "__cur_Chakana narxi": ("sale_currency",      str),
    "__cur_Ulgurji narxi": ("wholesale_currency", str),
}

STATUS_MAP = {
    "faol": "active",    "active": "active",
    "nofaol": "inactive","inactive": "inactive",
    "arxiv": "archived", "archived": "archived",
}


def _resolve_target_warehouse(db: Session, current_user: User, warehouse_id: Optional[int]):
    """So'rov parametridagi (yoki joriy filialning default) omborni aniqlaydi (T1.5).

    `warehouse_id` berilgan, lekin korxonada topilmasa - 400 (hech qachon jimgina boshqa omborga
    yozilmaydi), filial ruxsati yo'q bo'lsa - 403. Berilmagan va aniqlanmasa - `None`."""
    from app.models.warehouse import Warehouse
    from app.services.warehouse_resolver import resolve_warehouse
    try:
        _wid = resolve_warehouse(
            db, current_user.company_id, requested_id=warehouse_id, purpose="receive", user=current_user,
        )
        return db.query(Warehouse).filter(Warehouse.id == _wid).first()
    except HTTPException as e:
        if warehouse_id:
            # Tanlangan ombor topilmasa 400 (MODEL-24), filial ruxsati yo'q bo'lsa 403
            if e.status_code == 404:
                raise HTTPException(status_code=400, detail="Tanlangan ombor topilmadi")
            raise
        # Ombor aniqlanmadi - faqat qoldiqli satrlar xato bo'ladi (har satr uchun)
        return None


class _RowWarehouseResolver:
    """"Ombor" ustuni (nom) -> ombor id. Faqat korxonaning faol omborlari; filialli (non-admin) xodim
    uchun faqat o'z filiallari omborlari. Natija keshlanadi: (ombor_id, xato_matni)."""

    def __init__(self, db: Session, current_user: User, default_wh=None):
        from app.core.branch_context import effective_branch_ids
        from app.models.warehouse import Warehouse
        from app.services.tenant_guards import BRANCH_FREE_ROLES
        self.default_wh = default_wh
        self.by_name: dict = {}
        for w in db.query(Warehouse).filter(
            Warehouse.company_id == current_user.company_id, Warehouse.is_active.isnot(False),
        ).order_by(Warehouse.id).all():
            self.by_name.setdefault((w.name or "").strip().casefold(), []).append(w)
        self.allowed = frozenset() if current_user.role in BRANCH_FREE_ROLES \
            else effective_branch_ids(db, current_user)
        self.cache: dict = {}

    def resolve(self, raw):
        name = str(raw or "").replace("\xa0", " ").strip()
        key = name.casefold()
        if key in self.cache:
            return self.cache[key]
        cands = self.by_name.get(key, [])
        if not cands:
            res = (None, f"Ombor topilmadi: {name}")
        else:
            if self.allowed:
                cands = [w for w in cands if w.branch_id in self.allowed]
            if not cands:
                res = (None, f"Bu omborga import qilish uchun ruxsat yo'q: {name}")
            elif len(cands) > 1:
                dw = self.default_wh
                pick = next((w for w in cands if dw is not None and w.id == dw.id), None)
                res = (pick.id, None) if pick else (None, f"Ombor nomi bir nechta: {name} - omborni aniqlashtiring")
            else:
                res = (cands[0].id, None)
        self.cache[key] = res
        return res


@router.post("/bulk-check")
def bulk_check_products(
    rows: List[dict],
    search_by_sku: bool = Query(False),
    warehouse_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    """Import oldidan tekshiruv: `{found_count, new_count, stock_will_change}`.

    `stock_will_change` - mavjud mahsulotlardan nechtasining tanlangan (yoki qatordagi "Ombor") ombor
    qoldig'i Excel'dagi "Qoldiq" ga o'zgarishi."""
    target_wh = _resolve_target_warehouse(db, current_user, warehouse_id)   # 400/403 noto'g'ri ombor
    all_products = db.query(
        Product.id, Product.name, Product.barcode, Product.sku, Product.product_type,
    ).filter(
        Product.is_deleted == False,
        Product.company_id == current_user.company_id,
    ).all()

    name_map = {p.name: p for p in all_products if p.name}
    barcode_map = {p.barcode: p for p in all_products if p.barcode}
    sku_map = {p.sku: p for p in all_products if p.sku}

    found_count = 0
    new_count = 0
    found_rows: list = []   # (product, ombor_id, yangi_qoldiq)
    wh_resolver = None

    for row in rows:
        name = str(row.get("Nomi") or "").strip()
        barcode = str(row.get("Barkod") or "").strip()
        sku_val = str(row.get("SKU") or "").strip() or None
        if sku_val and sku_val.lstrip("0") == "":
            sku_val = None

        if not name and not barcode:
            continue

        product = None
        if name and name in name_map:
            product = name_map[name]
        elif barcode and barcode in barcode_map:
            product = barcode_map[barcode]
        elif search_by_sku and sku_val and sku_val in sku_map:
            product = sku_map[sku_val]

        if product is not None:
            found_count += 1
            raw_stock = row.get("Qoldiq")
            if raw_stock is None or str(raw_stock).strip() == "":
                continue
            try:
                new_qty = Decimal(str(raw_stock).replace(" ", "").replace("\xa0", "").replace(",", ".").strip())
            except Exception:
                continue
            row_wh_id = target_wh.id if target_wh else None
            wh_raw = str(row.get("Ombor") or "").strip()
            if wh_raw:
                if wh_resolver is None:
                    wh_resolver = _RowWarehouseResolver(db, current_user, target_wh)
                row_wh_id = wh_resolver.resolve(wh_raw)[0]
            if row_wh_id is not None and product.product_type not in ("sell", "service"):
                found_rows.append((product, row_wh_id, new_qty))
        else:
            new_count += 1

    stock_will_change = 0
    if found_rows:
        pids = list({p.id for p, _, _ in found_rows})
        has_variants = {r[0] for r in db.query(ProductVariant.product_id).filter(
            ProductVariant.product_id.in_(pids)).all()}
        cur = {(r.product_id, r.warehouse_id): r.quantity for r in db.query(StockLevel).filter(
            StockLevel.product_id.in_(pids), StockLevel.variant_id.is_(None)).all()}
        for p, wh_id, new_qty in found_rows:
            if p.id in has_variants:
                continue
            if Decimal(str(cur.get((p.id, wh_id)) or 0)) != new_qty:
                stock_will_change += 1

    return {"found_count": found_count, "new_count": new_count, "stock_will_change": stock_will_change}

@router.post("/bulk-import")
def bulk_import_products(
    rows: List[dict],
    allow_update: bool = Query(False),
    search_by_sku: bool = Query(False),
    warehouse_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    """Excel fayldan ko'plab mahsulotlarni yuklash yoki yangilash.

    Har bir satr alohida savepoint bilan saqlanadi — bitta xato
    butun importni to'xtatmaydi.
    """
    from app.services.tariff_guard import check_product_limit
    check_product_limit(db, current_user.company_id, count_to_add=len(rows))

    created = 0
    updated = 0
    errors: list = []
    
    # ── Omborni aniqlash (T1.5): tanlangan ombor (korxona/faollik/filial bo'yicha), aks holda
    # joriy filialning default ombori - korxonaning eng kichik id li ombori emas.
    # T4.5: qatordagi "Ombor" ustuni (nom) shu omborga nisbatan ustun ──
    warnings: list = []
    chosen_wh = _resolve_target_warehouse(db, current_user, warehouse_id)
    first_wh_id = chosen_wh.id if chosen_wh else None
    first_wh_name = chosen_wh.name if chosen_wh else None
    wh_resolver = _RowWarehouseResolver(db, current_user, chosen_wh)

    # ── Bazadagi BARCHA (o'chirilmagan) mahsulotlarni yuklash ──────────
    all_products = db.query(Product).filter(
        Product.is_deleted == False,
        Product.company_id == current_user.company_id,
    ).all()

    # Kategoriyalarni nomi bo'yicha map qilish
    from app.models.category import Category
    all_cats = db.query(Category).filter(
        Category.company_id == current_user.company_id,
        Category.is_deleted == False
    ).all()
    cat_name_map = {c.name.strip().lower(): c.id for c in all_cats}

    # Identifikatsiya xaritalarini yaratish (nomlardagi probellarni tozalab olamiz)
    name_map    = {p.name.strip():    p for p in all_products if p.name}
    barcode_map = {p.barcode.strip(): p for p in all_products if p.barcode}
    sku_map     = {p.sku.strip():     p for p in all_products if p.sku}

    # Barcode uchun to'liq set (is_deleted=True bo'lganlar ham partial index ta'sir qilmaydi,
    # lekin xavfsizlik uchun faqat aktiv barcodes yetarli — partial index shunga qaratilgan)
    db_skus     = set(sku_map.keys())
    db_barcodes = set(barcode_map.keys())
    # Xuddi shu sessiyada qo'shilgan yangilar uchun to'plamlar
    session_skus:     set = set()
    session_barcodes: set = set()

    for idx, row in enumerate(rows):
        row_num = row.get("__row_index", idx + 2)
        name             = str(row.get("Nomi") or "").strip()
        barcode          = str(row.get("Barkod") or "").strip()
        product_code_val = str(row.get("Kod") or "").strip() or None
        sku_val          = str(row.get("SKU") or "").strip() or None
        if sku_val and sku_val.lstrip("0") == "":
            sku_val = None

        if not name and not barcode:
            errors.append({"row": row_num, "error": "Mahsulot nomi yoki barkod majburiy"})
            continue

        # T4.5: qator bo'yicha ombor ("Ombor" ustuni) - topilmasa faqat shu qator xato
        row_wh_id = first_wh_id
        wh_raw = str(row.get("Ombor") or "").replace("\xa0", " ").strip()
        if wh_raw:
            row_wh_id, wh_err = wh_resolver.resolve(wh_raw)
            if wh_err:
                errors.append({"row": row_num, "name": name or barcode, "error": wh_err})
                continue

        # ── Mavjud mahsulotni topish ───────────────────────────────────
        existing = None
        if name and name in name_map:
            existing = name_map[name]
        if not existing and barcode and barcode in barcode_map:
            existing = barcode_map[barcode]
        if not existing and search_by_sku and sku_val and sku_val in sku_map:
            existing = sku_map[sku_val]

        # ── UPDATE ─────────────────────────────────────────────────────
        if existing:
            if not allow_update:
                errors.append({
                    "row": row_num, "name": name or barcode,
                    "error": f"'{name or barcode}' allaqachon mavjud — o'tkazib yuborildi",
                    "skipped": True,   # frontend uchun flag
                })
                continue

            stock_val = None
            for row_key, (field, cast) in FIELD_MAP.items():
                if field == "_warehouse":
                    continue   # yuqorida aniqlangan (row_wh_id)
                raw = row.get(row_key)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    # Qiymatni tozalash
                    if cast == Decimal:
                        # Narxlar/sonlar uchun probellarni olib tashlaymiz
                        clean_raw = str(raw).replace(" ", "").replace("\xa0", "").replace(",", ".").strip()
                        
                        if field == "_stock":
                            stock_val = Decimal(clean_raw)
                        else:
                            setattr(existing, field, Decimal(clean_raw))
                    elif field == "category_id":
                        # Kategoriya nomi bo'yicha ID ni topish yoki yangi ochish
                        clean_raw = str(raw).replace("\xa0", " ").strip()
                        if clean_raw:
                            cat_id = cat_name_map.get(clean_raw.lower())
                            if not cat_id:
                                # Mavjud bo'lmasa — yangi kategoriya ochamiz
                                new_cat = Category(name=clean_raw, company_id=current_user.company_id)
                                db.add(new_cat)
                                db.flush()
                                cat_id = new_cat.id
                                cat_name_map[clean_raw.lower()] = cat_id
                            
                            setattr(existing, field, cat_id)
                    elif field == "status":
                        clean_raw = str(raw).replace("\xa0", " ").strip()
                        mapped = STATUS_MAP.get(clean_raw.lower())
                        if mapped:
                            setattr(existing, field, mapped)
                    else:
                        clean_raw = str(raw).replace("\xa0", " ").strip()
                        if clean_raw:
                            setattr(existing, field, clean_raw)
                except Exception:
                    errors.append({"row": row_num, "name": name, "error": f"'{row_key}' qiymati noto'g'ri: {raw}"})
                    continue

            # Ob'ektni sessiyada ochiqchasiga belgilash va o'zgarishlarni qo'llash
            db.add(existing)
            sp = db.begin_nested()
            try:
                if stock_val is not None:
                    # Qoldiq faqat tanlangan ombor qatoriga (product, variant=NULL, warehouse)
                    # ADJUST harakati bilan yoziladi; variantli / sell / service — o'zgarmaydi
                    has_variants = db.query(ProductVariant.id).filter(
                        ProductVariant.product_id == existing.id
                    ).first() is not None
                    if existing.product_type in ("sell", "service") or has_variants:
                        warnings.append({
                            "row": row_num, "name": name or barcode,
                            "warning": "Qoldiq o'zgartirilmadi: variantli yoki tarkibiy/xizmat mahsulot — "
                                       "qoldiqni Inventarizatsiya orqali tuzating",
                        })
                    elif row_wh_id is None:
                        warnings.append({
                            "row": row_num, "name": name or barcode,
                            "warning": "Qoldiq o'zgartirilmadi: korxonada ombor topilmadi",
                        })
                    else:
                        stock = get_or_create_stock(db, existing.id, row_wh_id, None)
                        qty_before = stock.quantity if stock.quantity is not None else Decimal("0")
                        delta = stock_val - qty_before
                        if delta != 0:
                            stock.quantity = stock_val
                            db.add(StockMovement(
                                product_id=existing.id,
                                variant_id=None,
                                warehouse_id=row_wh_id,
                                type=MovementType.ADJUST,
                                qty_before=qty_before,
                                qty_after=stock_val,
                                quantity=abs(delta),
                                reference_type="product_import",
                                reference_id=None,
                                user_id=current_user.id,
                                reason="Excel import",
                            ))
                db.flush()
                sp.commit()
                updated += 1
            except Exception as exc:
                sp.rollback()
                # Session ni tozalash
                db.expire(existing)
                errors.append({
                    "row": row_num, "name": name or barcode,
                    "error": f"Yangilashda xato: {str(exc)[:200]}",
                })
            continue

        # ── CREATE ─────────────────────────────────────────────────────
        if not name:
            errors.append({"row": row_num, "error": "Yangi mahsulot uchun Nomi majburiy"})
            continue

        try:
            cost_price      = Decimal(str(row.get("Tan narxi") or 0))
            sale_price      = Decimal(str(row.get("Chakana narxi") or 0))
            wp_raw          = row.get("Ulgurji narxi")
            wholesale_price = Decimal(str(wp_raw)) if wp_raw else None
            initial_stock   = Decimal(str(row.get("Qoldiq") or 0))
            min_stock_val   = Decimal(str(row.get("Min. qoldiq") or 0))
            
            # Kategoriya tanitish
            cat_import_raw = str(row.get("Kategoriya") or "").strip()
            row_category_id = None
            if cat_import_raw:
                row_category_id = cat_name_map.get(cat_import_raw.lower())
                if not row_category_id:
                    # Mavjud bo'lmasa — yangi kategoriya ochamiz
                    new_cat = Category(name=cat_import_raw, company_id=current_user.company_id)
                    db.add(new_cat)
                    db.flush()
                    row_category_id = new_cat.id
                    cat_name_map[cat_import_raw.lower()] = row_category_id
            
            # Valyuta kodlari (narxlar convert qilinmasligi kerak)
            cost_cur        = str(row.get("__cur_Tan narxi") or "UZS").strip().upper() or "UZS"
            sale_cur        = str(row.get("__cur_Chakana narxi") or "UZS").strip().upper() or "UZS"
            wholesale_cur   = str(row.get("__cur_Ulgurji narxi") or "UZS").strip().upper() or "UZS"
        except Exception:
            errors.append({"row": row_num, "name": name, "error": "Narx/qoldiq qiymatlari noto'g'ri"})
            continue

        if initial_stock < 0:
            errors.append({"row": row_num, "name": name, "error": "Qoldiq manfiy bo'lishi mumkin emas"})
            continue
        if initial_stock > 0 and row_wh_id is None:
            errors.append({"row": row_num, "name": name, "error": "Ombor aniqlanmadi — omborni tanlang, qoldiqli mahsulotni yuklab bo'lmaydi"})
            continue

        # ── Barkod tekshiruvi (DB + joriy sessiya) ─────────────────────
        if barcode and (barcode in db_barcodes or barcode in session_barcodes):
            errors.append({
                "row": row_num, "name": name,
                "error": f"Barkod '{barcode}' allaqachon mavjud — o'tkazib yuborildi",
                "skipped": True,
            })
            continue

        unit       = str(row.get("O'lchov") or "dona").strip()
        brand      = str(row.get("Brand") or "").strip() or None
        status_val = STATUS_MAP.get(str(row.get("Holat") or "active").strip().lower(), "active")

        # ── SKU generatsiya ────────────────────────────────────────────
        sku_final = sku_val
        if not sku_final or sku_final in db_skus or sku_final in session_skus:
            while True:
                s = str(random.randint(10000, 99999))
                if s not in db_skus and s not in session_skus:
                    sku_final = s
                    break

        # ── Barkod generatsiya (bo'sh bo'lsa) ─────────────────────────
        if not barcode:
            while True:
                b = str(random.randint(10000000, 99999999))
                if b not in db_barcodes and b not in session_barcodes:
                    barcode = b
                    break

        barcode   = barcode[:50]
        sku_final = sku_final[:50]

        # ── Savepoint AVVAL, keyin db.add — to'g'ri tartib ────────────
        sp = db.begin_nested()
        try:
            product = Product(
                name=name[:255], barcode=barcode, sku=sku_final,
                product_code=product_code_val, unit=unit[:20] if unit else "dona",
                cost_price=cost_price, sale_price=sale_price,
                wholesale_price=wholesale_price, min_stock=min_stock_val,
                status=status_val, brand=brand[:100] if brand else None,
                company_id=current_user.company_id, images="[]",
                category_id=row_category_id,
                cost_currency=cost_cur,
                sale_currency=sale_cur,
                wholesale_currency=wholesale_cur,
            )
            # T3.12: kg/g mahsulotga tarozi PLU kodi avtomatik beriladi
            _assign_plu(db, current_user.company_id, product)
            db.add(product)
            db.flush()
            if initial_stock > 0:
                # Qoldiq tanlangan omborga kirim (IN) harakati + Batch bilan tushadi
                receive_stock(
                    db, product.id, initial_stock, current_user.id,
                    reason="Excel import", reference_type="product_import", reference_id=None,
                    warehouse_id=row_wh_id, purchase_price=cost_price,
                    company_id=current_user.company_id,
                )
            sp.commit()

            # Muvaffaqiyatli qo'shildi — in-memory map larni yangilash
            session_barcodes.add(barcode)
            session_skus.add(sku_final)
            name_map[name]       = product
            barcode_map[barcode] = product
            sku_map[sku_final]   = product
            created += 1

        except Exception as exc:
            sp.rollback()  # Product va StockLevel avtomatik session dan o'chiriladi
            err_msg = str(exc)
            if "uq_products_barcode" in err_msg or "duplicate key" in err_msg.lower():
                user_msg = f"Barkod '{barcode}' allaqachon bazada mavjud — o'tkazib yuborildi"
            elif "uq_products_sku" in err_msg:
                user_msg = f"SKU '{sku_final}' allaqachon mavjud — o'tkazib yuborildi"
            else:
                user_msg = f"Saqlashda xato: {err_msg[:200]}"
            errors.append({
                "row": row_num, "name": name,
                "error": user_msg,
                "skipped": True,
            })

    # ── Oxirgi commit (barcha muvaffaqiyatli savepoint lar uchun) ──────
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        errors.append({"row": 0, "error": f"Yakuniy saqlashda xato: {str(exc)[:300]}"})
        created = updated = 0

    total_errors = len(errors)
    skipped = sum(1 for e in errors if e.get("skipped"))
    return {
        "created":        created,
        "updated":        updated,
        "skipped":        skipped,
        "errors":         errors[:200],
        "total_errors":   total_errors,
        "warehouse_id":   first_wh_id,
        "warehouse_name": first_wh_name,
        "warnings":       warnings[:200],
    }
