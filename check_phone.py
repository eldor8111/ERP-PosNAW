import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    rows = conn.execute(text("SELECT id, name, phone, role, status FROM users WHERE phone LIKE '%933344602%'")).fetchall()
    if rows:
        for r in rows:
            print(f"ID={r.id} | {r.name} | {r.phone} | {r.role} | {r.status}")
    else:
        print("users: topilmadi")
    
    rows2 = conn.execute(text("SELECT id, name, phone FROM companies WHERE phone LIKE '%933344602%'")).fetchall()
    if rows2:
        for r in rows2:
            print(f"company ID={r.id} | {r.name} | {r.phone}")
    else:
        print("companies: topilmadi")
