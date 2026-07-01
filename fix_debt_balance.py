#!/usr/bin/env python3
"""
Barcha mijozlarning debt_balance ni debt_balances + joriy kurs asosida qayta hisoblaydi.
"""
import sys
from decimal import Decimal
from app.database import SessionLocal
from app.models.customer import Customer
from app.models.currency import Currency

db = SessionLocal()

try:
    # Joriy kurslarni olish
    currencies = {c.code: Decimal(str(c.rate)) for c in db.query(Currency).all()}
    print("Joriy kurslar:", {k: float(v) for k, v in currencies.items()})

    customers = db.query(Customer).all()
    updated = 0
    for cust in customers:
        balances = dict(cust.debt_balances or {})
        if not balances:
            continue
        total_uzs = Decimal("0")
        for curr, amt in balances.items():
            if curr == "UZS":
                total_uzs += Decimal(str(amt))
            else:
                rate = currencies.get(curr, Decimal("1"))
                total_uzs += Decimal(str(amt)) * rate

        old = float(cust.debt_balance or 0)
        print(f"  {cust.name}: {old} → {float(total_uzs)}  (balances: {balances})")
        cust.debt_balance = total_uzs
        updated += 1

    db.commit()
    print(f"\n✅ {updated} ta mijoz qarzi yangilandi!")
finally:
    db.close()
