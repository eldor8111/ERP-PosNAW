import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.database import SessionLocal
from app.models.sale import Sale

db = SessionLocal()
sales = db.query(Sale).all()
print(f"Total sales in DB: {len(sales)}")

for s in sales:
    print(f"Sale ID={s.id} | number={s.number} | company_id={s.company_id} | dt={s.created_at} | wh={s.warehouse_id}")

db.close()
