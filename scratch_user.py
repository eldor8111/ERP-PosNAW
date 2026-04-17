import sys
import os
sys.path.append(os.getcwd())
try:
    from app.db.session import SessionLocal
    from app.models.user import User
    from app.models.user_company import UserCompany
    db = SessionLocal()
    u = db.query(User).filter(User.phone == '998933344602').first()
    if not u:
        print('User not found')
    else:
        print(f'User: {u.name}, status: {u.status}, role: {u.role}, company_id: {u.company_id}')
        for uc in u.companies:
            print(f' - Company: {uc.company_id}, role: {uc.role}, is_active: {uc.is_active}')
except Exception as e:
    import traceback
    traceback.print_exc()
