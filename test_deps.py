import traceback
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

def test_dependencies():
    db = SessionLocal()
    try:
        from app.models.user import User, UserStatus
        from sqlalchemy.orm.attributes import set_committed_value
        
        user = db.query(User).filter(User.phone == '998900406080').first()
        if not user:
            user = db.query(User).filter(User.status == UserStatus.active).first()
            
        print(f"Before: User is dirty? {user in db.dirty}")
        set_committed_value(user, 'company_id', 999)
        print(f"After set_committed_value: User is dirty? {user in db.dirty}, company_id={user.company_id}")
        
        # Test if autoflush triggers exception
        from app.models.customer import Customer
        db.query(Customer).filter(Customer.company_id == 999).all()
        print("db.query completed successfully!")
        
    except Exception as e:
        print("Exception during test:")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_dependencies()
