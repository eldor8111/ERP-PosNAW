from app.database import engine, SessionLocal
from app.models.user import User, UserRole, UserStatus
from app.core.security import hash_password
from sqlalchemy import text

# 1. PostgreSQL enumni yangilab olamiz
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
    conn.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'super_admin';"))

# 2. Yangi sessiya ochamiz
db = SessionLocal()

try:
    # SQL orqali tekshiramiz (ORM filteridagi enum xatoligidan qochish uchun)
    existing_sa = db.execute(text("SELECT id, phone FROM users WHERE role = 'super_admin' LIMIT 1")).fetchone()

    if existing_sa:
        # Agarda super_admin allaqachon mavjud bo'lsa, parolini yangilaymiz
        sa_user = db.query(User).filter(User.id == existing_sa.id).first()
        sa_user.phone = "998999999999"
        sa_user.hashed_password = hash_password("superadmin123")
        db.commit()
        print("Mavjud Super Admin paroli va logini yangilandi:")
        print("Login: 998999999999 | Parol: superadmin123")
    else:
        # Agarda mavjud bo'lmasa, yangi Super Admin yaratamiz
        new_sa = User(
            name="Asosiy Administrator",
            phone="998999999999",
            hashed_password=hash_password("superadmin123"),
            role=UserRole.super_admin,
            status=UserStatus.active,
        )
        db.add(new_sa)
        db.commit()
        print("Yangi Super Admin muvaffaqiyatli yaratildi:")
        print("Login: 998999999999 | Parol: superadmin123")

except Exception as e:
    db.rollback()
    print(f"Xatolik yuz berdi: {e}")
finally:
    db.close()