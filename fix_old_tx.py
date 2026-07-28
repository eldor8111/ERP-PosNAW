from dotenv import load_dotenv
load_dotenv()
from app.database import SessionLocal
from app.models.moliya import Transaction

db = SessionLocal()
try:
    # Update older transactions that were mistakenly saved as UZS to USD
    # We only target supplier_payment transactions that have small amounts
    txs = db.query(Transaction).filter(
        Transaction.type == "expense",
        Transaction.reference_type == "supplier_payment",
        Transaction.amount < 10000,
        Transaction.currency_code == "UZS"
    ).all()
    
    count = 0
    for tx in txs:
        # Check if description doesn't already contain USD
        if "USD" not in (tx.description or ""):
            tx.currency_code = "USD"
            count += 1
            
    db.commit()
    print(f"Successfully updated {count} old transactions to USD.")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
