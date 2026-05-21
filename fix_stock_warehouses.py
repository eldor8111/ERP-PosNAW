import asyncio
from app.database import SessionLocal
from app.models.inventory import StockLevel
from app.models.warehouse import Warehouse
from sqlalchemy.orm import Session

def fix_unassigned_stock():
    db: Session = SessionLocal()
    try:
        # Find all stock levels where warehouse_id is NULL
        unassigned_stocks = db.query(StockLevel).filter(StockLevel.warehouse_id == None).all()
        
        fixed_count = 0
        
        for stock in unassigned_stocks:
            # get the company id from the product
            company_id = stock.product.company_id if stock.product else None
            if not company_id:
                continue
                
            # Find the first warehouse for this company
            first_wh = db.query(Warehouse).filter(Warehouse.company_id == company_id).order_by(Warehouse.id.asc()).first()
            if first_wh:
                stock.warehouse_id = first_wh.id
                fixed_count += 1
                
        db.commit()
        print(f"Fixed {fixed_count} unassigned stock records.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fix_unassigned_stock()
