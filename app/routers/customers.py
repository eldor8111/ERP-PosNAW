"""
Customers API: CRM module for managing customers, debt and loyalty.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel, field_validator  # type: ignore
from decimal import Decimal

from app.database import get_db  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User, UserRole  # type: ignore

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerIn(BaseModel):
    name: str
    phone: Optional[str] = None
    debt_limit: Optional[Decimal] = Decimal("0")
    loyalty_points: Optional[int] = 0
    card_number: Optional[str] = None
    cashback_percent: Optional[Decimal] = Decimal("0")

    @field_validator("card_number")
    @classmethod
    def card_valid(cls, v):
        if v is not None and str(v).strip() == "":
            return None
        return v

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v):
        if v is None:
            return v
        clean = v.strip().replace("+", "").replace(" ", "").replace("-", "")
        if not clean.isdigit() or not (7 <= len(clean) <= 15):
            raise ValueError("Telefon raqam noto'g'ri (faqat raqamlar, 7-15 ta belgi)")
        return v


class DebtUpdate(BaseModel):
    amount: Decimal
    reason: str


class PointsAdjust(BaseModel):
    delta: int          # musbat = qo'shish, manfiy = ayirish
    reason: Optional[str] = None


@router.get("")
def list_customers(
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Customer)
    q = q.filter(Customer.company_id == current_user.company_id)
    if search:
        q = q.filter(Customer.name.ilike(f"%{search}%") | Customer.phone.ilike(f"%{search}%"))
    return q.order_by(Customer.name).offset(skip).limit(limit).all()


@router.post("", status_code=201)
def create_customer(data: CustomerIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    customer_data = data.model_dump()
    customer_data["company_id"] = current_user.company_id
    customer = Customer(**customer_data)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    return cust


@router.put("/{customer_id}")
def update_customer(customer_id: int, data: CustomerIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    for key, val in data.model_dump().items():
        setattr(cust, key, val)
    db.commit()
    db.refresh(cust)
    return cust


@router.get("/{customer_id}/stats")
def get_customer_stats(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    from app.models.sale import Sale, SaleStatus

    all_sales = db.query(Sale).filter(Sale.customer_id == customer_id).all()
    completed = [s for s in all_sales if s.status != SaleStatus.refunded and s.status != SaleStatus.cancelled]
    returned = [s for s in all_sales if s.status == SaleStatus.refunded]

    return {
        "id": cust.id,
        "name": cust.name,
        "phone": cust.phone,
        "debt_balance": float(cust.debt_balance),
        "debt_limit": float(cust.debt_limit),
        "loyalty_points": cust.loyalty_points or 0,
        "tier": cust.tier,
        "card_number": cust.card_number,
        "cashback_percent": float(cust.cashback_percent or 0),
        "bonus_balance": float(cust.bonus_balance or 0),
        "total_spent": float(cust.total_spent or 0),
        "total_sales_count": len(completed),
        "total_sales_amount": sum(float(s.total_amount) for s in completed),
        "total_paid_amount": sum(float(s.paid_amount) for s in completed),
        "total_returns_count": len(returned),
        "total_returns_amount": sum(float(s.total_amount) for s in returned),
    }


@router.get("/{customer_id}/history")
def get_customer_history(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    from app.models.sale import Sale  # type: ignore
    from app.models.moliya import Transaction  # type: ignore

    sales = db.query(Sale).filter(Sale.customer_id == customer_id).order_by(Sale.created_at.desc()).limit(10).all()
    payments = db.query(Transaction).filter(
        Transaction.reference_type == 'customer_payment',
        Transaction.reference_id == customer_id
    ).order_by(Transaction.created_at.desc()).all()

    history = []
    for s in sales:
        history.append({
            "type": "sale",
            "date": s.created_at.isoformat(),
            "amount": float(s.total_amount),
            "paid": float(s.paid_amount),
            "debt": float(s.total_amount - s.paid_amount),
        })
    for p in payments:
        history.append({
            "type": "payment",
            "date": p.created_at.isoformat(),
            "amount": float(p.amount),
        })

    return sorted(history, key=lambda x: x["date"], reverse=True)


@router.post("/{customer_id}/pay-debt")
def pay_debt(customer_id: int, data: DebtUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    if data.amount > cust.debt_balance:
        raise HTTPException(status_code=400, detail="To'lov qarzdorlikdan ko'p bo'lolmaydi")
    cust.debt_balance -= data.amount
    db.commit()
    return {"message": "Qarzdorlik to'landi", "remaining_debt": float(cust.debt_balance)}


@router.post("/{customer_id}/adjust-points")
def adjust_loyalty_points(
    customer_id: int,
    data: PointsAdjust,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Loyallik ballarini qo'shish yoki ayirish"""
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    new_points = (cust.loyalty_points or 0) + data.delta
    if new_points < 0:
        raise HTTPException(status_code=400, detail="Ballar manfiy bo'lolmaydi")
    cust.loyalty_points = new_points
    db.commit()
    return {
        "customer_id": customer_id,
        "delta": data.delta,
        "loyalty_points": cust.loyalty_points,
        "tier": cust.tier,
    }


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(cust)
    db.commit()
