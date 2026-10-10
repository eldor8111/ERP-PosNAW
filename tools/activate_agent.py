import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.database import SessionLocal
from app.models.user import User, UserStatus, UserRole

db = SessionLocal()
try:
    u = db.query(User).filter(User.phone.like('%7663107%')).first()
    if u:
        u.status = UserStatus.active
        u.role = UserRole.marketplace_agent
        db.commit()
        print(f"Muvaffaqiyatli! {u.name} ({u.phone}) faollashtirildi! Status: ACTIVE")
    else:
        print("Botirjon (7663107) topilmadi!")
except Exception as e:
    db.rollback()
    print(f"Xatolik: {e}")
finally:
    db.close()
