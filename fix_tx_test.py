import sys
import os
import re

sys.path.append(os.path.join(os.getcwd(), 'app'))
from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("SELECT id, amount, currency_code, description FROM transactions WHERE description LIKE '%(%)%' AND currency_code = 'UZS'"))
    
    count = 0
    updates = []
    pattern = re.compile(r'\(([\d\.,]+)\s+([A-Z]{3})\)\s*$')
    for row in result:
        tx_id, amount, currency_code, desc = row
        if not desc: continue
        
        match = pattern.search(desc)
        if match:
            orig_amount_str = match.group(1).replace(',', '')
            orig_amount = float(orig_amount_str)
            orig_currency = match.group(2)
            
            # Check if it was converted
            if float(amount) > orig_amount * 1000:
                print(f"ID: {tx_id} | Desc: {desc} | Current: {amount} {currency_code} -> Target: {orig_amount} {orig_currency}")
                updates.append((orig_amount, orig_currency, tx_id))
                count += 1
                
    if updates:
        print(f"Total transactions to fix: {count}")
