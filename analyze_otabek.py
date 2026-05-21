import sys
import os
import json

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import SessionLocal
from app.models.company import Company
from app.models.supplier import Supplier
from app.models.moliya import Transaction

db = SessionLocal()

print("--- Companies ---")
comps = db.query(Company).filter(Company.org_code == "97258662").all()
if not comps:
    comps = db.query(Company).filter(Company.id == 97258662).all()
if not comps:
    print("Could not find company by org_code or id '97258662'. Getting all...")
    comps = db.query(Company).all()

company_ids = [c.id for c in comps]
for c in comps:
    print(f"Company ID: {c.id}, Name: {c.name}, Org Code: {c.org_code}")

print("\n--- Suppliers ---")
suppliers = db.query(Supplier).filter(
    Supplier.company_id.in_(company_ids) if company_ids else True,
    Supplier.name.ilike("%Otabek%")
).all()

for s in suppliers:
    print(f"Supplier ID: {s.id}, Name: {s.name}, Phone: {s.phone}, Debt: {s.debt_balance}")

supplier_ids = [s.id for s in suppliers]

print("\n--- Transactions for Suppliers ---")
txs = db.query(Transaction).filter(
    Transaction.reference_type.in_(["supplier_payment", "kirim", "purchase_order", "expense", "income"]),
    Transaction.reference_id.in_(supplier_ids) if supplier_ids else True
).all()

for tx in txs:
    if tx.reference_id in supplier_ids:
        print(f"TX ID: {tx.id}, Type: {tx.type}, RefType: {tx.reference_type}, RefID: {tx.reference_id}, Amount: {tx.amount}, Date: {tx.created_at}")
        
db.close()
