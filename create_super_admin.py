from app.database import SessionLocal
from app.models.user import User, UserRole, UserStatus
from app.core.security import hash_password

db = SessionLocal()
sa = db.query(User).filter(User.role == UserRole.super_admin).first()
if sa:
    sa.phone = "998999999999"
    sa.hashed_password = hash_password("superadmin123")
    db.commit()
    print("Mavjud Super Admin paroli yangilandi: login: 998999999999, parol: superadmin123")
else:
    new_sa = User(
        name="Asosiy Administrator",
        phone="998999999999",
        hashed_password=hash_password("superadmin123"),
        role=UserRole.super_admin,
        status=UserStatus.active,
    )
    db.add(new_sa)
    db.commit()
    print("Yangi Super Admin yaratildi: login: 998999999999, parol: superadmin123")
db.close()
