import traceback
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import Request

DB_URL = "postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

class MockClient:
    host = "127.0.0.1"

class MockRequest:
    client = MockClient()

def test_login():
    db = SessionLocal()
    try:
        from app.models.user import User, UserStatus
        from app.routers.auth import _process_login_success
        
        # We need to find the specific user who's experiencing 500
        user = db.query(User).filter(User.phone == '998900406080').first()
        if not user:
            user = db.query(User).filter(User.status == UserStatus.active).first()
            
        print(f"Testing for user id: {user.id}, phone: {user.phone}")
        
        req = MockRequest()
        
        res = _process_login_success(user, db, req)
        print("Success! Result:")
        print(res.model_dump())
        
    except Exception as e:
        print("Exception during _process_login_success:")
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_login()
