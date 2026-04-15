from sqlalchemy import Column, Integer, String, Numeric, ForeignKey  # type: ignore
from app.database import Base  # type: ignore

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    phone = Column(String(20), unique=True, nullable=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    debt_balance = Column(Numeric(14, 2), default=0)
    debt_limit = Column(Numeric(14, 2), default=0)
    loyalty_points = Column(Integer, default=0)
    tg_chat_id = Column(String(50), unique=True, index=True, nullable=True)
    
    # Skidka (sotuvda avtomatik qo'llaniladi)
    discount_percent = Column(Numeric(5, 2), default=0)

    # Keshbek va Sodiqlik kartasi
    card_number = Column(String(20), unique=True, index=True, nullable=True)
    cashback_percent = Column(Numeric(5, 2), default=0)
    bonus_balance = Column(Numeric(14, 2), default=0)
    total_spent = Column(Numeric(14, 2), default=0)

    @property
    def tier(self):
        if self.loyalty_points >= 10000:
            return "Gold"
        elif self.loyalty_points >= 5000:
            return "Silver"
        elif self.loyalty_points >= 1000:
            return "Bronze"
        return "Standard"
