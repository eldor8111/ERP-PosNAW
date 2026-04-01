from datetime import datetime, timezone
import random
import string

from sqlalchemy import Column, DateTime, Integer, String, Boolean
from sqlalchemy.orm import Session

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def generate_agent_code(db: Session) -> str:
    """J4602 ko'rinishida unikal kod yaratadi"""
    while True:
        letter = random.choice(string.ascii_uppercase)
        digits = ''.join(random.choices(string.digits, k=4))
        code = f"{letter}{digits}"
        exists = db.query(Agent).filter(Agent.code == code).first()
        if not exists:
            return code
