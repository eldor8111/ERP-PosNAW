import os
from app.database import SessionLocal
from app.models.product import Product, ProductConversion

def run():
    db = SessionLocal()
    dumba = db.query(Product).filter(Product.name.ilike('%dumba%')).first()
    butun = db.query(Product).filter(Product.name.ilike('%butun qo%')).first()
    
    if not dumba or not butun:
        print("Mahsulotlar topilmadi")
        return
        
    print(f"Dumba ID: {dumba.id}, Type: {dumba.product_type}")
    print(f"Butun Qo'y ID: {butun.id}")
    
    # Ma'lumotlarni yangilash
    dumba.product_type = "sell"
    
    conv = db.query(ProductConversion).filter(ProductConversion.sell_product_id == dumba.id).first()
    if not conv:
        conv = ProductConversion(sell_product_id=dumba.id, source_product_id=butun.id, ratio=1)
        db.add(conv)
        print("Konversiya yaratildi")
    else:
        conv.source_product_id = butun.id
        conv.ratio = 1
        print("Konversiya yangilandi")
        
    db.commit()
    print("Muvaffaqiyatli saqlandi! Endi Dumba sotuvida Butun qo'ydan ayiradi.")

if __name__ == "__main__":
    run()
