from app.database import SessionLocal
from app.models.product import Product, ProductConversion

db = SessionLocal()

dumbas = db.query(Product).filter(Product.name.ilike('%dumba%'), Product.is_deleted == False).all()
print(f"Found {len(dumbas)} Dumba(s)")

for p in dumbas:
    print(f"\nID: {p.id} | Name: {p.name} | Type: {p.product_type} | Barcode: {p.barcode}")
    conv = db.query(ProductConversion).filter(ProductConversion.sell_product_id == p.id).first()
    if conv:
        src = db.query(Product).filter(Product.id == conv.source_product_id).first()
        print(f"  -> Conversion Exists! Source: {src.name if src else 'NOT FOUND'} (ID: {conv.source_product_id}), Ratio: {conv.ratio}")
    else:
        print("  -> NO CONVERSION FOUND!")
