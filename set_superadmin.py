import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    conn.execute(text("UPDATE users SET role = 'super_admin' WHERE id = 11"))
    conn.commit()
    print("MUVAFFAQIYATLI: ID=11 (Ubaydullayev Javohir) roli super_admin ga ozgartirildi!")
    print("Endi login qiling: http://localhost:5173/login")
