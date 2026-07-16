from pydantic import BaseModel


class CompanyBotCreate(BaseModel):
    bot_token: str


class CompanyBotOut(BaseModel):
    id: int
    company_id: int
    bot_username: str | None
    is_active: bool

    class Config:
        from_attributes = True