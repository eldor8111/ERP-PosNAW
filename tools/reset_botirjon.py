import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password

db = SessionLocal()
try:
    u = db.query(User).filter(User.phone.like('%7663107%')).first()
    if u:
        u.hashed_password = hash_password('123456')
        db.commit()
        print(f"Muvaffaqiyatli! {u.name} ({u.phone}) paroli '123456' ga o'rnatildi!")
    else:
        print("Botirjon (7663107) topilmadi!")
except Exception as e:
    db.rollback()
    print(f"Xatolik: {e}")
finally:
    db.close()
