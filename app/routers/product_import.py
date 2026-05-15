"""
Mahsulotlarni Excel/JSON dan ommaviy yuklash endpointi.
bulk_import_products products.py dan ajratilgan.
"""
import random
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database import get_db
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.user import User, UserRole

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
}

STATUS_MAP = {
    "faol": "active",    "active": "active",
    "nofaol": "inactive","inactive": "inactive",
    "arxiv": "archived", "archived": "archived",
}
@router.get("/fix-db")
def fix_database_constraints(db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        # Drop old constraints if they exist
        db.execute(text("DROP INDEX IF EXISTS uq_products_barcode_active;"))
        db.execute(text("DROP INDEX IF EXISTS uq_products_sku_active;"))
        
        # Look for duplicates inside the same company before creating the index
        dups = db.execute(text('''
            SELECT company_id, barcode, COUNT(*) 
            FROM products 
            WHERE is_deleted = false AND barcode IS NOT NULL AND barcode != ''
            GROUP BY company_id, barcode 
            HAVING COUNT(*) > 1
        ''')).fetchall()
        
        if dups:
            # We must fix duplicates first! Keep the first one, delete others
            for dup in dups:
                cid, bcode, _ = dup
                products_to_fix = db.execute(text('''
                    SELECT id FROM products 
                    WHERE company_id = :cid AND barcode = :bcode AND is_deleted = false
                    ORDER BY id ASC
                '''), {"cid": cid, "bcode": bcode}).fetchall()
                
                # Keep first, soft delete the rest
                if len(products_to_fix) > 1:
                    ids_to_delete = [p[0] for p in products_to_fix[1:]]
                    db.execute(text("UPDATE products SET is_deleted = true, barcode = barcode || '-dup-' || id WHERE id = ANY(:ids)"), {"ids": ids_to_delete})
        
        db.commit()
        
        # Now create new constraints
        db.execute(text("CREATE UNIQUE INDEX uq_products_barcode_active ON products (company_id, barcode) WHERE is_deleted = false;"))
        db.execute(text("CREATE UNIQUE INDEX uq_products_sku_active ON products (company_id, sku) WHERE is_deleted = false;"))
        db.commit()
        
        return {"status": "success", "message": "Bazadagi muammo to'liq hal qilindi! Endi bemalol mahsulot qo'shishingiz mumkin."}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}

@router.post("/bulk-check")
def bulk_check_products(
    rows: List[dict],
    search_by_sku: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    all_products = db.query(Product.name, Product.barcode, Product.sku).filter(
        Product.is_deleted == False,
        Product.company_id == current_user.company_id,
    ).all()
    
    name_set = {p.name for p in all_products if p.name}
    barcode_set = {p.barcode for p in all_products if p.barcode}
    sku_set = {p.sku for p in all_products if p.sku}
    
    found_count = 0
    new_count = 0
    
    for row in rows:
        name = str(row.get("Nomi") or "").strip()
        barcode = str(row.get("Barkod") or "").strip()
        sku_val = str(row.get("SKU") or "").strip() or None
        if sku_val and sku_val.lstrip("0") == "":
            sku_val = None
            
        if not name and not barcode:
            continue
            
        exists = False
        if name and name in name_set:
            exists = True
        elif barcode and barcode in barcode_set:
            exists = True
        elif search_by_sku and sku_val and sku_val in sku_set:
            exists = True
            
        if exists:
            found_count += 1
        else:
            new_count += 1
            
    return {"found_count": found_count, "new_count": new_count}

@router.post("/bulk-import")
def bulk_import_products(
    rows: List[dict],
    allow_update: bool = Query(False),
    search_by_sku: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    """Excel fayldan ko'plab mahsulotlarni yuklash yoki yangilash.

    Har bir satr alohida savepoint bilan saqlanadi — bitta xato
    butun importni to'xtatmaydi.
    """
    created = 0
    updated = 0
    errors: list = []

    # ── Bazadagi BARCHA (o'chirilmagan) mahsulotlarni yuklash ──────────
    all_products = db.query(Product).filter(
        Product.is_deleted == False,
        Product.company_id == current_user.company_id,
    ).all()

    name_map    = {p.name:    p for p in all_products if p.name}
    barcode_map = {p.barcode: p for p in all_products if p.barcode}
    sku_map     = {p.sku:     p for p in all_products if p.sku}

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

            # Har bir update ni alohida savepoint bilan saqlash
            sp = db.begin_nested()
            try:
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
        except Exception:
            errors.append({"row": row_num, "name": name, "error": "Narx/qoldiq qiymatlari noto'g'ri"})
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
            )
            product.stock_level = StockLevel(quantity=initial_stock)
            db.add(product)
            db.flush()
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
        "created":      created,
        "updated":      updated,
        "skipped":      skipped,
        "errors":       errors[:200],
        "total_errors": total_errors,
    }
