"""
Faqat MANFIY qoldiqlarni to'g'irlash (xavfsiz versiya)
=======================================================
MANTIQ:
  - Boshlang'ich qoldiq = 0 bo'lgan va hozir MANFIY bo'lgan mahsulotlarni 0 ga qaytaradi
  - Ijobiy qoldiqlarni (xarid bilan kelganlarni) TEGINMAYDI
  - "Butun quy" Ombor Marazelka: 0 ga qaytaradi (boshlang'ich 0 edi, noto'g'ri yechilgan)
  - "Butun quy" Ombor Sveji: TEGINMAYDI (hozirgi 637 to'g'ri)

DRY_RUN = True  → faqat ko'rsatadi
DRY_RUN = False → bazani yangilaydi
"""
import sys
from decimal import Decimal

DRY_RUN = True   # <<< True=test, False=haqiqiy yangilash
WAREHOUSE_IDS = [18, 19]

sys.path.insert(0, "/root/eldor/erppos")
from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("=" * 65)
print("MANFIY QOLDIQLARNI TO'G'IRLASH (xavfsiz)")
print(f"Rejim: {'DRY RUN' if DRY_RUN else '!!! HAQIQIY YANGILASH !!!'}")
print("=" * 65)

# Har mahsulot+ombor uchun oxirgi inventarizatsiya
last_counts = db.execute(text("""
    SELECT DISTINCT ON (p.id, ic.warehouse_id)
        p.id AS product_id, p.name AS product_name,
        ic.warehouse_id, w.name AS warehouse_name,
        ici.counted_qty AS initial_qty
    FROM inventory_count_items ici
    JOIN inventory_counts ic ON ic.id = ici.count_id
    JOIN products p ON p.id = ici.product_id
    LEFT JOIN warehouses w ON w.id = ic.warehouse_id
    WHERE ic.warehouse_id = ANY(:wh_ids) AND ic.status = 'completed'
    ORDER BY p.id, ic.warehouse_id, ic.created_at DESC
"""), {"wh_ids": WAREHOUSE_IDS}).fetchall()

initial_map = {}
for r in last_counts:
    initial_map[(r.product_id, r.warehouse_id)] = Decimal(str(r.initial_qty or 0))

# Hozirgi manfiy qoldiqlar
neg_stocks = db.execute(text("""
    SELECT sl.product_id, sl.warehouse_id, sl.quantity,
           p.name as product_name, w.name as warehouse_name
    FROM stock_levels sl
    JOIN products p ON p.id = sl.product_id
    LEFT JOIN warehouses w ON w.id = sl.warehouse_id
    WHERE sl.warehouse_id = ANY(:wh_ids) AND sl.quantity < 0
    ORDER BY sl.quantity
"""), {"wh_ids": WAREHOUSE_IDS}).fetchall()

print(f"\nManfiy qoldiqlar: {len(neg_stocks)} ta")
print(f"{'Mahsulot':35s} {'Ombor':18s} {'Boshlang\'ich':>12s} {'Hozirgi':>10s} {'Yangi':>8s}")
print("-" * 85)

updates = []
for r in neg_stocks:
    key = (r.product_id, r.warehouse_id)
    initial = initial_map.get(key, None)

    if initial is None:
        print(f"{r.product_name[:35]:35s} {(r.warehouse_name or '?')[:18]:18s} {'N/A':>12s} {float(r.quantity):>10.2f} {'SKIP (inventarizatsiya yo\'q)':>8s}")
        continue

    if initial == Decimal("0") and r.quantity < 0:
        # Boshlang'ich 0 edi, manfiyga tushgan → 0 ga qaytaramiz
        print(f"{r.product_name[:35]:35s} {(r.warehouse_name or '?')[:18]:18s} {float(initial):>12.2f} {float(r.quantity):>10.2f} {'→ 0':>8s}  ← TO'G'IRLANADI")
        updates.append((r.product_id, r.warehouse_id, Decimal("0"), r.product_name, r.warehouse_name))
    else:
        print(f"{r.product_name[:35]:35s} {(r.warehouse_name or '?')[:18]:18s} {float(initial):>12.2f} {float(r.quantity):>10.2f} {'SKIP':>8s}  (boshlang'ich {float(initial):.1f})")

print(f"\nTo'g'irlanadigan: {len(updates)} ta")

if not DRY_RUN and updates:
    print("\nYangilanmoqda...")
    for pid, wid, new_qty, pname, wname in updates:
        db.execute(text(
            "UPDATE stock_levels SET quantity=:qty, updated_at=NOW() WHERE product_id=:pid AND warehouse_id=:wid"
        ), {"qty": float(new_qty), "pid": pid, "wid": wid})
        print(f"  ✓ {pname[:30]} [{wname}] → {float(new_qty):.2f}")
    db.commit()
    print("\n✅ Barcha to'g'irlamalar saqlandi!")
elif DRY_RUN:
    print("\n⚠️  DRY RUN — hech narsa o'zgartirilmadi.")
    print("Yangilash uchun: DRY_RUN = False qilib qayta ishga tushiring")

print("=" * 65)
db.close()
