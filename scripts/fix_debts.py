import os
import sys

# Django/FastAPI uchun yo'llarni to'g'rilash
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.customer import Customer
from sqlalchemy.orm.attributes import flag_modified

def fix_customer_debts():
    db = SessionLocal()
    try:
        customers = db.query(Customer).all()
        fixed_count = 0
        
        for c in customers:
            # 1. Agar debt_balances dictionary bo'lmasa, uni to'g'irlaymiz
            if not isinstance(c.debt_balances, dict):
                c.debt_balances = {}
                flag_modified(c, "debt_balances")
            
            # 2. Xatolik sababli manfiy bo'lib qolgan debt_balances larni tekshiramiz
            has_negative = False
            for curr, amt in c.debt_balances.items():
                if float(amt) < 0:
                    has_negative = True
                    break
                    
            if has_negative:
                print(f"Mijoz (ID: {c.id}, Ism: {c.name}) qarzlari manfiy: {c.debt_balances}. Asl balans: {c.debt_balance}")
                
                # Agar haqiqiy debt_balance noldan katta bo'lsa (qarz bo'lsa) va manfiy UZS yozilgan bo'lsa:
                if float(c.debt_balance or 0) >= 0:
                    legacy_curr = (c.debt_currency or "UZS").strip().upper()
                    # Qarzni debt_balance dan olib tiklaymiz
                    c.debt_balances = {legacy_curr: float(c.debt_balance or 0)}
                    flag_modified(c, "debt_balances")
                    fixed_count += 1
                    print(f" -> TUZATILDI: {c.debt_balances}")
                
        if fixed_count > 0:
            db.commit()
            print(f"\nJami {fixed_count} ta mijozning qarzi tuzatildi.")
        else:
            print("\nBarcha mijozlarning qarzlari joyida, tuzatish talab etilmaydi.")
            
    except Exception as e:
        print(f"Xatolik yuz berdi: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_customer_debts()
