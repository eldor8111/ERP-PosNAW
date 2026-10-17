"""Mijoz qatori bilan ishlash yordamchilari (T0.26).

QULF TARTIBI (butun loyihada bir xil bo'lishi shart, aks holda deadlock):
    mijoz  ->  ombor qoldig'i (StockLevel)  ->  hamyon (Wallet)
Ikki mijoz qulflanadigan joyda (masalan sotuv mijozini almashtirish) —
`id` o'sish tartibida qulflanadi.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.customer import Customer

ARCHIVED_DETAIL = "Mijoz arxivlangan — u bilan amal bajarib bo'lmaydi"


def lock_customer(
    db: Session,
    customer_id: int,
    company_id: Optional[int],
    *,
    allow_inactive: bool = False,
    required: bool = True,
) -> Optional[Customer]:
    """Mijoz qatorini `FOR UPDATE` bilan o'qiydi (sotuv, to'lov, tahrir bir-birining
    qarz/bonus/ball hisobini ustidan yozib yubormasligi uchun).

    - topilmasa: 404 (`required=False` bo'lsa None qaytaradi);
    - arxivlangan (`is_active=False`) bo'lsa: 400 (`allow_inactive=True` bo'lsa o'tadi —
      masalan eski sotuvni o'chirish/qaytarish arxivlangan mijozga ham ishlashi kerak).
    """
    cust = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == company_id,
    ).with_for_update().first()
    if not cust:
        if required:
            raise HTTPException(status_code=404, detail="Mijoz topilmadi")
        return None
    if not allow_inactive and cust.is_active is False:
        raise HTTPException(status_code=400, detail=ARCHIVED_DETAIL)
    return cust
