import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.database import engine, SessionLocal
from sqlalchemy import text
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.batch import Batch

def patch_db():
    print("Starting FIFO DB Patch...")
    with engine.connect() as conn:
        try:
            # 1. Modify batches table
            conn.execute(text("ALTER TABLE batches ALTER COLUMN lot_number DROP NOT NULL;"))
            conn.execute(text("ALTER TABLE batches ALTER COLUMN warehouse_id DROP NOT NULL;"))
            conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS initial_quantity NUMERIC(12, 3) DEFAULT 0;"))
            conn.execute(text("ALTER TABLE batches ADD COLUMN IF NOT EXISTS purchase_price NUMERIC(14, 2) DEFAULT 0;"))
            
            # 2. Create sale_item_batches
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sale_item_batches (
                    id SERIAL PRIMARY KEY,
                    sale_item_id INTEGER NOT NULL REFERENCES sale_items(id) ON DELETE CASCADE,
                    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
                    quantity NUMERIC(12, 3) NOT NULL,
                    unit_cost NUMERIC(14, 2) NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_sale_item_batches_sale_item_id ON sale_item_batches(sale_item_id);
                CREATE INDEX IF NOT EXISTS ix_sale_item_batches_batch_id ON sale_item_batches(batch_id);
            """))
            conn.commit()
            print("Schema modified successfully!")
        except Exception as e:
            print(f"Error modifying schema (might already exist): {e}")

    # 3. Seed missing batches for current stock so sales won't break
    print("Seeding initial batches for existing stock...")
    db = SessionLocal()
    try:
        stocks = db.query(StockLevel).filter(StockLevel.quantity > 0).all()
        created_count = 0
        for stock in stocks:
            # Check if this product/warehouse already has an active batch
            existing_batch = db.query(Batch).filter(
                Batch.product_id == stock.product_id,
                Batch.warehouse_id == stock.warehouse_id,
                Batch.quantity > 0
            ).first()
            
            if not existing_batch:
                product = db.query(Product).filter(Product.id == stock.product_id).first()
                cost = product.cost_price if product and product.cost_price else 0
                
                new_batch = Batch(
                    product_id=stock.product_id,
                    warehouse_id=stock.warehouse_id,
                    lot_number="INITIAL-STOCK",
                    initial_quantity=stock.quantity,
                    quantity=stock.quantity,
                    purchase_price=cost,
                    company_id=product.company_id if product else None
                )
                db.add(new_batch)
                created_count += 1
        db.commit()
        print(f"Seeded {created_count} initial batches for existing stock.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding batches: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    patch_db()
