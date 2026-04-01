import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE sales ADD COLUMN customer_id INTEGER REFERENCES customers(id)"))
        conn.commit()
        print("Column customer_id added successfully!")
    except Exception as e:
        print(f"Error adding column: {e}")
