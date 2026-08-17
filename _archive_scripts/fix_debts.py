import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.supplier import Supplier
from app.models.purchase_order import PurchaseOrder, POStatus, POItem
from app.models.moliya import Transaction
from app.models.currency import Currency
from sqlalchemy.orm.attributes import flag_modified

def run_fix():
    db = SessionLocal()
    try:
        suppliers = db.query(Supplier).all()
        
        # Valyuta kurslari
        rates = {}
        for c in db.query(Currency).all():
            rates[c.code] = float(c.rate)
        rates["UZS"] = 1.0
        
        updated_count = 0
        
        for sup in suppliers:
            # Barcha xaridlar
            pos = db.query(PurchaseOrder).filter(
                PurchaseOrder.supplier_id == sup.id, 
                PurchaseOrder.status != POStatus.cancelled
            ).order_by(PurchaseOrder.created_at.asc()).all()
            
            # Barcha to'lovlar (Xarid paytida qilingan yoki alohida qilingan to'lovlar)
            txs = db.query(Transaction).filter(
                Transaction.reference_type.in_(["supplier_payment", "purchase_order"]),
                Transaction.reference_id == sup.id,
                Transaction.type == "expense"
            ).order_by(Transaction.created_at.asc()).all()
            
            debt_balances = {}
            
            # 1. Xaridlarni qarzga qo'shish
            for po in pos:
                # Har bir mahsulot bo'yicha haqiqiy valyuta qarzini qo'shish
                for item in po.items:
                    cur = item.cost_currency or 'UZS'
                    if cur != 'UZS' and item.original_unit_cost:
                        amt = float(item.original_unit_cost) * float(item.qty_ordered)
                    else:
                        amt = float(item.unit_cost) * float(item.qty_ordered)
                    
                    if amt > 0:
                        debt_balances[cur] = debt_balances.get(cur, 0.0) + amt
                
                # Agar PO da umumiy chegirma (discount) bo'lsa, uni UZS to'lovi kabi qarzdan ayiramiz
                po_discount = float(po.discount_amount or 0)
                if po_discount > 0:
                    rem_uzs = po_discount
                    if 'UZS' in debt_balances and debt_balances['UZS'] > 0:
                        ded = min(debt_balances['UZS'], rem_uzs)
                        debt_balances['UZS'] -= ded
                        rem_uzs -= ded
                    
                    if rem_uzs > 0.001:
                        for c_cur, c_amt in list(debt_balances.items()):
                            if c_amt <= 0: continue
                            c_rate = rates.get(c_cur, 1.0)
                            d_uzs = c_amt * c_rate
                            cover = min(rem_uzs, d_uzs)
                            debt_balances[c_cur] -= (cover / c_rate)
                            rem_uzs -= cover
                            if rem_uzs <= 0.001: break

            # 2. To'lovlarni qarzdan ayirish
            for tx in txs:
                tx_cur = tx.currency_code or 'UZS'
                tx_amt = float(tx.amount or 0)
                
                remaining_uzs = tx_amt * rates.get(tx_cur, 1.0)
                
                # Avval to'lov valyutasining o'zidan ayiramiz
                if tx_cur in debt_balances and debt_balances[tx_cur] > 0:
                    deducted = min(debt_balances[tx_cur], tx_amt)
                    debt_balances[tx_cur] -= deducted
                    remaining_uzs -= (deducted * rates.get(tx_cur, 1.0))
                    
                # Qolganini boshqa valyutalardan kurs bo'yicha ayiramiz
                if remaining_uzs > 0.001:
                    for cur, amt in list(debt_balances.items()):
                        if cur == tx_cur or amt <= 0: continue
                        cur_rate = rates.get(cur, 1.0)
                        debt_in_uzs = amt * cur_rate
                        
                        uzs_to_cover = min(remaining_uzs, debt_in_uzs)
                        debt_balances[cur] -= (uzs_to_cover / cur_rate)
                        remaining_uzs -= uzs_to_cover
                        if remaining_uzs <= 0.001: break
            
            # Natijani saqlash
            final_balances = {k: round(v, 2) for k, v in debt_balances.items() if round(v, 2) > 0}
            
            total_uzs = 0
            for k, v in final_balances.items():
                total_uzs += v * rates.get(k, 1.0)
                
            sup.debt_balances = final_balances
            sup.debt_balance = total_uzs
            flag_modified(sup, "debt_balances")
            updated_count += 1
            
        db.commit()
        print(f"Muvaffaqiyatli yakunlandi. {updated_count} ta ta'minotchi qarzi qayta hisoblandi.")
        
    except Exception as e:
        db.rollback()
        print("Xatolik yuz berdi:", e)
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    run_fix()
