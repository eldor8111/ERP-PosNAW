"""D2.4 — Dorixona: quti, blister va dona bitta kartochkada (mahsulot birliklari).

`/api/pharmacy/products/{id}/units` — mahsulotning sotuv/kirim birliklari (ProductUnit): nomi, nisbati
(asosiy birlikda nechta), ixtiyoriy narxi va shtrix-kodi. Qoldiq doim asosiy birlikda saqlanadi.
Faqat dorixona moduli yoqilgan korxonada ishlaydi (oddiy do'konda 403); har bir korxona faqat o'z
mahsulotining birliklarini ko'radi va o'zgartiradi (boshqa korxona mahsuloti — 404).
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import get_current_user, require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.product import Product
from app.models.product_units import ProductUnit
from app.models.user import User, UserRole
from app.services.pharmacy import get_pharmacy_settings
from app.services.sale_stock import list_product_units, pack_ratio_of, unit_list_price

router = APIRouter(
    prefix="/pharmacy/products",
    tags=["Pharmacy units"],
    dependencies=[Depends(require_feature("pharmacy"))],
)

WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)
MAX_RATIO = Decimal("1000000")


class UnitIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    ratio: Decimal
    sale_price: Optional[Decimal] = None
    barcode: Optional[str] = Field(None, max_length=100)
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("Birlik nomi bo'sh bo'lmasligi kerak")
        return v

    @field_validator("ratio")
    @classmethod
    def _ratio(cls, v):
        if v is None or v <= 0:
            raise ValueError("Nisbat musbat bo'lishi kerak")
        if v > MAX_RATIO:
            raise ValueError("Nisbat juda katta")
        return v

    @field_validator("sale_price")
    @classmethod
    def _price(cls, v):
        if v is not None and v < 0:
            raise ValueError("Narx manfiy bo'lishi mumkin emas")
        return v

    @field_validator("barcode")
    @classmethod
    def _barcode(cls, v):
        v = (v or "").strip()
        return v or None


def _own_product(db: Session, product_id: int, company_id) -> Product:
    p = db.query(Product).filter(
        Product.id == product_id, Product.company_id == company_id, Product.is_deleted == False,  # noqa: E712
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return p


def _own_unit(db: Session, product_id: int, unit_id: int, company_id) -> ProductUnit:
    u = db.query(ProductUnit).filter(
        ProductUnit.id == unit_id, ProductUnit.product_id == product_id, ProductUnit.company_id == company_id,
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Birlik topilmadi")
    return u


def _check_unique(db: Session, company_id: int, product_id: int, data: UnitIn, exclude_id: Optional[int] = None) -> None:
    q = db.query(ProductUnit.id).filter(
        ProductUnit.product_id == product_id, func.lower(ProductUnit.name) == data.name.lower(),
    )
    if exclude_id:
        q = q.filter(ProductUnit.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=400, detail=f"'{data.name}' birligi bu mahsulotda allaqachon bor")
    if data.barcode:
        q = db.query(ProductUnit.id).filter(ProductUnit.company_id == company_id, ProductUnit.barcode == data.barcode)
        if exclude_id:
            q = q.filter(ProductUnit.id != exclude_id)
        if q.first():
            raise HTTPException(status_code=400, detail=f"Shtrix-kod {data.barcode} boshqa birlikda ishlatilgan")
        if db.query(Product.id).filter(
            Product.company_id == company_id, Product.barcode == data.barcode, Product.is_deleted == False,  # noqa: E712
        ).first():
            raise HTTPException(status_code=400, detail=f"Shtrix-kod {data.barcode} mahsulot shtrix-kodi sifatida ishlatilgan")


def _out(u: ProductUnit, units: list, product: Product, pack: Optional[Decimal], price_round) -> Dict[str, Any]:
    return {
        "id": u.id,
        "product_id": u.product_id,
        "name": u.name,
        "ratio": float(u.ratio),
        "sale_price": float(u.sale_price) if u.sale_price is not None else None,
        # sotuvda amal qiladigan narx: o'z narxi, quti narxidan hisoblangan yoki mahsulot narxi * nisbat
        "price": float(unit_list_price(u, units, product.sale_price, pack, price_round)),
        "barcode": u.barcode,
        "sort_order": u.sort_order,
        "is_pack": bool(pack is not None and Decimal(str(u.ratio)) == pack),
    }


def _list(db: Session, product: Product, company_id: int) -> List[Dict[str, Any]]:
    units = list_product_units(db, product.id, company_id)
    pack = pack_ratio_of(db, product.id, company_id, units)
    price_round = get_pharmacy_settings(db, company_id).get("price_round") or 0
    return [_out(u, units, product, pack, price_round) for u in units]


@router.get("/{product_id}/units")
def list_units(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Mahsulot birliklari (katta nisbatdan kichigiga). Kassir ham ko'ra oladi."""
    product = _own_product(db, product_id, current_user.company_id)
    return _list(db, product, current_user.company_id)


@router.post("/{product_id}/units", status_code=status.HTTP_201_CREATED)
def create_unit(
    product_id: int,
    data: UnitIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    product = _own_product(db, product_id, current_user.company_id)
    _check_unique(db, current_user.company_id, product.id, data)
    u = ProductUnit(
        product_id=product.id, company_id=current_user.company_id, name=data.name, ratio=data.ratio,
        sale_price=data.sale_price, barcode=data.barcode, sort_order=data.sort_order,
    )
    db.add(u)
    db.flush()
    log_action(db, action="UNIT_CREATE", entity_type="product_unit", entity_id=u.id, user_id=current_user.id,
               new_values={"product_id": product.id, "name": u.name, "ratio": str(u.ratio)})
    db.commit()
    return next(x for x in _list(db, product, current_user.company_id) if x["id"] == u.id)


@router.put("/{product_id}/units/{unit_id}")
def update_unit(
    product_id: int,
    unit_id: int,
    data: UnitIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
) -> Dict[str, Any]:
    product = _own_product(db, product_id, current_user.company_id)
    u = _own_unit(db, product.id, unit_id, current_user.company_id)
    _check_unique(db, current_user.company_id, product.id, data, exclude_id=u.id)
    old = {"name": u.name, "ratio": str(u.ratio), "sale_price": str(u.sale_price) if u.sale_price is not None else None}
    u.name, u.ratio, u.sale_price, u.barcode, u.sort_order = data.name, data.ratio, data.sale_price, data.barcode, data.sort_order
    db.flush()
    log_action(db, action="UNIT_UPDATE", entity_type="product_unit", entity_id=u.id, user_id=current_user.id,
               old_values=old,
               new_values={"name": u.name, "ratio": str(u.ratio), "sale_price": str(u.sale_price) if u.sale_price is not None else None})
    db.commit()
    return next(x for x in _list(db, product, current_user.company_id) if x["id"] == u.id)


@router.delete("/{product_id}/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unit(
    product_id: int,
    unit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
):
    """Birlikni o'chirish. O'tgan sotuvlardagi birlik nomi va nisbati o'zgarmaydi (sotuvda nusxa saqlangan)."""
    product = _own_product(db, product_id, current_user.company_id)
    u = _own_unit(db, product.id, unit_id, current_user.company_id)
    log_action(db, action="UNIT_DELETE", entity_type="product_unit", entity_id=u.id, user_id=current_user.id,
               old_values={"product_id": product.id, "name": u.name, "ratio": str(u.ratio)})
    db.delete(u)
    db.commit()
