"""
Bu script 97258662 (va boshqa) kompaniyalar uchun yozilmagan
supplier_payment tranzaksiyalarini topib, bazaga qo'shadi.

ISHLATISH: python fix_missing_supplier_transactions.py
"""
import sys
sys.path.insert(0, '.')

from app.database import SessionLocal
from app.models.moliya import Transaction
from app.models.supplier import Supplier
from app.core.audit import AuditLog
from sqlalchemy import text
from datetime import datetime

db = SessionLocal()

try:
    # company_id=2 → 97258662 tashkilot (o'zgartiring kerak bo'lsa)
    COMPANY_ID = 2  # <-- 97258662 kompaniyasining ID sini aniqlang

    # Barcha kompaniyalar ro'yxatini ko'rsatish
    from app.models.company import Company
    companies = db.query(Company).all()
    print("\n=== KOMPANIYALAR ===")
    for c in companies:
        print(f"  ID={c.id}, Org kodi={c.org_code}, Nomi={c.name}")
    
    print("\n=== AUDIT LOG dan yozilmagan to'lovlarni izlash ===")
    
    # AuditLog dan PAY_DEBT amallarini topish
    missing = []
    try:
        logs = db.query(AuditLog).filter(
            AuditLog.action == "PAY_DEBT",
            AuditLog.entity_type == "supplier",
        ).all()
        
        for log in logs:
            # Bu to'lov uchun transaction bormi?
            tx = db.query(Transaction).filter(
                Transaction.reference_type == "supplier_payment",
                Transaction.reference_id == log.entity_id,
                Transaction.type == "expense",
            ).first()
            
            if not tx:
                amount = log.new_values.get("amount") if log.new_values else None
                reason = log.new_values.get("reason") if log.new_values else "Qarz to'lovi"
                print(f"  ⚠ Tranzaksiya YO'Q: supplier_id={log.entity_id}, summa={amount}, vaqt={log.created_at}")
                missing.append({
                    "supplier_id": log.entity_id,
                    "amount": amount,
                    "reason": reason,
                    "created_at": log.created_at,
                    "user_id": log.user_id,
                })
            else:
                print(f"  ✓ Tranzaksiya bor: supplier_id={log.entity_id}, tx_id={tx.id}")
    except Exception as e:
        print(f"AuditLog yo'q yoki xato: {e}")
    
    if not missing:
        print("\n✅ Barcha to'lovlar uchun tranzaksiya mavjud!")
    else:
        print(f"\n⚠ {len(missing)} ta yozilmagan tranzaksiya topildi!")
        
        confirm = input("\nUlarni bazaga qo'shishni xohlaysizmi? (yes/no): ").strip().lower()
        if confirm == 'yes':
            for item in missing:
                if not item["amount"]:
                    print(f"  ⛔ Summa yo'q, o'tkazildi: {item}")
                    continue
                
                # Supplier'ning company_id sini olish
                supplier = db.get(Supplier, item["supplier_id"])
                if not supplier:
                    print(f"  ⛔ Supplier {item['supplier_id']} topilmadi")
                    continue
                
                new_tx = Transaction(
                    company_id=supplier.company_id,
                    branch_id=0,
                    wallet_id=None,
                    type="expense",
                    amount=float(item["amount"]),
                    payment_type="cash",
                    reference_type="supplier_payment",
                    reference_id=item["supplier_id"],
                    description=item["reason"] or "Qarz to'lovi (tiklangan)",
                    created_at=item["created_at"],
                )
                db.add(new_tx)
                print(f"  ✅ Qo'shildi: supplier_id={item['supplier_id']}, summa={item['amount']}")
            
            db.commit()
            print("\n✅ Saqlandi!")
        else:
            print("Bekor qilindi.")

except Exception as e:
    db.rollback()
    import traceback
    traceback.print_exc()
finally:
    db.close()
