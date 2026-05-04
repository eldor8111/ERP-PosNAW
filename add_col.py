import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/erp_pos"

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE products ADD COLUMN product_code VARCHAR(100);"))
        print("Column product_code added.")
    except Exception as e:
        print(f"Error (maybe already exists): {e}")

    try:
        conn.execute(text("CREATE INDEX ix_products_product_code ON products (product_code);"))
        print("Index added.")
    except Exception as e:
        print(f"Error (maybe already exists): {e}")
