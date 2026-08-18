from app.database import engine
from sqlalchemy import text
import pprint

with engine.connect() as conn:
    print("----- SALE -----")
    res = conn.execute(text("SELECT id, number, customer_id, total_amount, paid_amount, debt_amounts, before_debt_balances FROM sales WHERE number='S202608100074'"))
    for row in res:
        pprint.pprint(dict(row._mapping))
        
    print("\n----- CUSTOMER -----")
    c_res = conn.execute(text("SELECT id, name, debt_balance, debt_currency, debt_balances FROM customers WHERE id=1001"))
    for row in c_res:
        pprint.pprint(dict(row._mapping))
