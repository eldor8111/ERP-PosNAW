import asyncio
from app.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password

async def create_user():
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.phone == '+998991234567').first()
        if existing_user:
            print("Foydalanuvchi allaqachon mavjud: +998991234567 / admin123")
            return

        from app.models.company import Company
        company = db.query(Company).filter(Company.id == 1).first()
        if not company:
            company = Company(name="Lokal Kompaniya")
            db.add(company)
            db.commit()
            db.refresh(company)

        new_user = User(
            phone='+998991234567',
            hashed_password=hash_password('admin123'),
            name='Lokal Admin',
            role='director',
            status='active',
            company_id=company.id
        )
        db.add(new_user)
        db.commit()
        print("Lokal foydalanuvchi yaratildi! Login: +998991234567 Parol: admin123")
    except Exception as e:
        print(f"Xatolik: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(create_user())
