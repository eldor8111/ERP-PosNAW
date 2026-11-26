"""Restoran rejimi API (R0): sozlamalar va boshlang'ich tuzilma (sexlar, zallar, stollar).

Hamma endpoint `require_restaurant` ostida: do'kon korxonasi chaqirsa 403.
Sexlar: restaurant_menu.py (R1.4); zal va stollar: restaurant_floor.py (R2).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.core.features import require_restaurant
from app.database import get_db
from app.models.company import Company
from app.models.restaurant import Hall, KitchenStation, RestaurantTable
from app.models.user import User, UserRole
from app.services.restaurant import normalize_restaurant_settings, restaurant_settings_of

router = APIRouter(prefix="/restaurant", tags=["Restoran"], dependencies=[Depends(require_restaurant)])


def _company(db: Session, user: User) -> Company:
    c = db.get(Company, user.company_id) if user.company_id else None
    if c is None:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    return c


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return restaurant_settings_of(_company(db, user))


@router.put("/settings")
def update_settings(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.super_admin, UserRole.admin, UserRole.director)),
):
    c = _company(db, user)
    merged = restaurant_settings_of(c)
    merged.update(normalize_restaurant_settings(payload))
    c.restaurant_settings = merged
    db.commit()
    return merged


@router.get("/layout")
def get_layout(
    branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Korxona sexlari va filial bo'yicha zallar va stollar (faqat ruxsat etilgan filiallar)."""
    scope = ctx.scope_ids()
    if branch_id is not None and scope is not None and branch_id not in scope:
        raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
    st_q = db.query(KitchenStation).filter(KitchenStation.company_id == user.company_id)
    hall_q = db.query(Hall).filter(Hall.company_id == user.company_id)
    if branch_id is not None:
        hall_q = hall_q.filter(Hall.branch_id == branch_id)
    elif scope is not None:
        hall_q = hall_q.filter(Hall.branch_id.in_(scope))
    stations = st_q.order_by(KitchenStation.sort_order, KitchenStation.id).all()
    halls = hall_q.order_by(Hall.branch_id, Hall.sort_order, Hall.id).all()
    tables = []
    if halls:
        tables = db.query(RestaurantTable).filter(
            RestaurantTable.company_id == user.company_id,
            RestaurantTable.hall_id.in_([h.id for h in halls]),
        ).order_by(RestaurantTable.hall_id, RestaurantTable.id).all()
    by_hall = {}
    for t in tables:
        by_hall.setdefault(t.hall_id, []).append({
            "id": t.id, "name": t.name, "seats": t.seats, "x": t.x, "y": t.y, "w": t.w, "h": t.h,
            "shape": t.shape, "is_active": t.is_active,
        })
    return {
        "stations": [{"id": s.id, "name": s.name, "kds_enabled": s.kds_enabled, "is_active": s.is_active,
                      "sort_order": s.sort_order} for s in stations],
        "halls": [{"id": h.id, "branch_id": h.branch_id, "name": h.name,
                   "service_pct": float(h.service_pct) if h.service_pct is not None else None,
                   "is_active": h.is_active, "tables": by_hall.get(h.id, [])} for h in halls],
    }
