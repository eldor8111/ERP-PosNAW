"""
Qoldiq to'g'irlash skripti (Reconciliation v2)
===============================================
MANTIQ:
  1. Har bir mahsulot+ombor uchun ENG OXIRGI inventarizatsiya (counted_qty) = boshlang'ich qoldiq
  2. O'sha inventarizatsiyadan keyin bo'lgan barcha sotuvlarni yechamiz
  3. To'g'ri joriy qoldiq = counted_qty - jami_sotilgan
  4. stock_levels jadvalini yangilaymiz

DRY_RUN = True  →  faqat ko'rsatadi, o'zgartirmaydi
DRY_RUN = False →  bazani yangilaydi
"""

import sys
from decimal import Decimal
from collections import defaultdict

DRY_RUN = True          # <<< True = xavfsiz test, False = haqiqiy yangilash
WAREHOUSE_IDS = [18, 19]  # Ombor Sveji (18), Ombor Marazelka (19)

sys.path.insert(0, "/root/eldor/erppos")
from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("=" * 75)
print("QOLDIQ TO'G'IRLASH SKRIPTI v2")
print(f"Rejim: {'DRY RUN (hech narsa o\'zgartirilmaydi)' if DRY_RUN else '!!! HAQIQIY YANGILASH !!!'}")
print(f"Omborlar: {WAREHOUSE_IDS}")
print("=" * 75)

# ── 1. Har bir mahsulot+ombor uchun ENG OXIRGI inventarizatsiyani topamiz ──
print("\n[1] Har mahsulot uchun eng oxirgi inventarizatsiya o'qilmoqda...")

last_counts = db.execute(text("""
    SELECT DISTINCT ON (p.id, ic.warehouse_id)
        p.id         AS product_id,
        p.name       AS product_name,
        ic.warehouse_id,
        w.name       AS warehouse_name,
        ic.id        AS count_id,
        ic.created_at AS counted_at,
        ici.counted_qty AS initial_qty
    FROM inventory_count_items ici
    JOIN inventory_counts ic ON ic.id = ici.count_id
    JOIN products p ON p.id = ici.product_id
    LEFT JOIN warehouses w ON w.id = ic.warehouse_id
    WHERE ic.warehouse_id = ANY(:wh_ids)
      AND ic.status = 'completed'
    ORDER BY p.id, ic.warehouse_id, ic.created_at DESC
"""), {"wh_ids": WAREHOUSE_IDS}).fetchall()

print(f"  Topilgan: {len(last_counts)} ta mahsulot+ombor kombinatsiyasi")

# ── 2. Jun 1 dan beri sotuvlarni warehouse_id bo'yicha jamlaymiz ──
print("\n[2] Jun 1 dan beri barcha sotuvlar jamlanmoqda...")

sold_rows = db.execute(text("""
    SELECT
        si.product_id,
        si.warehouse_id,
        SUM(si.quantity) AS total_sold
    FROM sale_items si
    JOIN sales s ON s.id = si.sale_id
    WHERE s.created_at >= '2026-06-01 00:00:00'
      AND s.status NOT IN ('cancelled', 'refunded')
      AND si.warehouse_id = ANY(:wh_ids)
    GROUP BY si.product_id, si.warehouse_id
"""), {"wh_ids": WAREHOUSE_IDS}).fetchall()

sold_map = {}
for r in sold_rows:
    sold_map[(r.product_id, r.warehouse_id)] = Decimal(str(r.total_sold))

print(f"  Topilgan: {len(sold_map)} ta mahsulot+ombor sotuvlar")

# ── 3. To'g'ri joriy qoldiqni hisoblaymiz ──
print("\n[3] Hisoblash...")
print("-" * 75)
print(f"{'Mahsulot':30s} {'Ombor':18s} {'Boshlang\'ich':>12s} {'Sotilgan':>10s} {'To\'g\'ri':>10s} {'Hozirgi':>10s} {'Farq':>8s}")
print("-" * 75)

updates = []  # (product_id, warehouse_id, correct_qty, old_qty)

for row in last_counts:
    pid = row.product_id
    wid = row.warehouse_id
    
    initial = Decimal(str(row.initial_qty)) if row.initial_qty is not None else Decimal("0")
    sold = sold_map.get((pid, wid), Decimal("0"))
    correct = initial - sold
    
    # Hozirgi qoldiq
    cur = db.execute(text(
        "SELECT quantity FROM stock_levels WHERE product_id=:pid AND warehouse_id=:wid"
    ), {"pid": pid, "wid": wid}).fetchone()
    
    current_qty = Decimal(str(cur.quantity)) if cur else Decimal("0")
    diff = correct - current_qty
    
    flag = " ✓" if abs(diff) < Decimal("0.01") else " ← TO'G'IRLASH KERAK"
    print(f"{row.product_name[:30]:30s} {(row.warehouse_name or 'NULL')[:18]:18s} {float(initial):>12.2f} {float(sold):>10.2f} {float(correct):>10.2f} {float(current_qty):>10.2f} {float(diff):>+8.2f}{flag}")
    
    if abs(diff) >= Decimal("0.001"):
        updates.append((pid, wid, correct, current_qty, row.product_name, row.warehouse_name))

# ── 4. Yangilash ──
print(f"\n[4] To'g'irlash kerak bo'lgan qatorlar soni: {len(updates)}")

if not DRY_RUN and updates:
    print("\n  Yangilanmoqda...")
    for pid, wid, correct_qty, old_qty, pname, wname in updates:
        # stock_levels ni yangilaymiz
        existing = db.execute(text(
            "SELECT id FROM stock_levels WHERE product_id=:pid AND warehouse_id=:wid"
        ), {"pid": pid, "wid": wid}).fetchone()
        
        if existing:
            db.execute(text(
                "UPDATE stock_levels SET quantity=:qty, updated_at=NOW() WHERE product_id=:pid AND warehouse_id=:wid"
            ), {"qty": float(correct_qty), "pid": pid, "wid": wid})
        else:
            db.execute(text(
                "INSERT INTO stock_levels (product_id, warehouse_id, quantity) VALUES (:pid, :wid, :qty)"
            ), {"pid": pid, "wid": wid, "qty": float(correct_qty)})
        
        print(f"  ✓ {pname[:30]} [{wname}]: {float(old_qty):.2f} → {float(correct_qty):.2f}")
    
    db.commit()
    print("\n  ✅ Barcha qoldiqlar yangilandi!")
elif DRY_RUN and updates:
    print("\n  ⚠️  DRY RUN rejimida — hech narsa o'zgartirilmadi.")
    print("  Haqiqiy yangilash uchun: DRY_RUN = False qilib qayta ishga tushiring.")
else:
    print("\n  ✅ Hamma qoldiq to'g'ri, yangilash shart emas!")

print("\n" + "=" * 75)
print("XULOSA - Hozirgi MANFIY qoldiqlar (to'g'irlanmagan):")
neg = db.execute(text("""
    SELECT p.name, w.name as wname, sl.quantity
    FROM stock_levels sl
    JOIN products p ON p.id = sl.product_id
    LEFT JOIN warehouses w ON w.id = sl.warehouse_id
    WHERE sl.warehouse_id = ANY(:wh_ids) AND sl.quantity < 0
    ORDER BY sl.quantity
"""), {"wh_ids": WAREHOUSE_IDS}).fetchall()

if neg:
    for r in neg:
        print(f"  {r.name[:35]:35s} [{r.wname}]: {float(r.quantity):.2f}")
else:
    print("  Manfiy qoldiq yo'q! ✅")
print("=" * 75)
db.close()
