from pydantic import BaseModel


class SendSMSRequest(BaseModel):
    phone: str
    message: str
    sms_type: str = "manual"
