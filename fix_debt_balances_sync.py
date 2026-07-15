"""
Barcha mijozlardagi debt_balance va debt_balances ni sinxronlashtiradi.
Excel import qilingan eski mijozlarda debt_balances bor, lekin debt_balance = 0 bo'lishi mumkin.
Yoki debt_balance bor, lekin debt_balances = {} bo'lishi mumkin.

Mantiq (modal add kabi):
  - debt_balances bo'sh bo'lmasa → debt_balance = sum(debt_balances UZS ekvivalenti)
  - debt_balance > 0 lekin debt_balances bo'sh bo'lsa → debt_balances = {currency: debt_balance}
"""
import os, sys
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL topilmadi (.env faylini tekshiring)")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
db = Session()

from app.models.customer import Customer
from app.models.currency import Currency as CurrencyModel

# Barcha valyuta kurslarini yuklaymiz
currencies_map = {c.code: Decimal(str(c.rate)) for c in db.query(CurrencyModel).all()}
currencies_map.setdefault("UZS", Decimal("1"))

customers = db.query(Customer).all()
fixed = 0

for cust in customers:
    balances = cust.debt_balances or {}
    old_balance = Decimal(str(cust.debt_balance or 0))
    
    if balances and any(float(v or 0) > 0 for v in balances.values()):
        # debt_balances bor → debt_balance ni qayta hisoblaymiz
        new_balance = sum(
            (Decimal(str(amt)) * currencies_map.get(str(curr).strip().upper(), Decimal("1"))
             for curr, amt in balances.items()),
            Decimal("0")
        )
        if abs(new_balance - old_balance) > Decimal("0.01"):
            print(f"  [{cust.id}] {cust.name}: debt_balance {old_balance} → {new_balance} (balances={balances})")
            cust.debt_balance = new_balance
            cust.debt_currency = "UZS"
            fixed += 1
    elif old_balance > 0 and not balances:
        # debt_balance bor, lekin debt_balances yo'q → to'ldiramiz
        currency = (cust.debt_currency or "UZS").strip().upper() or "UZS"
        new_balances = {currency: float(old_balance)}
        print(f"  [{cust.id}] {cust.name}: debt_balances bo'sh → {new_balances}")
        cust.debt_balances = new_balances
        flag_modified(cust, "debt_balances")
        fixed += 1

print(f"\nJami {len(customers)} ta mijoz tekshirildi, {fixed} ta to'g'rilandi.")
if fixed > 0:
    confirm = input("O'zgarishlarni saqlashni xohlaysizmi? (y/n): ")
    if confirm.lower() == 'y':
        db.commit()
        print("Saqlandi.")
    else:
        db.rollback()
        print("Bekor qilindi.")
else:
    print("Barcha ma'lumotlar sinxron.")

db.close()
