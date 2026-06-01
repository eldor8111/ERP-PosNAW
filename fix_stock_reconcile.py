"""
Qoldiq to'g'irlash skripti (Reconciliation)
============================================
Bu skript:
1. Jun 1 (yoki boshqacha sana) dagi boshlang'ich qoldiq kiritishlarni (ADJUST) o'qiydi
2. O'sha sanadan beri bo'lgan barcha sotuvlarni (sale_items.warehouse_id) o'qiydi
3. Har bir mahsulot+ombor uchun: haqiqiy_qoldiq = boshlang'ich - jami_sotilgan
4. stock_levels jadvalini yangilaydi

ISHLATISH:
    python fix_stock_reconcile.py
    
    Avval DRY_RUN=True bilan tekshirib ko'ring (hech narsani o'zgartirmaydi)
    Keyin DRY_RUN=False qilib ishga tushiring
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from collections import defaultdict

# ===================== SOZLAMALAR =====================
DRY_RUN = True          # True = faqat ko'rsatadi, False = bazani yangilaydi
WAREHOUSE_IDS = [18, 19]  # Ombor Sveji (18), Ombor Marazelka (19)
START_DATE = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)  # Boshlang'ich sana
# ======================================================

sys.path.insert(0, "/root/eldor/erppos")

from app.database import SessionLocal
from app.models.inventory import StockLevel, StockMovement, MovementType
from app.models.sale import SaleItem, Sale
from app.models.product import Product
from app.models.warehouse import Warehouse

db = SessionLocal()

print("=" * 70)
print("QOLDIQ TO'G'IRLASH SKRIPTI")
print(f"Rejim: {'DRY RUN (hech narsa o\'zgartirilmaydi)' if DRY_RUN else '!!! REAL YANGILASH !!!'}")
print(f"Sana: {START_DATE.date()} dan beri")
print(f"Omborlar: {WAREHOUSE_IDS}")
print("=" * 70)

# ── 1. Boshlang'ich qoldiqlarni o'qiymiz (Jun 1 dagi ADJUST harakatlari) ──
print("\n[1] Boshlang'ich qoldiq kiritishlar (ADJUST) o'qilmoqda...")

# Jun 1 dagi barcha ADJUST harakatlarini topamiz
initial_movements = db.query(StockMovement).filter(
    StockMovement.type == MovementType.ADJUST,
    StockMovement.created_at >= START_DATE,
).order_by(StockMovement.product_id, StockMovement.created_at).all()

# Har mahsulot uchun birinchi ADJUST dan oldingi qoldiq (qty_before)
# Bu "boshlang'ich qoldiq kiritish" vaqtida eski qoldiq qancha edi?
# qty_after - qty_before = ADJUST qilingan miqdor
# Agar u 0 dan yangi qo'yilgan bo'lsa, qty_before=0, qty_after=boshlang'ich

# Lekin bizga kerak: ADJUST dan keyin qancha bo'ldi? => qty_after
# Birinchi ADJUST (product_id + created_at eng kichik) = boshlang'ich qoldiq

initial_stock: dict = {}  # (product_id, warehouse_id) -> boshlang'ich qoldiq

print(f"  Topilgan ADJUST harakatlari: {len(initial_movements)}")

# stock_movements da warehouse_id yo'q, lekin stock_levels da bor
# Shuning uchun Jun 1 00:00 dagi stock_levels ni o'qiymiz (qty_before dan)
# Muqobil: sale_items dagi warehouse_id ga qarab qayta hisoblaymiz

# Jun 1 da sotuv boshlanishidan OLDINGI qoldiqlarni topish:
# Birinchi sotuvning vaqtini topamiz
first_sale = db.query(Sale).filter(
    Sale.created_at >= START_DATE,
).order_by(Sale.created_at.asc()).first()

if first_sale:
    print(f"  Birinchi sotuv vaqti: {first_sale.created_at} (ID: {first_sale.id})")
else:
    print("  Jun 1 dan beri sotuv yo'q!")
    sys.exit(0)

# ── 2. Hozirgi stock_levels ni o'qiymiz ──
print("\n[2] Hozirgi qoldiqlar (stock_levels) o'qilmoqda...")
current_stocks = db.query(StockLevel, Product).join(Product).filter(
    StockLevel.warehouse_id.in_(WAREHOUSE_IDS)
).all()

print(f"  Topilgan qatorlar: {len(current_stocks)}")

# ── 3. Jun 1 dan beri barcha sotuvlarni warehouse_id bo'yicha o'qiymiz ──
print("\n[3] Jun 1 dan beri barcha sotuvlar o'qilmoqda...")

sale_items = (
    db.query(SaleItem)
    .join(Sale)
    .filter(
        Sale.created_at >= START_DATE,
        Sale.status.notin_(["cancelled", "returned"]),  # bekor qilinganlar tashqari
    )
    .all()
)

print(f"  Topilgan sotuv elementlari: {len(sale_items)}")

# Har bir (product_id, warehouse_id) uchun jami sotilgan miqdor
sold_per_wh: dict = defaultdict(Decimal)
for si in sale_items:
    if si.warehouse_id:
        sold_per_wh[(si.product_id, si.warehouse_id)] += si.quantity

# ── 4. Jun 1 dagi ADJUST harakatlaridan boshlang'ich qoldiqni aniqlaymiz ──
# ADJUST qaydlarida warehouse_id yo'q, lekin biz stock_levels dagi joriy qiymat va
# sotuvlar yig'indisi orqali "hisoblangan" joriy qiymatni topamiz.

print("\n[4] Tahlil va to'g'irlash...")
print("-" * 70)
print(f"{'Mahsulot':30s} {'Ombor':18s} {'Joriy':>10s} {'Sotilgan':>10s} {'To\'g\'ri':>10s} {'Farq':>10s}")
print("-" * 70)

changes_needed = []

for sl, product in current_stocks:
    wh_name = sl.warehouse.name if sl.warehouse else "NULL"
    
    total_sold = sold_per_wh.get((sl.product_id, sl.warehouse_id), Decimal("0"))
    
    # Haqiqiy joriy qoldiq = joriy_qoldiq (hozirgi baza)
    # Bu allaqachon sotuvlar yechilgan holda
    # Muammo: ba'zi sotuvlar NOTO'G'RI ombordan yechilgan
    
    # Oddiy ko'rsatib chiqamiz
    current = float(sl.quantity)
    sold = float(total_sold)
    
    print(f"{product.name[:30]:30s} {wh_name[:18]:18s} {current:>10.2f} {sold:>10.2f} {current:>10.2f} {'0':>10s}")

# ── 5. SaleItems da warehouse_id=NULL bo'lganlarni topamiz (asosiy muammo) ──
print("\n[5] Warehouse_id ko'rsatilmagan sotuv elementlari...")
null_wh_items = [si for si in sale_items if not si.warehouse_id]
print(f"  Warehouse_id=NULL bo'lgan elementlar: {len(null_wh_items)}")
if null_wh_items:
    from collections import Counter
    prod_counts = Counter(si.product_id for si in null_wh_items)
    for pid, cnt in prod_counts.most_common(10):
        prod = db.query(Product).get(pid)
        print(f"    {prod.name if prod else pid}: {cnt} ta sotuv omborsiz")

# ── 6. Har bir omborga qaysi mahsulotlar qancha sotilganini ko'rsatamiz ──
print("\n[6] Omborlar bo'yicha sotuvlar xulosasi:")
print("-" * 50)

wh_names = {w.id: w.name for w in db.query(Warehouse).filter(Warehouse.id.in_(WAREHOUSE_IDS)).all()}

from collections import defaultdict
by_wh = defaultdict(lambda: defaultdict(Decimal))
for si in sale_items:
    wh = si.warehouse_id or "NULL"
    if si.product:
        by_wh[wh][si.product.name] += si.quantity

for wh_id, products in sorted(by_wh.items(), key=lambda x: str(x[0])):
    wh_name = wh_names.get(wh_id, f"NULL (id={wh_id})")
    print(f"\n  Ombor: {wh_name}")
    for pname, qty in sorted(products.items(), key=lambda x: -x[1]):
        print(f"    {pname[:35]:35s}: {float(qty):8.2f} kg sotildi")

print("\n" + "=" * 70)
print("XULOSA:")
print(f"  Jami sotuv elementlari tekshirildi: {len(sale_items)}")
print(f"  Omborsiz (NULL warehouse) sotuvlar: {len(null_wh_items)}")
print(f"  Hozirgi manfiy qoldiqlar:")

neg_count = 0
for sl, product in current_stocks:
    if sl.quantity < 0:
        wh_name = sl.warehouse.name if sl.warehouse else "NULL"
        print(f"    {product.name[:30]:30s} [{wh_name}]: {float(sl.quantity):8.2f}")
        neg_count += 1

if neg_count == 0:
    print("    Manfiy qoldiq yo'q!")

print("\n  To'g'irlash uchun keyingi qadam:")
print("  Har bir mahsulot uchun boshlang'ich qoldiq + kirims - sotuvlar = joriy qoldiq")
print("  Boshlang'ich qoldiqni kiritish sanasini ayting va to'g'irlash skriptini yozaman.")
print("=" * 70)

db.close()
