from pydantic import BaseModel

class CompanyBotCreate(BaseModel):
    bot_token: str

class CompanyBotSettingsUpdate(BaseModel):
    notify_instant_sales: bool
    notify_instant_finance: bool
    notify_scheduled: bool
    scheduled_time: str

class CompanyBotOut(BaseModel):
    id: int
    company_id: int
    bot_username: str | None
    is_active: bool
    notify_instant_sales: bool
    notify_instant_finance: bool
    notify_scheduled: bool
    scheduled_time: str

    class Config:
        from_attributes = True

