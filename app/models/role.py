from sqlalchemy import Column, Integer, String, Boolean, JSON, ForeignKey  # type: ignore
from sqlalchemy.orm import relationship  # type: ignore
from app.database import Base  # type: ignore

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)  # Null if it's a global system role
    permissions = Column(JSON, default={})
    is_system = Column(Boolean, default=False)  # True for super_admin, admin, manager etc., so they can't be deleted

    company = relationship("Company")
    users = relationship("User", back_populates="custom_role")
