from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, model_validator  # type: ignore


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
            data["debt_currency"] = currency
        else:
            # Pydantic from_attributes works with a custom dict
            fields = [
                "id", "name", "inn", "phone", "email", "address", "payment_terms",
                "debt_balance", "debt_currency", "debt_balances", "is_active", "created_at",
                "bank_name", "bank_account", "bank_mfo", "contract_number", "contract_date",
                "rating", "notes"
            ]
            data_dict = {}
            for f in fields:
                if f == "debt_balances":
                    data_dict["debt_balances"] = balances
                elif f == "debt_currency":
                    data_dict["debt_currency"] = currency
                else:
                    data_dict[f] = getattr(data, f, None)
            return data_dict
            
        return data
