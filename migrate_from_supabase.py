"""
Supabase -> Local PostgreSQL migration script
"""
import requests
import psycopg2
import time
import json
import os
import sys

SUPABASE_URL = "https://iuykdhoggtzdrdpstdvz.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "") or (sys.argv[1] if len(sys.argv) > 1 else "")
LOCAL_DB = "postgresql://erppos:Erppos2025x@localhost:5432/erppos"
if not SUPABASE_KEY:
    print("Usage: python migrate_from_supabase.py <key>")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "apikey": SUPABASE_KEY,
}

TABLES = [
    "agents",
    "companies",
    "branches",
    "users",
    "user_companies",
    "categories",
    "currencies",
    "warehouses",
    "bin_locations",
    "suppliers",
    "customers",
    "products",
    "shifts",
    "sales",
    "sale_items",
    "sale_payments",
    "purchase_orders",
    "po_items",
    "inventory_counts",
    "inventory_count_items",
    "stock_transfers",
    "stock_transfer_items",
    "finance_accounts",
    "finance_transactions",
]


def fetch_table(table):
    rows = []
    offset = 0
    limit = 1000
    while True:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            params={"select": "*", "offset": offset, "limit": limit},
            timeout=30,
        )
        if r.status_code == 404:
            print(f"  Table {table} not found in Supabase, skipping")
            return []
        if r.status_code != 200:
            print(f"  Error {r.status_code}: {r.text[:200]}")
            return rows
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
        time.sleep(0.05)
    return rows


def insert_rows(cur, table, rows):
    if not rows:
        return 0
    columns = list(rows[0].keys())
    col_names = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f'INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
    count = 0
    for row in rows:
        values = []
        for c in columns:
            v = row.get(c)
            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            values.append(v)
        try:
            cur.execute(sql, values)
            count += 1
        except Exception as e:
            print(f"  Row error in {table}: {e}")
            cur.connection.rollback()
            cur.execute("SET session_replication_role = 'replica';")
    return count


def main():
    conn = psycopg2.connect(LOCAL_DB)
    cur = conn.cursor()
    cur.execute("SET session_replication_role = 'replica';")
    conn.commit()

    total = 0
    for table in TABLES:
        print(f"Fetching {table}...", end=" ", flush=True)
        rows = fetch_table(table)
        if not rows:
            print("0 rows")
            continue
        print(f"{len(rows)} rows -> inserting...", end=" ", flush=True)
        n = insert_rows(cur, table, rows)
        conn.commit()
        total += n
        print(f"done ({n} inserted)")

    cur.execute("SET session_replication_role = 'DEFAULT';")
    conn.commit()
    cur.close()
    conn.close()
    print(f"\nMigration complete! Total rows inserted: {total}")


if __name__ == "__main__":
    main()
