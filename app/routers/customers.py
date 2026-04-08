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
        # Bo'sh string'ni None ga o'tkazish
        stripped = v.strip()
        if not stripped:
            return None
        clean = stripped.replace("+", "").replace(" ", "").replace("-", "")
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

    all_sales = db.query(Sale).filter(
        Sale.customer_id == customer_id,
        Sale.company_id == current_user.company_id
    ).all()
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

    sales = db.query(Sale).filter(
        Sale.customer_id == customer_id,
        Sale.company_id == current_user.company_id
    ).order_by(Sale.created_at.desc()).limit(10).all()
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


@router.post("/bulk-import")
def bulk_import_customers(
    rows: list[dict],
    allow_update: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Excel fayldan mijozlarni yuklash yoki yangilash."""
    FIELD_MAP = {
        "Ism":             ("name",             str),
        "Telefon":         ("phone",            str),
        "Qarz":            ("debt_balance",     Decimal),
        "Kredit limit":    ("debt_limit",       Decimal),
        "Sodiqlik ballari":("loyalty_points",   int),
        "Karta raqami":    ("card_number",      str),
        "Cashback":        ("cashback_percent", Decimal),
        "Bonus":           ("bonus_balance",    Decimal),
    }

    created = 0
    updated = 0
    errors: list = []

    dup_q_base = db.query(Customer).filter(Customer.company_id == current_user.company_id)

    for idx, row in enumerate(rows):
        row_num = row.get("__row_index", idx + 2)
        name = str(row.get("Ism") or "").strip()
        phone = str(row.get("Telefon") or "").strip()
        card = str(row.get("Karta raqami") or "").strip() or None

        if not name and not phone:
            errors.append({"row": row_num, "error": "Mijoz ismi yoki telefoni majburiy"})
            continue

        existing = None
        if phone:
            existing = dup_q_base.filter(Customer.phone == phone).first()
        if not existing and name:
            existing = dup_q_base.filter(Customer.name == name).first()
        if not existing and card:
            existing = dup_q_base.filter(Customer.card_number == card).first()

        if existing:
            if not allow_update:
                errors.append({
                    "row": row_num, "name": name or phone,
                    "error": f"'{name or phone}' allaqachon mavjud — o'tkazib yuborildi"
                })
                continue

            for row_key, (field, cast) in FIELD_MAP.items():
                raw = row.get(row_key)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    val = str(raw).strip()
                    if cast == Decimal:
                        val = Decimal(val)
                    elif cast == int:
                        val = int(val)
                    setattr(existing, field, val)
                except Exception:
                    errors.append({"row": row_num, "name": name, "error": f"'{row_key}' qiymati xato: {raw}"})
                    continue

            updated += 1
            continue

        if not name:
            errors.append({"row": row_num, "error": "Yangi mijoz uchun Ism majburiy"})
            continue

        kwargs = {"name": name, "company_id": current_user.company_id}
        for row_key, (field, cast) in FIELD_MAP.items():
            if field == "name": continue
            raw = row.get(row_key)
            if raw is not None and str(raw).strip() != "":
                try:
                    val = str(raw).strip()
                    if cast == Decimal:
                        val = Decimal(val)
                    elif cast == int:
                        val = int(val)
                    kwargs[field] = val
                except:
                    pass

        # check card/phone to avoid integrity errors
        check_card = kwargs.get("card_number")
        if check_card and dup_q_base.filter(Customer.card_number == check_card).first():
            kwargs.pop("card_number")
            
        check_phone = kwargs.get("phone")
        if check_phone and dup_q_base.filter(Customer.phone == check_phone).first():
            kwargs.pop("phone")

        cust = Customer(**kwargs)
        db.add(cust)
        db.flush()
        created += 1

    db.commit()
    return {"created": created, "updated": updated, "skipped": len(errors), "errors": errors}

@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(cust)
    db.commit()
