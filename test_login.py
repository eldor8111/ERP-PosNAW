"""
Diagnose the 500 error on /api/auth/login by running through the login code path
with a real user, catching and printing any exceptions.
"""
import traceback
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql+psycopg2://postgres.iuykdhoggtzdrdpstdvz:Erppos2024!@aws-1-ap-northeast-1.pooler.supabase.com:6543/postgres"
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
db = Session()

try:
    from app.models.user import User, UserStatus
    from app.schemas.user import UserOut
    from app.core.security import create_access_token, create_refresh_token
    from app.core.audit import log_action

    # Get an admin user
    user = db.query(User).filter(User.status == UserStatus.active).first()
    print(f"Testing with user: {user.phone}, role: {user.role}")

    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    print(f"user_role: {user_role!r}")

    OTP_REQUIRED_ROLES = {"cashier", "manager", "accountant", "warehouse"}
    if user_role not in OTP_REQUIRED_ROLES:
        print("Not OTP role -> creating tokens...")
        access_token = create_access_token({"sub": str(user.id), "role": user_role})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        print(f"access_token created: {access_token[:20]}...")

        print("Running log_action...")
        log_action(db=db, action="LOGIN", entity_type="user", entity_id=user.id,
                   user_id=user.id, ip_address="127.0.0.1")
        db.commit()
        print("log_action OK")

        print("Running UserOut.model_validate...")
        user_out = UserOut.model_validate(user)
        print(f"UserOut OK: {user_out}")

        from app.schemas.user import TokenResponse
        result = TokenResponse(access_token=access_token, refresh_token=refresh_token, user=user_out)
        print("TokenResponse OK:", result)
    else:
        print("OTP required role, testing OTP path...")

except Exception:
    print("\n=== EXCEPTION IN LOGIN FLOW ===")
    traceback.print_exc()
finally:
    db.close()
