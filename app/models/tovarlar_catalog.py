from sqlalchemy import Column, Integer, String, Text, Index

from app.database import Base


class TovarlarCatalog(Base):
    __tablename__ = "tovarlar_catalog"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    mxik_code      = Column(String(30), nullable=False, index=True)
    mxik_name      = Column(Text, nullable=True)
    barcode        = Column(String(30), nullable=False, unique=True, index=True)
    unit_name      = Column(String(200), nullable=True)
    group_name     = Column(Text, nullable=True)
    attribute_name = Column(Text, nullable=True)
    lgota_id       = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_tovarlar_catalog_barcode", "barcode", unique=True),
        Index("ix_tovarlar_catalog_mxik_code", "mxik_code"),
    )
