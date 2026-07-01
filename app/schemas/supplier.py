from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel  # type: ignore


class SupplierCreate(BaseModel):
    name: str
    inn: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms: int = 30
    debt_balance: Optional[Decimal] = Decimal("0")  # Boshlang'ich qarz
    debt_currency: Optional[str] = "UZS"  # Qarz valyutasi: UZS, USD, RUB ...
    debt_balances: Optional[dict] = None
    # Bank
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_mfo: Optional[str] = None
    # Shartnoma
    contract_number: Optional[str] = None
    contract_date: Optional[datetime] = None
    # Reyting
    rating: Optional[float] = None
    notes: Optional[str] = None


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    inn: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[int] = None
    is_active: Optional[bool] = None
    # Bank
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_mfo: Optional[str] = None
    # Shartnoma
    contract_number: Optional[str] = None
    contract_date: Optional[datetime] = None
    # Reyting
    rating: Optional[float] = None
    notes: Optional[str] = None
    # Qarz balans (admin tomonidan to'g'ridan-to'g'ri o'zgartirish)
    debt_balance: Optional[Decimal] = None
    debt_currency: Optional[str] = None
    debt_balances: Optional[dict] = None


class SupplierOut(BaseModel):
    id: int
    name: str
    inn: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    address: Optional[str]
    payment_terms: int
    debt_balance: Decimal
    debt_currency: str = "UZS"
    debt_balances: Optional[dict] = {}
    is_active: bool
    created_at: datetime
    # Bank
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    bank_mfo: Optional[str] = None
    # Shartnoma
    contract_number: Optional[str] = None
    contract_date: Optional[datetime] = None
    # Reyting
    rating: Optional[float] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}
