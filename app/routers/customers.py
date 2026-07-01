"""
Customers API: CRM module for managing customers, debt and loyalty.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel, field_validator, model_validator  # type: ignore
from app.utils.translit import name_phone_search_filter  # type: ignore
from decimal import Decimal
from sqlalchemy.orm.attributes import flag_modified  # type: ignore

from app.database import get_db  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.customer_prices import CustomerPrice  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User, UserRole  # type: ignore

router = APIRouter(prefix="/customers", tags=["customers"])


class CustomerIn(BaseModel):
    name: str
    phone: Optional[str] = None
    debt_balance: Optional[Decimal] = Decimal("0")
    debt_currency: Optional[str] = "UZS"
    debt_balances: Optional[dict] = None
    debt_limit: Optional[Decimal] = Decimal("0")
    loyalty_points: Optional[int] = 0
    card_number: Optional[str] = None
    cashback_percent: Optional[Decimal] = Decimal("0")
    price_type: Optional[str] = "sale"  # sale, wholesale, cost
    
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
        stripped = v.strip()
        if not stripped:
            return None
        clean = stripped.replace("+", "").replace(" ", "").replace("-", "")
        if not clean.isdigit() or not (7 <= len(clean) <= 15):
            raise ValueError("Telefon raqam noto'g'ri (faqat raqamlar, 7-15 ta belgi)")
        return v


class CustomerOut(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    debt_balance: Decimal
    debt_currency: str = "UZS"
    debt_balances: Optional[dict] = {}
    debt_limit: Decimal
    loyalty_points: int
    card_number: Optional[str] = None
    cashback_percent: Decimal
    bonus_balance: Decimal = Decimal("0")
    total_spent: Decimal = Decimal("0")
    company_id: Optional[int] = None
    price_type: Optional[str] = "sale"
    discount_percent: Optional[Decimal] = Decimal("0")

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def normalize_debts(cls, data):
        is_dict = isinstance(data, dict)
        
        # Attribute yoki Dict qiymatini olish
        if is_dict:
            debt_currency = data.get("debt_currency") or "UZS"
            debt_balance = data.get("debt_balance") or 0
            debt_balances = data.get("debt_balances")
        else:
            debt_currency = getattr(data, "debt_currency", "UZS") or "UZS"
            debt_balance = getattr(data, "debt_balance", 0) or 0
            debt_balances = getattr(data, "debt_balances", None)
            
        currency = str(debt_currency).strip().upper() or "UZS"
        
        if debt_balances is None:
            balances = {}
        else:
            balances = dict(debt_balances)
            
        # Agar debt_balances bo'sh bo'lib, jami debt_balance musbat bo'lsa
        if not balances and float(debt_balance) > 0:
            balances[currency] = float(debt_balance)
            
        if is_dict:
            data["debt_balances"] = balances
            data["debt_currency"] = "UZS"
        else:
            # ORM obyekt bo'lsa, xavfsiz va tez ishlashi uchun barcha kerakli fieldlar bilan yangi dict qaytaramiz
            data_dict = {
                "id": getattr(data, "id", None),
                "name": getattr(data, "name", None),
                "phone": getattr(data, "phone", None),
                "debt_balance": getattr(data, "debt_balance", Decimal("0")),
                "debt_currency": "UZS",
                "debt_balances": balances,
                "debt_limit": getattr(data, "debt_limit", Decimal("0")),
                "loyalty_points": getattr(data, "loyalty_points", 0),
                "card_number": getattr(data, "card_number", None),
                "cashback_percent": getattr(data, "cashback_percent", Decimal("0")),
                "bonus_balance": getattr(data, "bonus_balance", Decimal("0")),
                "total_spent": getattr(data, "total_spent", Decimal("0")),
                "company_id": getattr(data, "company_id", None),
                "price_type": getattr(data, "price_type", "sale"),
                "discount_percent": getattr(data, "discount_percent", Decimal("0")),
            }
            return data_dict
            
        return data


class PaginatedCustomersOut(BaseModel):
    items: list[CustomerOut]
    total: int


def _calc_debt_in_uzs(balances: dict, db: Session) -> Decimal:
    """debt_balances dict va joriy kurslardan UZS ekvivalentini hisoblaydi."""
    from app.models.currency import Currency as CurrencyModel
    total = Decimal("0")
    for curr, amt in (balances or {}).items():
        if curr == "UZS":
            total += Decimal(str(amt))
        else:
            curr_obj = db.query(CurrencyModel).filter(CurrencyModel.code == curr).first()
            rate = Decimal(str(curr_obj.rate)) if curr_obj else Decimal("1")
            total += Decimal(str(amt)) * rate
    return total


class DebtUpdate(BaseModel):
    amount: Decimal
    reason: str
    currency: Optional[str] = "UZS"
    wallet_id: Optional[int] = None
    payment_type: Optional[str] = "cash"


class PointsAdjust(BaseModel):
    delta: int          # musbat = qo'shish, manfiy = ayirish
    reason: Optional[str] = None


@router.post("/recalc-debts")
def recalc_all_debts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Barcha mijozlarning debt_balance ni debt_balances + joriy kurs asosida qayta hisoblaydi.
    Bu endpoint faqat bir martalik fix uchun yoki kurs o'zgarganda chaqiriladi."""
    customers = db.query(Customer).filter(
        Customer.company_id == current_user.company_id
    ).all()
    updated = 0
    for cust in customers:
        balances = dict(cust.debt_balances or {})
        if not balances:
            continue
        new_balance = _calc_debt_in_uzs(balances, db)
        cust.debt_balance = new_balance
        updated += 1
    db.commit()
    return {"message": f"{updated} ta mijoz qarzi qayta hisoblandi", "updated": updated}


@router.get("", response_model=list[CustomerOut])
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
        q = q.filter(
            name_phone_search_filter(Customer.name, Customer.phone, search)
        )
    items = q.order_by(Customer.name).offset(skip).limit(limit).all()
    return items


@router.get("/paginated", response_model=PaginatedCustomersOut)
def list_customers_paginated(
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    sort_by: Optional[str] = Query(None), # debt_balance, name, id
    sort_order: Optional[str] = Query("asc"), # asc, desc
    min_debt: Optional[Decimal] = Query(None),
    max_debt: Optional[Decimal] = Query(None),
    exact_debt: Optional[Decimal] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Customer)
    q = q.filter(Customer.company_id == current_user.company_id)
    if search:
        q = q.filter(
            name_phone_search_filter(Customer.name, Customer.phone, search)
        )
    
    if exact_debt is not None:
        q = q.filter(Customer.debt_balance == exact_debt)
    else:
        if min_debt is not None:
            q = q.filter(Customer.debt_balance >= min_debt)
        if max_debt is not None:
            q = q.filter(Customer.debt_balance <= max_debt)
    
    total = q.count()

    # Sorting
    if sort_by:
        col = getattr(Customer, sort_by, None)
        if col:
            if sort_order == "desc":
                q = q.order_by(col.desc())
            else:
                q = q.order_by(col.asc())
        else:
            q = q.order_by(Customer.name)
    else:
        q = q.order_by(Customer.name)

    items = q.offset(skip).limit(limit).all()

    return {
        "items": items,
        "total": total
    }


@router.post("", status_code=201, response_model=CustomerOut)
def create_customer(data: CustomerIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.currency import Currency as CurrencyModel
    customer_data = data.model_dump()
    customer_data["company_id"] = current_user.company_id

    # debt_balances ni normalize qilish
    balances = customer_data.get("debt_balances") or {}
    if not balances and float(customer_data.get("debt_balance") or 0) > 0:
        currency = (customer_data.get("debt_currency") or "UZS").strip().upper() or "UZS"
        balances = {currency: float(customer_data["debt_balance"])}
    customer_data["debt_balances"] = balances

    # debt_balance ni debt_balances dan hisoblash (UZS ekvivalent)
    total_uzs = Decimal("0")
    for curr, amt in balances.items():
        if curr == "UZS":
            total_uzs += Decimal(str(amt))
        else:
            curr_obj = db.query(CurrencyModel).filter(CurrencyModel.code == curr).first()
            rate = Decimal(str(curr_obj.rate)) if curr_obj else Decimal("1")
            total_uzs += Decimal(str(amt)) * rate
    customer_data["debt_balance"] = total_uzs
    customer_data["debt_currency"] = "UZS"

    customer = Customer(**customer_data)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    return cust


@router.put("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, data: CustomerIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from app.models.currency import Currency as CurrencyModel
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    update_data = data.model_dump()

    # debt_balances ni normalize qilish
    balances = update_data.get("debt_balances") or {}
    if not balances and float(update_data.get("debt_balance") or 0) > 0:
        currency = (update_data.get("debt_currency") or "UZS").strip().upper() or "UZS"
        balances = {currency: float(update_data["debt_balance"])}
    update_data["debt_balances"] = balances

    # debt_balance ni debt_balances dan hisoblash (UZS ekvivalent)
    total_uzs = Decimal("0")
    for curr, amt in balances.items():
        if curr == "UZS":
            total_uzs += Decimal(str(amt))
        else:
            curr_obj = db.query(CurrencyModel).filter(CurrencyModel.code == curr).first()
            rate = Decimal(str(curr_obj.rate)) if curr_obj else Decimal("1")
            total_uzs += Decimal(str(amt)) * rate
    update_data["debt_balance"] = total_uzs
    update_data["debt_currency"] = "UZS"

    for key, val in update_data.items():
        setattr(cust, key, val)
    flag_modified(cust, "debt_balances")
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

    # debt_balances ni normalize qilish (eski debt_balance ni ham hisobga olish)
    balances = dict(cust.debt_balances or {})
    if not balances and float(cust.debt_balance or 0) > 0:
        currency = (cust.debt_currency or "UZS").strip().upper() or "UZS"
        balances[currency] = float(cust.debt_balance)

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
        "debt_currency": "UZS",
        "debt_balances": balances,
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
    from app.models.currency import Currency as CurrencyModel
    from app.models.moliya import Transaction, Wallet, KassaMovement
    from sqlalchemy.orm.attributes import flag_modified

    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    currency = data.currency or "UZS"

    # Ensure debt_balances is initialised before any reads
    if not cust.debt_balances:
        cust.debt_balances = {}

    # --- LEGACY MIGRATION ---
    # Eski akkountlarda debt_balances bo'sh bo'ladi, debt_balance eski field'da.
    # Agar debt_balances bo'sh bo'lsa, avval uni debt_balance dan to'ldiramiz.
    if not cust.debt_balances and float(cust.debt_balance or 0) > 0:
        legacy_currency = (cust.debt_currency or "UZS").strip().upper() or "UZS"
        cust.debt_balances = {legacy_currency: float(cust.debt_balance)}

    # Update the currency-specific balance in debt_balances JSON
    curr_val = Decimal(str(cust.debt_balances.get(currency, 0)))
    cust.debt_balances[currency] = float(max(Decimal("0"), curr_val - data.amount))
    flag_modified(cust, "debt_balances")

    # Update aggregate debt_balance (always in UZS)
    exchange_rate = Decimal("1")
    if currency != "UZS":
        curr_obj = db.query(CurrencyModel).filter(CurrencyModel.code == currency).first()
        if curr_obj:
            exchange_rate = Decimal(str(curr_obj.rate))

    amount_in_uzs = data.amount * exchange_rate
    cust.debt_balance = max(Decimal("0"), (cust.debt_balance or Decimal("0")) - amount_in_uzs)

    if data.wallet_id:
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            # Credit wallet with the raw amount in the payment currency
            wallet.balance = float(wallet.balance) + float(data.amount)
        tx = Transaction(
            company_id=current_user.company_id,
            branch_id=current_user.branch_id or 0,
            wallet_id=data.wallet_id,
            type="income",
            amount=data.amount,
            payment_type=data.payment_type,
            reference_type="customer_payment",
            reference_id=customer_id,
            description=data.reason,
        )
        db.add(tx)
        # KassaMovement — mijoz to'lovi
        db.add(KassaMovement(
            wallet_id=data.wallet_id,
            company_id=current_user.company_id,
            direction="in",
            payment_type=data.payment_type or "cash",
            amount=data.amount,
            reference_type="customer_payment",
            reference_id=customer_id,
            description=f"Mijoz to'lovi: {cust.name} — {data.reason}",
            created_by=current_user.id,
        ))

    db.commit()
    return {
        "message": "Qarzdorlik to'landi",
        "remaining_debt": float(cust.debt_balance),
        "debt_balances": cust.debt_balances,
    }




@router.get("/{customer_id}/cashback")
def get_customer_cashback(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POS uchun: mijozning keshbek va bonus balans ma'lumotlari (yengil endpoint)."""
    cust = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    return {
        "customer_id": cust.id,
        "name": cust.name,
        "bonus_balance": float(cust.bonus_balance or 0),
        "cashback_percent": float(cust.cashback_percent or 0),
        "loyalty_points": cust.loyalty_points or 0,
        "tier": cust.tier,
        "debt_balance": float(cust.debt_balance or 0),
        "debt_limit": float(cust.debt_limit or 0),
    }


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
    from app.models.sale import Sale
    q = db.query(Customer).filter(Customer.id == customer_id)
    q = q.filter(Customer.company_id == current_user.company_id)
    cust = q.first()
    if not cust:
        raise HTTPException(status_code=404, detail="Not found")
    db.query(Sale).filter(Sale.customer_id == customer_id).update({"customer_id": None})
    db.delete(cust)
    db.commit()


# ── Customer Prices ────────────────────────────────────────────────────────────

class CustomerPriceIn(BaseModel):
    product_id: int
    price: Decimal


@router.get("/{customer_id}/prices")
def list_customer_prices(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cust = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    return db.query(CustomerPrice).filter(
        CustomerPrice.customer_id == customer_id,
        CustomerPrice.company_id == current_user.company_id,
    ).all()


@router.post("/{customer_id}/prices", status_code=201)
def set_customer_price(
    customer_id: int,
    data: CustomerPriceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cust = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == current_user.company_id,
    ).first()
    if not cust:
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    existing = db.query(CustomerPrice).filter(
        CustomerPrice.customer_id == customer_id,
        CustomerPrice.product_id == data.product_id,
        CustomerPrice.company_id == current_user.company_id,
    ).first()
    if existing:
        existing.price = data.price
        db.commit()
        db.refresh(existing)
        return existing
    cp = CustomerPrice(
        company_id=current_user.company_id,
        customer_id=customer_id,
        product_id=data.product_id,
        price=data.price,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


@router.delete("/{customer_id}/prices/{product_id}", status_code=204)
def delete_customer_price(
    customer_id: int,
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cp = db.query(CustomerPrice).filter(
        CustomerPrice.customer_id == customer_id,
        CustomerPrice.product_id == product_id,
        CustomerPrice.company_id == current_user.company_id,
    ).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Narx topilmadi")
    db.delete(cp)
    db.commit()
