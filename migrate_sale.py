import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'test.db')
print("DB Path:", db_path)

try:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("ALTER TABLE sales ADD COLUMN before_debt_balances JSON;")
    conn.commit()
    conn.close()
    print("Successfully added before_debt_balances column")
except Exception as e:
    print(f"Error: {e}")
