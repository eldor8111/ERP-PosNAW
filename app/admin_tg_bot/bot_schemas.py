from typing import Optional
from pydantic import BaseModel

class CompanyBotCreate(BaseModel):
    bot_token: str

class CompanyBotSettingsUpdate(BaseModel):
    notify_instant_sales: bool = True
    notify_instant_finance: bool = True
    notify_scheduled: bool = True
    scheduled_time: str = "20:00"
    notify_expired_products: bool = True
    expired_days_before: int = 7

class CompanyBotOut(BaseModel):
    id: int
    company_id: int
    bot_username: Optional[str] = None
    is_active: bool
    notify_instant_sales: Optional[bool] = True
    notify_instant_finance: Optional[bool] = True
    notify_scheduled: Optional[bool] = True
    scheduled_time: Optional[str] = "20:00"
    notify_expired_products: Optional[bool] = True
    expired_days_before: Optional[int] = 7

    class Config:
        from_attributes = True
