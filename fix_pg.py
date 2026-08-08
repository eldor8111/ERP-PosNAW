import traceback

try:
    import psycopg2
    conn = psycopg2.connect("dbname=erppos user=postgres password=postgres host=localhost port=5432")
    cursor = conn.cursor()
    cursor.execute("SELECT id, amount, currency_code, description FROM transactions WHERE description LIKE '%(%)%' AND currency_code = 'UZS'")
    rows = cursor.fetchall()

    import re
    pattern = re.compile(r'\(([\d\.,]+)\s+([A-Z]{3})\)\s*$')
    updates = []

    for row in rows:
        tx_id, amount, currency_code, desc = row
        if not desc: continue
        
        match = pattern.search(desc)
        if match:
            orig_amount_str = match.group(1).replace(',', '')
            orig_amount = float(orig_amount_str)
            orig_currency = match.group(2)
            
            # Verify it was likely converted (amount in db is at least 1000x larger)
            if float(amount) > orig_amount * 1000:
                print(f"Fixing ID {tx_id}: {amount} UZS -> {orig_amount} {orig_currency}")
                updates.append((orig_amount, orig_currency, tx_id))

    if updates:
        for amt, curr, tid in updates:
            cursor.execute("UPDATE transactions SET amount = %s, currency_code = %s WHERE id = %s", (amt, curr, tid))
        conn.commit()
        print(f"Fixed {len(updates)} transactions in postgres db.")
    else:
        print("No transactions to fix.")

    conn.close()
except Exception as e:
    traceback.print_exc()
