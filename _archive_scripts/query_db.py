from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    res = conn.execute(text("SELECT id, number, customer_id, total_amount, paid_amount, debt_amounts, before_debt_balances FROM sales WHERE number='S202608100074'"))
    for row in res:
        print(dict(row._mapping))
