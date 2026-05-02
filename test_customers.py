import traceback
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

def test_customers():
    db = SessionLocal()
    try:
        from app.models.user import User, UserStatus
        from app.routers.customers import list_customers
        
        user = db.query(User).filter(User.phone == '998900406080').first()
        if not user:
            user = db.query(User).filter(User.status == UserStatus.active).first()
            
        print(f"Testing list_customers for user id: {user.id}, phone: {user.phone}, company_id: {user.company_id}")
        
        res = list_customers(
            skip=0, limit=20, db=db, current_user=user,
            search=None
        )
        print("Success! Number of customers:", len(res))
        
    except Exception as e:
        print("Exception during list_customers:")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_customers()
