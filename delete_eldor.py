import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from app.database import engine
from sqlalchemy import text

def delete_company():
    with engine.connect() as conn:
        with conn.begin():
            # Search by name or org_code, just to be sure
            rows = conn.execute(text("SELECT id, name, phone, org_code FROM companies WHERE name ILIKE '%Eldor%' OR org_code = '74949003'")).fetchall()
            
            if not rows:
                print("Topilmadi: 'Eldor' yoki '74949003' kodli kompaniya yo'q.")
                
                print("Barcha kompaniyalar:")
                all_comps = conn.execute(text("SELECT id, name, phone, org_code FROM companies")).fetchall()
                for c in all_comps:
                    print(f"  ID={c.id} | {c.name} | {c.phone} | {c.org_code}")
                return
            
            for company in rows:
                cid = company.id
                print(f"O'chirilmoqda: ID={cid} | Name={company.name} | Phone={company.phone} | Code={company.org_code}")
                
                # Users
                users = conn.execute(text("SELECT id FROM users WHERE company_id = :cid"), {"cid": cid}).fetchall()
                for u in users:
                    conn.execute(text("DELETE FROM audit_logs WHERE user_id = :uid"), {"uid": u.id})
                
                # Boshqa jadvallar
                conn.execute(text("DELETE FROM currencies WHERE company_id = :cid"), {"cid": cid})
                conn.execute(text("DELETE FROM users WHERE company_id = :cid"), {"cid": cid})
                conn.execute(text("DELETE FROM branches WHERE company_id = :cid"), {"cid": cid})
                conn.execute(text("DELETE FROM companies WHERE id = :cid"), {"cid": cid})
                
                print(f"MUVAFFAQIYATLI O'CHIRILDI: {company.name}")

if __name__ == "__main__":
    delete_company()
