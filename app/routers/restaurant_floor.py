"""Restoran zallari va stollari (R2.1, R2.2): zal va stol CRUD, zal sxemasini saqlash.

Hamma endpoint `require_restaurant` ostida. Filial doirasi: xodim faqat o'ziga ruxsat etilgan filial zallarini
ko'radi va tahrirlaydi. Stol va zal o'chirilmaydi, nofaol qilinadi (R3 cheklari ularga bog'lanadi).
Stol holatlari (band, hisob so'ralgan, bron) va stol amallari (ko'chirish, birlashtirish) R3 da cheklar bilan.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.features import require_restaurant
from app.database import get_db
from app.models.branch import Branch
from app.models.restaurant import Hall, RestaurantTable
from app.models.user import User, UserRole

router = APIRouter(prefix="/restaurant", tags=["Restoran zali"], dependencies=[Depends(require_restaurant)])

READ_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant,
              UserRole.warehouse, UserRole.cashier)
EDIT_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager)

GRID_MAX = 200          # sxema o'lchami (shartli katak)
SIZE_MAX = 20
SEATS_MAX = 50
SHAPES = ("rect", "round")
MAX_TABLES_PER_HALL = 300


class HallIn(BaseModel):
    branch_id: Optional[int] = None
    name: Optional[str] = None
    service_pct: Optional[float] = None
    clear_service_pct: Optional[bool] = None   # True — zal korxona xizmat haqini oladi (service_pct = NULL)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class TableIn(BaseModel):
    name: Optional[str] = None
    seats: Optional[int] = None
    shape: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    w: Optional[int] = None
    h: Optional[int] = None
    is_active: Optional[bool] = None


class LayoutItem(BaseModel):
    id: int
    x: int
    y: int
    w: Optional[int] = None
    h: Optional[int] = None
    shape: Optional[str] = None


class LayoutIn(BaseModel):
    tables: List[LayoutItem]


# ───────────────────────── yordamchilar ─────────────────────────

def _check_branch(db: Session, ctx: BranchContext, user: User, branch_id: int) -> Branch:
    b = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == user.company_id).first()
    if b is None:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    if ctx.allowed_branch_ids is not None and branch_id not in ctx.allowed_branch_ids:
        raise HTTPException(status_code=403, detail="Bu filialga ruxsat yo'q")
    return b


def _hall(db: Session, ctx: BranchContext, user: User, hall_id: int) -> Hall:
    h = db.query(Hall).filter(Hall.id == hall_id, Hall.company_id == user.company_id).first()
    if h is None:
        raise HTTPException(status_code=404, detail="Zal topilmadi")
    _check_branch(db, ctx, user, h.branch_id)
    return h


def _table(db: Session, ctx: BranchContext, user: User, table_id: int) -> RestaurantTable:
    t = db.query(RestaurantTable).filter(RestaurantTable.id == table_id,
                                         RestaurantTable.company_id == user.company_id).first()
    if t is None:
        raise HTTPException(status_code=404, detail="Stol topilmadi")
    _hall(db, ctx, user, t.hall_id)
    return t


def _name(v, what: str, max_len: int) -> str:
    v = (v or "").strip()
    if not v or len(v) > max_len:
        raise HTTPException(status_code=400, detail=f"{what} nomi 1-{max_len} belgi bo'lishi kerak")
    return v


def _int(v, what: str, lo: int, hi: int) -> int:
    if v is None or not lo <= int(v) <= hi:
        raise HTTPException(status_code=400, detail=f"{what}: {lo} dan {hi} gacha")
    return int(v)


def _shape(v) -> str:
    if v not in SHAPES:
        raise HTTPException(status_code=400, detail="Stol shakli: rect yoki round")
    return v


def _table_out(t: RestaurantTable) -> dict:
    return {"id": t.id, "hall_id": t.hall_id, "name": t.name, "seats": t.seats, "x": t.x, "y": t.y,
            "w": t.w, "h": t.h, "shape": t.shape, "is_active": t.is_active}


def _hall_out(h: Hall, tables: list) -> dict:
    return {"id": h.id, "branch_id": h.branch_id, "name": h.name,
            "service_pct": float(h.service_pct) if h.service_pct is not None else None,
            "sort_order": h.sort_order, "is_active": h.is_active, "tables": [_table_out(t) for t in tables]}


def _dup_table_name(db: Session, hall_id: int, name: str, exclude_id: Optional[int] = None) -> bool:
    q = db.query(RestaurantTable.id).filter(RestaurantTable.hall_id == hall_id, RestaurantTable.is_active == True,  # noqa: E712
                                            func.lower(RestaurantTable.name) == name.lower())
    if exclude_id is not None:
        q = q.filter(RestaurantTable.id != exclude_id)
    return q.first() is not None


# ───────────────────────── zallar ─────────────────────────

@router.get("/halls")
def list_halls(
    branch_id: Optional[int] = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*READ_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    q = db.query(Hall).filter(Hall.company_id == user.company_id)
    if branch_id is not None:
        _check_branch(db, ctx, user, branch_id)
        q = q.filter(Hall.branch_id == branch_id)
    else:
        scope = ctx.scope_ids()
        if scope is not None:
            q = q.filter(Hall.branch_id.in_(scope))
    if not include_inactive:
        q = q.filter(Hall.is_active == True)  # noqa: E712
    halls = q.order_by(Hall.branch_id, Hall.sort_order, Hall.id).all()
    by_hall = {}
    if halls:
        tq = db.query(RestaurantTable).filter(RestaurantTable.company_id == user.company_id,
                                              RestaurantTable.hall_id.in_([h.id for h in halls]))
        if not include_inactive:
            tq = tq.filter(RestaurantTable.is_active == True)  # noqa: E712
        for t in tq.order_by(RestaurantTable.id):
            by_hall.setdefault(t.hall_id, []).append(t)
    return [_hall_out(h, by_hall.get(h.id, [])) for h in halls]


def _service_pct(v):
    if v is None:
        return None
    if not 0 <= float(v) <= 50:
        raise HTTPException(status_code=400, detail="Xizmat haqi 0 dan 50 foizgacha")
    return round(float(v), 2)


@router.post("/halls", status_code=201)
def create_hall(payload: HallIn, db: Session = Depends(get_db), user: User = Depends(require_roles(*EDIT_ROLES)),
                ctx: BranchContext = Depends(get_branch_context)):
    if payload.branch_id is None:
        raise HTTPException(status_code=400, detail="Filial tanlanmagan")
    _check_branch(db, ctx, user, payload.branch_id)
    name = _name(payload.name, "Zal", 100)
    dup = db.query(Hall.id).filter(Hall.company_id == user.company_id, Hall.branch_id == payload.branch_id,
                                   Hall.is_active == True, func.lower(Hall.name) == name.lower()).first()  # noqa: E712
    if dup:
        raise HTTPException(status_code=409, detail="Bu filialda shunday nomli zal bor")
    last = db.query(func.max(Hall.sort_order)).filter(Hall.company_id == user.company_id,
                                                      Hall.branch_id == payload.branch_id).scalar()
    h = Hall(company_id=user.company_id, branch_id=payload.branch_id, name=name,
             service_pct=_service_pct(payload.service_pct),
             sort_order=payload.sort_order if payload.sort_order is not None else (last or 0) + 1)
    db.add(h)
    db.commit()
    db.refresh(h)
    return _hall_out(h, [])


@router.put("/halls/{hall_id}")
def update_hall(hall_id: int, payload: HallIn, db: Session = Depends(get_db),
                user: User = Depends(require_roles(*EDIT_ROLES)), ctx: BranchContext = Depends(get_branch_context)):
    h = _hall(db, ctx, user, hall_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = _name(data["name"], "Zal", 100)
        dup = db.query(Hall.id).filter(Hall.company_id == user.company_id, Hall.branch_id == h.branch_id,
                                       Hall.id != h.id, Hall.is_active == True,  # noqa: E712
                                       func.lower(Hall.name) == name.lower()).first()
        if dup:
            raise HTTPException(status_code=409, detail="Bu filialda shunday nomli zal bor")
        h.name = name
    if data.get("clear_service_pct"):
        h.service_pct = None
    elif "service_pct" in data:
        h.service_pct = _service_pct(data["service_pct"])
    if data.get("sort_order") is not None:
        h.sort_order = int(data["sort_order"])
    if data.get("is_active") is not None:
        h.is_active = bool(data["is_active"])
    db.commit()
    tables = db.query(RestaurantTable).filter(RestaurantTable.hall_id == h.id,
                                              RestaurantTable.is_active == True).order_by(RestaurantTable.id).all()  # noqa: E712
    return _hall_out(h, tables)


# ───────────────────────── stollar ─────────────────────────

def _free_spot(db: Session, hall_id: int) -> tuple:
    """Yangi stol uchun bo'sh joy: mavjud stollar ostidagi qatorga, chapdan."""
    rows = db.query(RestaurantTable.y, RestaurantTable.h).filter(RestaurantTable.hall_id == hall_id,
                                                                 RestaurantTable.is_active == True).all()  # noqa: E712
    bottom = max((y + h for y, h in rows), default=-1)
    return 0, min(bottom + 1, GRID_MAX - 2)


@router.post("/halls/{hall_id}/tables", status_code=201)
def create_table(hall_id: int, payload: TableIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(*EDIT_ROLES)), ctx: BranchContext = Depends(get_branch_context)):
    h = _hall(db, ctx, user, hall_id)
    count = db.query(func.count(RestaurantTable.id)).filter(RestaurantTable.hall_id == h.id,
                                                            RestaurantTable.is_active == True).scalar()  # noqa: E712
    if count >= MAX_TABLES_PER_HALL:
        raise HTTPException(status_code=400, detail=f"Bitta zalda {MAX_TABLES_PER_HALL} tadan ko'p stol bo'lmaydi")
    name = _name(payload.name if payload.name is not None else str(count + 1), "Stol", 50)
    if _dup_table_name(db, h.id, name):
        raise HTTPException(status_code=409, detail="Bu zalda shunday nomli stol bor")
    fx, fy = _free_spot(db, h.id)
    t = RestaurantTable(
        company_id=user.company_id, hall_id=h.id, name=name,
        seats=_int(payload.seats if payload.seats is not None else 4, "O'rinlar", 1, SEATS_MAX),
        shape=_shape(payload.shape or "rect"),
        x=_int(payload.x if payload.x is not None else fx, "X", 0, GRID_MAX),
        y=_int(payload.y if payload.y is not None else fy, "Y", 0, GRID_MAX),
        w=_int(payload.w if payload.w is not None else 2, "Eni", 1, SIZE_MAX),
        h=_int(payload.h if payload.h is not None else 2, "Bo'yi", 1, SIZE_MAX),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _table_out(t)


@router.put("/tables/{table_id}")
def update_table(table_id: int, payload: TableIn, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(*EDIT_ROLES)), ctx: BranchContext = Depends(get_branch_context)):
    t = _table(db, ctx, user, table_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = _name(data["name"], "Stol", 50)
        if _dup_table_name(db, t.hall_id, name, exclude_id=t.id):
            raise HTTPException(status_code=409, detail="Bu zalda shunday nomli stol bor")
        t.name = name
    if data.get("seats") is not None:
        t.seats = _int(data["seats"], "O'rinlar", 1, SEATS_MAX)
    if data.get("shape") is not None:
        t.shape = _shape(data["shape"])
    for k, lo, hi, what in (("x", 0, GRID_MAX, "X"), ("y", 0, GRID_MAX, "Y"),
                            ("w", 1, SIZE_MAX, "Eni"), ("h", 1, SIZE_MAX, "Bo'yi")):
        if data.get(k) is not None:
            setattr(t, k, _int(data[k], what, lo, hi))
    if data.get("is_active") is not None:
        if data["is_active"] and not t.is_active and _dup_table_name(db, t.hall_id, t.name, exclude_id=t.id):
            raise HTTPException(status_code=409, detail="Bu zalda shunday nomli faol stol bor")
        t.is_active = bool(data["is_active"])
    db.commit()
    db.refresh(t)
    return _table_out(t)


@router.delete("/tables/{table_id}")
def delete_table(table_id: int, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(*EDIT_ROLES)), ctx: BranchContext = Depends(get_branch_context)):
    """Stol nofaol qilinadi (tarixdagi cheklar uchun saqlanadi)."""
    t = _table(db, ctx, user, table_id)
    t.is_active = False
    db.commit()
    return {"ok": True}


@router.put("/halls/{hall_id}/layout")
def save_layout(hall_id: int, payload: LayoutIn, db: Session = Depends(get_db),
                user: User = Depends(require_roles(*EDIT_ROLES)), ctx: BranchContext = Depends(get_branch_context)):
    """Zal sxemasini bir yo'la saqlaydi (stollar joyi, o'lchami, shakli). Faqat shu zal stollari."""
    h = _hall(db, ctx, user, hall_id)
    if len(payload.tables) > MAX_TABLES_PER_HALL:
        raise HTTPException(status_code=400, detail="Stollar soni juda ko'p")
    ids = [it.id for it in payload.tables]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Stol takrorlangan")
    tables = {t.id: t for t in db.query(RestaurantTable).filter(RestaurantTable.hall_id == h.id,
                                                                RestaurantTable.company_id == user.company_id,
                                                                RestaurantTable.id.in_(ids or [0]))}
    missing = set(ids) - set(tables)
    if missing:
        raise HTTPException(status_code=400, detail="Stol bu zalga tegishli emas")
    for it in payload.tables:
        t = tables[it.id]
        t.x = _int(it.x, "X", 0, GRID_MAX)
        t.y = _int(it.y, "Y", 0, GRID_MAX)
        if it.w is not None:
            t.w = _int(it.w, "Eni", 1, SIZE_MAX)
        if it.h is not None:
            t.h = _int(it.h, "Bo'yi", 1, SIZE_MAX)
        if it.shape is not None:
            t.shape = _shape(it.shape)
    log_action(db=db, action="HALL_LAYOUT_SAVE", entity_type="hall", entity_id=h.id, user_id=user.id,
               new_values={"tables": len(ids)})
    db.commit()
    active = db.query(RestaurantTable).filter(RestaurantTable.hall_id == h.id,
                                              RestaurantTable.is_active == True).order_by(RestaurantTable.id).all()  # noqa: E712
    return _hall_out(h, active)
