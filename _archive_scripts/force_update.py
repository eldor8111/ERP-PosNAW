from app.database import SessionLocal
from app.models.product import Product, ProductConversion
from app.models.inventory import StockLevel

db = SessionLocal()
try:
    dumba = db.query(Product).filter(Product.name.ilike('%dumba%'), Product.is_deleted == False).first()
    butun = db.query(Product).filter(Product.name.ilike('%butun qo%'), Product.is_deleted == False).first()

    if not dumba:
        print("Dumba topilmadi!")
    elif not butun:
        print("Butun qo'y topilmadi!")
    else:
        print(f"Oldingi holat: {dumba.name} -> {dumba.product_type}")
        dumba.product_type = "sell"
        
        conv = db.query(ProductConversion).filter(ProductConversion.sell_product_id == dumba.id).first()
        if conv:
            conv.source_product_id = butun.id
            conv.ratio = 1.0
        else:
            db.add(ProductConversion(sell_product_id=dumba.id, source_product_id=butun.id, ratio=1.0))
        
        db.query(StockLevel).filter(StockLevel.product_id == dumba.id).delete(synchronize_session=False)
        db.commit()
        
        print(f"Muvaffaqiyatli saqlandi! Yangi holat: {dumba.name} -> {dumba.product_type}")
finally:
    db.close()
