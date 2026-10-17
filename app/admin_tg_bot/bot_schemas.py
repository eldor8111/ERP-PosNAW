from typing import Optional
from pydantic import BaseModel

class CompanyBotCreate(BaseModel):
    bot_token: str

class CompanyBotSettingsUpdate(BaseModel):
    """Berilmagan maydonlar o'zgarmaydi (qisman yangilash, T3.16)."""
    notify_instant_sales: Optional[bool] = None
    notify_instant_finance: Optional[bool] = None
    notify_scheduled: Optional[bool] = None
    scheduled_time: Optional[str] = None
    notify_expired_products: Optional[bool] = None
    expired_days_before: Optional[int] = None
    notify_branch_managers: Optional[bool] = None
    report_by_branch: Optional[bool] = None

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
    notify_branch_managers: Optional[bool] = True
    report_by_branch: Optional[bool] = True

    class Config:
        from_attributes = True
