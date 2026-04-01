import re
import os

FILE_PATH = 'app/routers/finance.py'

with open(FILE_PATH, 'r', encoding='utf-8') as f:
    text = f.read()

pattern = r'''(income = _base\("income"\)\s*expense = _base\("expense"\)\s*)(return \{)'''

replacement = r'''\1
    from app.models.company import Company
    comp = db.query(Company).filter(Company.id == user.company_id).first() if user.company_id else None
    
    \2
        "company_name": comp.name if comp else "Tizim",
        "org_code": comp.org_code if comp else "-",
'''

if 'company_name' not in text.split('def get_cash_balance')[1]:
    new_text = re.sub(pattern, replacement, text)
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(new_text)
    print("finance.py updated successfully.")
else:
    print("Already updated.")
