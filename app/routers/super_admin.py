"""
Super Admin Panel API — faqat super_admin roli uchun.
Korxonalar (company) → Filiallar (branch) → Tafsilot
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from pydantic import BaseModel  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.warehouse import Warehouse  # type: ignore
from app.models.sale import Sale  # type: ignore

router = APIRouter(prefix="/super-admin", tags=["Super Admin"])


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Faqat Super Admin uchun")
    return current_user


# ── Overview ─────────────────────────────────────────────

@router.get("/overview")
def get_overview(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    companies_count = db.query(func.count(Company.id)).filter(Company.is_active == True).scalar() or 0
    branches_count = db.query(func.count(Branch.id)).filter(Branch.is_active == True).scalar() or 0
    users_count = db.query(func.count(User.id)).scalar() or 0
    warehouses_count = db.query(func.count(Warehouse.id)).filter(Warehouse.is_active == True).scalar() or 0
    sales_count = db.query(func.count(Sale.id)).scalar() or 0
    total_revenue = float(db.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 0)
    role_stats = db.query(User.role, func.count(User.id)).group_by(User.role).all()
    return {
        "companies": companies_count,
        "branches": branches_count,
        "users": users_count,
        "warehouses": warehouses_count,
        "sales": sales_count,
        "total_revenue": total_revenue,
        "users_by_role": {r.value: c for r, c in role_stats},
    }


# ── Companies ─────────────────────────────────────────────

@router.get("/companies")
def list_companies(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Barcha korxonalar — har birida filiallar va xodimlar soni"""
    companies = db.query(Company).order_by(Company.id).all()
    result = []
    for c in companies:
        branches_count = db.query(func.count(Branch.id)).filter(Branch.company_id == c.id).scalar() or 0
        # branches lari orqali userlar
        branch_ids = [b.id for b in db.query(Branch.id).filter(Branch.company_id == c.id).all()]
        users_count = 0
        if branch_ids:
            users_count = db.query(func.count(User.id)).filter(User.branch_id.in_(branch_ids)).scalar() or 0
        result.append({
            "id": c.id,
            "name": c.name,
            "address": c.address,
            "phone": c.phone,
            "email": c.email,
            "is_active": c.is_active,
            "created_at": str(c.created_at),
            "branches_count": branches_count,
            "users_count": users_count,
        })
    return result


@router.get("/companies/{company_id}")
def get_company_detail(company_id: int, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Bitta korxona + uning filiallari ro'yxati"""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")

    branches = db.query(Branch).filter(Branch.company_id == company_id).order_by(Branch.id).all()
    branches_data = []
    for b in branches:
        users_count = db.query(func.count(User.id)).filter(User.branch_id == b.id).scalar() or 0
        warehouses_count = db.query(func.count(Warehouse.id)).filter(Warehouse.branch_id == b.id, Warehouse.is_active == True).scalar() or 0
        branches_data.append({
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "phone": b.phone,
            "is_active": b.is_active,
            "users_count": users_count,
            "warehouses_count": warehouses_count,
        })

    total_users = sum(b["users_count"] for b in branches_data)
    total_warehouses = sum(b["warehouses_count"] for b in branches_data)

    return {
        "id": company.id,
        "name": company.name,
        "address": company.address,
        "phone": company.phone,
        "email": company.email,
        "is_active": company.is_active,
        "created_at": str(company.created_at),
        "stats": {
            "branches": len(branches_data),
            "users": total_users,
            "warehouses": total_warehouses,
        },
        "branches": branches_data,
    }


# ── Branches ─────────────────────────────────────────────

@router.get("/branches")
def list_all_branches(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Barcha filiallar (company bilan birgalikda)"""
    branches = db.query(Branch).order_by(Branch.id).all()
    result = []
    for b in branches:
        users_count = db.query(func.count(User.id)).filter(User.branch_id == b.id).scalar() or 0
        warehouses_count = db.query(func.count(Warehouse.id)).filter(Warehouse.branch_id == b.id).scalar() or 0
        result.append({
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "phone": b.phone,
            "is_active": b.is_active,
            "company_id": b.company_id,
            "company_name": b.company.name if b.company else None,
            "users_count": users_count,
            "warehouses_count": warehouses_count,
        })
    return result


@router.get("/branches/{branch_id}")
def get_branch_detail(branch_id: int, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Bitta filial: xodimlar va omborlar"""
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")

    users = db.query(User).filter(User.branch_id == branch_id).order_by(User.id).all()
    users_data = [
        {"id": u.id, "name": u.name, "phone": u.phone, "role": u.role.value, "status": u.status.value, "created_at": str(u.created_at)}
        for u in users
    ]

    warehouses = db.query(Warehouse).filter(Warehouse.branch_id == branch_id, Warehouse.is_active == True).all()
    warehouses_data = [{"id": w.id, "name": w.name, "address": w.address} for w in warehouses]

    return {
        "id": branch.id,
        "name": branch.name,
        "address": branch.address,
        "phone": branch.phone,
        "is_active": branch.is_active,
        "company_id": branch.company_id,
        "company_name": branch.company.name if branch.company else None,
        "stats": {"users": len(users_data), "warehouses": len(warehouses_data)},
        "users": users_data,
        "warehouses": warehouses_data,
    }


# ── Users ─────────────────────────────────────────────────

@router.get("/users")
def list_all_users(
    role: Optional[str] = None,
    branch_id: Optional[int] = None,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if branch_id:
        q = q.filter(User.branch_id == branch_id)
    if company_id:
        branch_ids = [b.id for b in db.query(Branch.id).filter(Branch.company_id == company_id).all()]
        if branch_ids:
            q = q.filter(User.branch_id.in_(branch_ids))
    users = q.order_by(User.id).all()
    return [
        {
            "id": u.id, "name": u.name, "phone": u.phone, "email": u.email,
            "role": u.role.value, "status": u.status.value,
            "branch_id": u.branch_id,
            "branch_name": u.branch.name if u.branch else None,
            "created_at": str(u.created_at),
        }
        for u in users
    ]


@router.patch("/users/{user_id}/role")
def change_user_role(user_id: int, role: str, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi")
    try:
        user.role = UserRole(role)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Noto'g'ri rol: {role}")
    db.commit()
    return {"message": f"{user.name} roli {role} ga o'zgartirildi"}


# ── Balans to'ldirish ─────────────────────────────────────

class TopUpRequest(BaseModel):
    org_code: str
    amount: float


@router.post("/top-up")
def top_up_balance(data: TopUpRequest, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Miqdor 0 dan katta bo'lishi kerak")
    company = db.query(Company).filter(Company.org_code == data.org_code.strip().upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail="Tashkilot topilmadi")
    company.balance = float(company.balance or 0) + data.amount
    db.commit()
    return {
        "company_name": company.name,
        "org_code": company.org_code,
        "added": data.amount,
        "new_balance": float(company.balance),
    }
