import os
from dotenv import load_dotenv
load_dotenv()
from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS debt_amounts JSON DEFAULT '{}';"))
    conn.commit()
    print("Column added successfully!")
