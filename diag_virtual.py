import sys
sys.stdout.reconfigure(encoding="utf-8")
from app.database import SessionLocal
from app.models.product import Product, ProductConversion
from app.models.inventory import StockLevel, StockMovement
from app.models.sale import Sale, SaleItem

db = SessionLocal()

print("=== MAHSULOTLAR ===")
for p in db.query(Product).filter(Product.is_deleted == False).order_by(Product.id).all():
    print(f"  [{p.id}] {p.name!r} type={p.product_type} company={p.company_id}")

print("\n=== KONVERSIYALAR ===")
for c in db.query(ProductConversion).all():
    sell = db.query(Product).get(c.sell_product_id)
    src = db.query(Product).get(c.source_product_id)
    sn = sell.name if sell else "?"
    stn = src.name if src else "?"
    print(f"  sell={c.sell_product_id} ({sn}) -> source={c.source_product_id} ({stn}) ratio={c.ratio}")

print("\n=== QOLDIQLAR ===")
for s in db.query(StockLevel).all():
    p = db.query(Product).get(s.product_id)
    pn = p.name if p else "?"
    print(f"  product={s.product_id} ({pn}) wh={s.warehouse_id} qty={s.quantity}")

print("\n=== OXIRGI 5 SOTUV ===")
sales = db.query(Sale).order_by(Sale.id.desc()).limit(5).all()
for sale in sales:
    items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
    for it in items:
        prod = db.query(Product).get(it.product_id)
        pn = prod.name if prod else str(it.product_id)
        print(f"  sale#{sale.id} {sale.number} status={sale.status} item={pn} qty={it.quantity} wh={sale.warehouse_id}")

print("\n=== OXIRGI STOCK MOVEMENTS ===")
movs = db.query(StockMovement).order_by(StockMovement.id.desc()).limit(15).all()
for m in movs:
    p = db.query(Product).get(m.product_id)
    pn = p.name if p else str(m.product_id)
    print(f"  [{m.id}] {pn} {m.type} qty={m.quantity} reason={m.reason!r} ref={m.reference_type}#{m.reference_id}")

db.close()
