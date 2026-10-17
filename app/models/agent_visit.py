from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class AgentVisit(Base):
    """Savdo agentining mijozga tashrifi (check-in → check-out) yoki rejalashtirilgan tashrif. Masofa
    serverda hisoblanadi; radiusdan tashqarida bo'lsa ham yoziladi, lekin
    within_radius=False — rahbar hisobotida "tasdiqlanmagan" bo'lib ko'rinadi."""
    __tablename__ = "agent_visits"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    agent_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    planned = Column(Boolean, nullable=False, default=False)   # bugungi rejada bormidi
    planned_date = Column(Date, nullable=True, index=True)      # rejalashtirilgan sana
    status = Column(String(20), nullable=True, default="planned", index=True) # planned | visited | cancelled
    check_in_at = Column(DateTime, nullable=True, default=lambda: datetime.now(timezone.utc), index=True)
    lat = Column(Numeric(10, 7), nullable=True)
    lng = Column(Numeric(10, 7), nullable=True)
    distance_m = Column(Integer, nullable=True)
    within_radius = Column(Boolean, nullable=True)             # None — mijoz nuqtasi noma'lum
    check_out_at = Column(DateTime, nullable=True)
    result = Column(String(20), nullable=True)                 # order | no_order | closed | payment
    note = Column(Text, nullable=True)
    photo_path = Column(String(300), nullable=True)

    customer = relationship("Customer", lazy="joined")
    agent = relationship("User", foreign_keys=[agent_id], lazy="joined")
