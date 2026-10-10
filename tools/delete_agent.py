import sys
from app.database import SessionLocal
from app.models.user import User, SmsVerification
from app.models.marketplace import MarketplaceAgentCategory, MarketplaceAgentTransaction
from app.models.mobile_device import MobileDevice

db = SessionLocal()
try:
    users = db.query(User).filter(
        User.phone.like('%7663107%') | User.phone.like('%7763107%')
    ).all()
    
    if not users:
        print("Bunday telefon raqamli foydalanuvchi topilmadi.")
    
    for u in users:
        print(f"O'chirilmoqda: ID={u.id}, Ism={u.name}, Tel={u.phone}, Rol={u.role}, Status={u.status}")
        db.query(MarketplaceAgentCategory).filter(MarketplaceAgentCategory.user_id == u.id).delete()
        db.query(MarketplaceAgentTransaction).filter(MarketplaceAgentTransaction.user_id == u.id).delete()
        db.query(MobileDevice).filter(MobileDevice.user_id == u.id).delete()
        db.delete(u)

    # SMS kodlarini ham tozalash
    db.query(SmsVerification).filter(
        SmsVerification.phone.like('%7663107%') | SmsVerification.phone.like('%7763107%')
    ).delete()

    db.commit()
    print(f"Tayyor! {len(users)} ta foydalanuvchi va SMS kodlar bazadan tozalandi.")
except Exception as e:
    db.rollback()
    print(f"Xatolik yuz berdi: {e}")
finally:
    db.close()
