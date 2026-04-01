import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from app.database import engine
from sqlalchemy import text

def delete_company():
    with engine.connect() as conn:
        with conn.begin():
            rows = conn.execute(text("SELECT id, name, phone, org_code FROM companies WHERE name ILIKE '%sdsd%'")).fetchall()
            
            if not rows:
                print("Topilmadi: 'sdsd' nomli kompaniya yo'q.")
                return
            
            company = rows[0]
            cid = company.id
            print(f"Topildi: ID={cid} | Name={company.name} | Phone={company.phone}")
            
            # Users
            users = conn.execute(text("SELECT id FROM users WHERE company_id = :cid"), {"cid": cid}).fetchall()
            for u in users:
                conn.execute(text("DELETE FROM audit_logs WHERE user_id = :uid"), {"uid": u.id})
            
            # Currencies
            conn.execute(text("DELETE FROM currencies WHERE company_id = :cid"), {"cid": cid})
            
            # Users
            conn.execute(text("DELETE FROM users WHERE company_id = :cid"), {"cid": cid})
            
            # Branches
            conn.execute(text("DELETE FROM branches WHERE company_id = :cid"), {"cid": cid})
            
            # Company
            conn.execute(text("DELETE FROM companies WHERE id = :cid"), {"cid": cid})
            
            print(f"MUVAFFAQIYATLI O'CHIRILDI: {company.name} kompaniyasi va bog'liq foydalanuvchilar.")

if __name__ == "__main__":
    delete_company()
