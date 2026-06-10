from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class HistoryEntry(BaseModel):
    id: int
    updated_at: datetime
    updated_value: str


class CurrencyRateResponse(BaseModel):
    id: int
    currency_id: int
    created_at: datetime
    currency: str
    updated_history: list[HistoryEntry] = []

    class Config:
        from_attributes = True
