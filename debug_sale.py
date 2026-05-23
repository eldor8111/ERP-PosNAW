"""
Virtual mahsulot (Dumba) sotilganda Butun qo'y qoldig'i yechilmasligini diagnostika qilish.
Server da ishlatish: venv/bin/python debug_sale.py
"""
from decimal import Decimal
from collections import defaultdict
from app.database import SessionLocal
from app.models.product import Product, ProductConversion
from app.models.inventory import StockLevel, StockMovement

db = SessionLocal()

print("=" * 60)
print("1. DUMBA MAHSULOTI HOLATI")
print("=" * 60)
dumba = db.query(Product).filter(Product.name.ilike('%dumba%'), Product.is_deleted == False).first()
if not dumba:
    print("❌ DUMBA topilmadi!")
    db.close()
    exit()
print(f"   ID: {dumba.id}")
print(f"   Nomi: {dumba.name}")
print(f"   product_type: {dumba.product_type}  <-- 'sell' bo'lishi kerak")

print()
print("=" * 60)
print("2. DUMBA KONVERSIYA YOZUVI")
print("=" * 60)
conv = db.query(ProductConversion).filter(ProductConversion.sell_product_id == dumba.id).first()
if not conv:
    print("❌ KONVERSIYA TOPILMADI! Bu asosiy muammo.")
    print("   force_update.py skriptini qayta ishga tushiring!")
else:
    print(f"   ✅ Konversiya mavjud:")
    print(f"   sell_product_id  = {conv.sell_product_id}")
    print(f"   source_product_id= {conv.source_product_id}")
    print(f"   ratio            = {conv.ratio}")

print()
print("=" * 60)
print("3. BUTUN QO'Y MAHSULOTI")
print("=" * 60)
if conv:
    butun = db.query(Product).filter(Product.id == conv.source_product_id, Product.is_deleted == False).first()
    if not butun:
        print(f"❌ source_product_id={conv.source_product_id} bo'yicha mahsulot topilmadi yoki o'chirilgan!")
    else:
        print(f"   ✅ Butun qo'y topildi:")
        print(f"   ID: {butun.id}, Nomi: {butun.name}, Turi: {butun.product_type}")

print()
print("=" * 60)
print("4. BUTUN QO'Y STOCK LEVELLARI")
print("=" * 60)
if conv and butun:
    stocks = db.query(StockLevel).filter(StockLevel.product_id == butun.id).all()
    print(f"   Jami {len(stocks)} ta StockLevel yozuvi:")
    for s in stocks:
        print(f"   warehouse_id={s.warehouse_id}, quantity={s.quantity}")
    
    active_stocks = [s for s in stocks if s.quantity > 0]
    print(f"   Aktiv ({len(active_stocks)} ta, miqdori > 0):")
    for s in active_stocks:
        print(f"   ✅ warehouse_id={s.warehouse_id}, quantity={s.quantity}")
    if not active_stocks:
        print("   ❌ Miqdori > 0 bo'lgan StockLevel yo'q!")

print()
print("=" * 60)
print("5. DUMBA STOCK LEVELLARI (bo'sh bo'lishi kerak)")
print("=" * 60)
dumba_stocks = db.query(StockLevel).filter(StockLevel.product_id == dumba.id).all()
if dumba_stocks:
    print(f"   ⚠️  Dumba uchun {len(dumba_stocks)} ta StockLevel topildi (kerak emas):")
    for s in dumba_stocks:
        print(f"   warehouse_id={s.warehouse_id}, quantity={s.quantity}")
else:
    print("   ✅ Dumba uchun StockLevel yo'q (to'g'ri)")

print()
print("=" * 60)
print("6. SO'NGGI 3 TA SOTUV HARAKATLARI")
print("=" * 60)
movements = db.query(StockMovement).filter(
    StockMovement.product_id.in_([dumba.id, conv.source_product_id if conv else 0])
).order_by(StockMovement.id.desc()).limit(6).all()
for m in movements:
    prod_name = "Dumba" if m.product_id == dumba.id else "Butun qo'y"
    print(f"   [{prod_name}] {m.type.value} qty={m.quantity} ref={m.reference_type}#{m.reference_id} reason={m.reason}")

print()
print("=" * 60)
print("7. SALE_SERVICE.PY VERSIYASI TEKSHIRUVI")
print("=" * 60)
try:
    import inspect
    from app.services.sale_service import create_sale
    src = inspect.getsource(create_sale)
    if 'virtual_source_ids' in src:
        print("   ✅ YANGI KOD mavjud (virtual_source_ids topildi)")
    else:
        print("   ❌ ESKI KOD ishlamoqda! git pull + pm2 restart qiling")
    
    if 'use_all_warehouses' in src:
        print("   ✅ YANGI KOD mavjud (use_all_warehouses topildi)")
    else:
        print("   ❌ ESKI KOD! Yangi kodni yuklab oling")
except Exception as e:
    print(f"   ⚠️  Tekshirishda xatolik: {e}")

print()
print("=" * 60)
print("8. XULOSA VA TAVSIYA")
print("=" * 60)
if not conv:
    print("❌ MUAMMO: Konversiya yo'q. force_update.py ni ishga tushiring")
elif not active_stocks:
    print("❌ MUAMMO: Butun qo'y ning StockLevel qoldig'i yo'q yoki 0")
else:
    print("✅ DB holati to'g'ri. Agar sotuv ishlamasa:")
    print("   1. git pull origin main")
    print("   2. pm2 restart erppos-backend")
    print("   3. pm2 logs erppos-backend --lines 50 (xatoni tekshiring)")

db.close()
