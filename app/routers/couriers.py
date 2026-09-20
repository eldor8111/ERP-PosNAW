"""
Couriers API: dostavchiklar (kuryerlar) boshqaruvi.
Kuryer CRM foydalanuvchisi emas — faqat kuryer boti / Mini App orqali
ishlaydi (3-bosqich). Bu router CRM uchun CRUD + statistika beradi.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, cast, String
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.dependencies import require_roles
from app.models.user import User, UserRole
from app.models.courier import Courier
from app.models.order import Order, OrderStatus

router = APIRouter(prefix="/couriers", tags=["couriers"])

MANAGE_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)


class CourierIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=3, max_length=32)
    transport: Optional[str] = Field(None, max_length=30)


class CourierUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    phone: Optional[str] = Field(None, min_length=3, max_length=32)
    transport: Optional[str] = Field(None, max_length=30)
    is_active: Optional[bool] = None


def _courier_out(c: Courier, stats: Optional[dict] = None) -> dict:
    out = {
        "id": c.id,
        "name": c.name,
        "phone": c.phone,
        "transport": c.transport,
        "is_active": bool(c.is_active),
        "tg_connected": bool(c.tg_chat_id),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
    if stats:
        out.update(stats)
    return out


@router.get("")
def list_couriers(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    q = db.query(Courier).filter(Courier.company_id == current_user.company_id)
    if not include_inactive:
        q = q.filter(Courier.is_active == True)  # noqa: E712
    couriers = q.order_by(Courier.name).all()

    # Statistika: faol (assigned/on_way) va bugun yetkazilgan buyurtma GURUHLARI soni
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    ids = [c.id for c in couriers]
    active_by_courier: dict = {}
    delivered_today_by_courier: dict = {}
    if ids:
        active_rows = db.query(
            Order.courier_id,
            func.count(func.distinct(func.coalesce(Order.order_group_id, cast(Order.id, String)))),
        ).filter(
            Order.courier_id.in_(ids),
            Order.status.in_([OrderStatus.assigned, OrderStatus.on_way]),
        ).group_by(Order.courier_id).all()
        active_by_courier = {r[0]: r[1] for r in active_rows}

        delivered_rows = db.query(
            Order.courier_id,
            func.count(func.distinct(Order.order_group_id)),
        ).filter(
            Order.courier_id.in_(ids),
            Order.status == OrderStatus.delivered,
            Order.delivered_at >= today_start,
        ).group_by(Order.courier_id).all()
        delivered_today_by_courier = {r[0]: r[1] for r in delivered_rows}

    return [
        _courier_out(c, {
            "active_orders": int(active_by_courier.get(c.id, 0) or 0),
            "delivered_today": int(delivered_today_by_courier.get(c.id, 0) or 0),
        })
        for c in couriers
    ]


@router.post("", status_code=201)
def create_courier(
    data: CourierIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    courier = Courier(
        company_id=current_user.company_id,
        name=data.name.strip(),
        phone=data.phone.strip(),
        transport=(data.transport or "").strip() or None,
        is_active=True,
    )
    db.add(courier)
    db.commit()
    db.refresh(courier)
    return _courier_out(courier)


@router.put("/{courier_id}")
def update_courier(
    courier_id: int,
    data: CourierUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    courier = db.query(Courier).filter(
        Courier.id == courier_id,
        Courier.company_id == current_user.company_id,
    ).first()
    if not courier:
        raise HTTPException(status_code=404, detail="Dostavchik topilmadi")

    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        if k in ("name", "phone", "transport") and isinstance(v, str):
            v = v.strip() or None
        setattr(courier, k, v)
    db.commit()
    db.refresh(courier)
    return _courier_out(courier)


@router.delete("/{courier_id}")
def deactivate_courier(
    courier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    """Yumshoq o'chirish — kuryer nofaol qilinadi (buyurtma tarixi saqlanadi)."""
    courier = db.query(Courier).filter(
        Courier.id == courier_id,
        Courier.company_id == current_user.company_id,
    ).first()
    if not courier:
        raise HTTPException(status_code=404, detail="Dostavchik topilmadi")
    courier.is_active = False
    db.commit()
    return {"message": "Dostavchik nofaol qilindi"}
