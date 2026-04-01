"""
Bu skript 933344602 foydalanuvchini bazadan to'liq o'chiradi.
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

from app.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        # Foydalanuvchini topish
        phones = ['933344602', '+998933344602', '998933344602', '0933344602']
        found = None
        for phone in phones:
            row = conn.execute(text("SELECT id, name, phone, role FROM users WHERE phone = :p"), {"p": phone}).fetchone()
            if row:
                found = row
                break
        
        if not found:
            print("TOPILMADI! Barcha foydalanuvchilar:")
            rows = conn.execute(text("SELECT id, name, phone, role FROM users LIMIT 20")).fetchall()
            for r in rows:
                print(f"   ID={r.id} | {r.name} | {r.phone} | {r.role}")
            return

        user_id = found.id
        print(f"TOPILDI: ID={user_id} | {found.name} | {found.phone} | {found.role}")
        
        confirm = input(f"\n'{found.name}' ({found.phone}) ni o'chirishni tasdiqlaysizmi? (ha/yo'q): ").strip().lower()
        if confirm not in ('ha', 'h', 'yes', 'y'):
            print("Bekor qilindi.")
            return
        
        # audit_logs ni o'chirish
        r = conn.execute(text("DELETE FROM audit_logs WHERE user_id = :uid"), {"uid": user_id})
        print(f"   audit_logs: {r.rowcount} ta yozuv o'chirildi")
        
        # Boshqa bog'liq jadvallar
        for tbl in ['shifts', 'purchase_orders', 'inventory_counts']:
            try:
                r2 = conn.execute(text(f"DELETE FROM {tbl} WHERE user_id = :uid"), {"uid": user_id})
                if r2.rowcount:
                    print(f"   {tbl}: {r2.rowcount} ta yozuv o'chirildi")
            except Exception:
                pass
        
        # Foydalanuvchini o'chirish
        conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        conn.commit()
        
        print(f"\nMUVAFFAQIYATLI: '{found.name}' ({found.phone}) o'chirildi!")
        print("\nKEYINGI QADAMLAR:")
        print("1. http://localhost:5173/register sahifasiga borib qayta ro'yxatdan o'ting")
        print("2. Ro'yxatdan o'tgandan so'ng: python set_superadmin.py ni bajaring")

if __name__ == "__main__":
    run()
