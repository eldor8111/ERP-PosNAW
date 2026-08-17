from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.database import Base


class Attribute(Base):
    __tablename__ = "attributes"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False) # e.g. "Rang", "Razmer", "Hajm"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    values = relationship("AttributeValue", back_populates="attribute", cascade="all, delete-orphan")


class AttributeValue(Base):
    __tablename__ = "attribute_values"

    id = Column(Integer, primary_key=True, index=True)
    attribute_id = Column(Integer, ForeignKey("attributes.id"), nullable=False, index=True)
    value = Column(String(100), nullable=False) # e.g. "Qizil", "42", "250ml"
    
    attribute = relationship("Attribute", back_populates="values")
    variants = relationship("VariantAttributeValue", back_populates="attribute_value", cascade="all, delete-orphan")


class VariantAttributeValue(Base):
    __tablename__ = "variant_attribute_values"

    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id"), nullable=False, index=True)
    attribute_value_id = Column(Integer, ForeignKey("attribute_values.id"), nullable=False, index=True)

    variant = relationship("ProductVariant", back_populates="attribute_values")
    attribute_value = relationship("AttributeValue", back_populates="variants")
