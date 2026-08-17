import sys
sys.stdout.reconfigure(encoding='utf-8')
from decimal import Decimal
from app.database import SessionLocal
from app.models.user import User
from app.models.product import Product, ProductType, ProductConversion
from app.models.inventory import StockLevel, StockMovement
from app.schemas.sale import SaleCreate, SaleItemIn
from app.services.sale_service import create_sale
from fastapi import BackgroundTasks

db = SessionLocal()
try:
    user = db.query(User).first()
    
    # Check if Jgar exists, or get its ID. For simulation, let's just create dummy ones.
    parent = Product(name='Test Parent', company_id=user.company_id, cost_price=1000, sale_price=1500, status='active', product_type='stock', sku='P1', barcode='B1', unit='kg')
    db.add(parent)
    db.flush()
    
    child = Product(name='Test Child', company_id=user.company_id, cost_price=1000, sale_price=2000, status='active', product_type='sell', sku='C1', barcode='B2', unit='kg')
    db.add(child)
    db.flush()
    
    db.add(ProductConversion(sell_product_id=child.id, source_product_id=parent.id, ratio=Decimal('1.0')))
    db.flush()
    
    # Parent is in warehouse 2
    db.add(StockLevel(product_id=parent.id, warehouse_id=2, quantity=Decimal('100.0')))
    
    # Child is in warehouse 1 (but it shouldn't have stock anyway)
    # db.add(StockLevel(product_id=child.id, warehouse_id=1, quantity=Decimal('0.0')))
    db.commit()
    
    print("Parent ID:", parent.id, "Child ID:", child.id)
    
    # Now sell child in warehouse 1
    data = SaleCreate(
        warehouse_id=1,
        customer_id=None,
        payment_type='cash',
        paid_amount=Decimal('2000'),
        paid_cash=Decimal('2000'),
        items=[SaleItemIn(product_id=child.id, quantity=Decimal('2.0'), price=Decimal('2000'))]
    )
    
    bg = BackgroundTasks()
    sale = create_sale(db=db, data=data, current_user=user, ip=None, background_tasks=bg)
    
    # Check stock of parent
    p_stock = db.query(StockLevel).filter(StockLevel.product_id == parent.id).all()
    print("Parent Stock after sale:", [(s.warehouse_id, float(s.quantity)) for s in p_stock])
    
    # Check stock of child
    c_stock = db.query(StockLevel).filter(StockLevel.product_id == child.id).all()
    print("Child Stock after sale:", [(s.warehouse_id, float(s.quantity)) for s in c_stock])
    
    # Check movements
    movs = db.query(StockMovement).filter(StockMovement.reference_id == sale.id, StockMovement.reference_type == 'sale').all()
    for m in movs:
        print("Movement:", "Product:", m.product_id, "WH:", m.warehouse_id, "Qty Before:", m.qty_before, "Qty After:", m.qty_after)
        
finally:
    db.rollback()
