"""
Super Admin Panel API — faqat super_admin roli uchun.
Korxonalar (company) → Filiallar (branch) → Tafsilot
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from pydantic import BaseModel  # type: ignore
from fastapi.responses import JSONResponse  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore
from sqlalchemy.orm import Session, joinedload  # type: ignore
from sqlalchemy import func, or_  # type: ignore

from app.database import get_db  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.company import Company  # type: ignore
from app.models.branch import Branch  # type: ignore
from app.models.user_company import UserCompany  # type: ignore
from app.models.warehouse import Warehouse  # type: ignore
from app.models.sale import Sale  # type: ignore
from app.models.platform_settings import PlatformSettings  # type: ignore
from app.core.audit import log_action  # type: ignore
from app.schemas.branch import BranchCreate, BranchUpdate  # type: ignore
from app.schemas.warehouse import WarehouseCreate, WarehouseUpdate  # type: ignore
from app.utils.tariff_check import check_branch_limit, get_company_limits  # type: ignore

router = APIRouter(prefix="/super-admin", tags=["Super Admin"])


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=403, detail="Faqat Super Admin uchun")
    return current_user


# ── Overview ─────────────────────────────────────────────

@router.get("/overview")
def get_overview(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    from datetime import datetime, timezone
    from app.models.billing import BalanceLog

    companies_count   = db.query(func.count(Company.id)).filter(Company.is_active == True).scalar() or 0
    branches_count    = db.query(func.count(Branch.id)).filter(Branch.is_active == True).scalar() or 0
    users_count       = db.query(func.count(User.id)).scalar() or 0
    warehouses_count  = db.query(func.count(Warehouse.id)).filter(Warehouse.is_active == True).scalar() or 0
    sales_count       = db.query(func.count(Sale.id)).scalar() or 0
    total_revenue     = float(db.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar() or 0)
    role_stats        = db.query(User.role, func.count(User.id)).group_by(User.role).all()

    # Bugungi tarif sotuvlari
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_logs  = (
        db.query(BalanceLog)
        .filter(
            BalanceLog.log_type == "subscription",
            BalanceLog.created_at >= today_start,
            BalanceLog.amount < 0,          # chiqim = tarif to'lovi
        )
        .all()
    )
    today_subscriptions = len(today_logs)
    today_sub_revenue   = float(sum(abs(lg.amount) for lg in today_logs))

    return {
        "companies": companies_count,
        "branches": branches_count,
        "users": users_count,
        "warehouses": warehouses_count,
        "sales": sales_count,
        "total_revenue": total_revenue,
        "users_by_role": {r.value: c for r, c in role_stats},
        "today_subscriptions": today_subscriptions,
        "today_sub_revenue": today_sub_revenue,
    }


# ── Companies ─────────────────────────────────────────────

@router.get("/companies")
def list_companies(
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Barcha korxonalar — har birida filiallar va xodimlar soni"""
    branch_counts = (
        db.query(Branch.company_id, func.count(Branch.id).label("cnt"))
        .group_by(Branch.company_id)
        .subquery()
    )
    # T3.2: xodimlar korxona bo'yicha (filialsizlar va faqat user_companies orqali a'zolar bilan)
    members = (
        db.query(User.company_id.label("cid"), User.id.label("uid"))
        .filter(User.company_id.isnot(None))
        .union(
            db.query(UserCompany.company_id.label("cid"), UserCompany.user_id.label("uid"))
            .filter(UserCompany.is_active == True)  # noqa: E712
        )
        .subquery()
    )
    user_counts = (
        db.query(members.c.cid.label("company_id"), func.count().label("cnt"))
        .group_by(members.c.cid)
        .subquery()
    )
    q = (
        db.query(
            Company,
            func.coalesce(branch_counts.c.cnt, 0).label("branches_count"),
            func.coalesce(user_counts.c.cnt, 0).label("users_count"),
        )
        .outerjoin(branch_counts, Company.id == branch_counts.c.company_id)
        .outerjoin(user_counts, Company.id == user_counts.c.company_id)
    )
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(
            or_(Company.name.ilike(like), Company.org_code.ilike(like))
        )
    rows = q.order_by(Company.id).all()
    result = []
    for c, branches_count, users_count in rows:
        result.append({
            "id": c.id,
            "name": c.name,
            "code": c.org_code,
            "org_code": c.org_code,
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

    user_sub = (
        db.query(User.branch_id, func.count(User.id).label("cnt"))
        .group_by(User.branch_id)
        .subquery()
    )
    wh_sub = (
        db.query(Warehouse.branch_id, func.count(Warehouse.id).label("cnt"))
        .filter(Warehouse.is_active == True)
        .group_by(Warehouse.branch_id)
        .subquery()
    )
    rows = (
        db.query(
            Branch,
            func.coalesce(user_sub.c.cnt, 0).label("users_count"),
            func.coalesce(wh_sub.c.cnt, 0).label("warehouses_count"),
        )
        .outerjoin(user_sub, Branch.id == user_sub.c.branch_id)
        .outerjoin(wh_sub, Branch.id == wh_sub.c.branch_id)
        .filter(Branch.company_id == company_id)
        .order_by(Branch.id)
        .all()
    )
    branches_data = []
    for b, users_count, warehouses_count in rows:
        branches_data.append({
            "id": b.id,
            "name": b.name,
            "address": b.address,
            "phone": b.phone,
            "is_active": b.is_active,
            "users_count": users_count,
            "warehouses_count": warehouses_count,
        })

    # T3.2: korxona bo'yicha hisob — filialsiz xodim/omborlar ham kiradi
    members = _company_member_map(db, company_id)
    total_users = len(members)
    users_no_branch = sum(1 for bid in members.values() if bid is None)
    wh_cond = or_(
        Warehouse.company_id == company_id,
        Warehouse.branch_id.in_(db.query(Branch.id).filter(Branch.company_id == company_id)),
    )
    total_warehouses = (
        db.query(func.count(Warehouse.id)).filter(wh_cond, Warehouse.is_active == True).scalar() or 0  # noqa: E712
    )
    warehouses_no_branch = (
        db.query(func.count(Warehouse.id))
        .filter(Warehouse.company_id == company_id, Warehouse.branch_id.is_(None), Warehouse.is_active == True)  # noqa: E712
        .scalar() or 0
    )
    branches_active = sum(1 for b in branches_data if b["is_active"])
    limits_info = get_company_limits(db, company)
    unassigned_wh = (
        db.query(Warehouse)
        .filter(Warehouse.company_id == company_id, Warehouse.branch_id.is_(None), Warehouse.is_active == True)  # noqa: E712
        .order_by(Warehouse.id)
        .all()
    )

    from datetime import datetime, timezone as tz
    from app.models.billing import CompanyPackage
    now = datetime.now(tz.utc)
    sub_ends = company.subscription_ends_at
    if sub_ends and sub_ends.tzinfo is None:
        sub_ends = sub_ends.replace(tzinfo=tz.utc)
    is_active_sub = sub_ends is not None and sub_ends > now
    days_left = max(0, (sub_ends - now).days) if is_active_sub else 0

    # Kompaniya paketlari
    cp_rows = db.query(CompanyPackage).filter(CompanyPackage.company_id == company_id).all()
    company_packages_data = []
    for cp in cp_rows:
        cp_ends = cp.ends_at
        if cp_ends and cp_ends.tzinfo is None:
            cp_ends = cp_ends.replace(tzinfo=tz.utc)
        company_packages_data.append({
            "id": cp.id,
            "package_code": cp.package_code,
            "starts_at": cp.starts_at.isoformat() if cp.starts_at else None,
            "ends_at": cp_ends.isoformat() if cp_ends else None,
            "is_active": bool(cp.is_active),
            "is_trial": bool(cp.is_trial),
        })

    return {
        "id": company.id,
        "name": company.name,
        "address": company.address,
        "phone": company.phone,
        "email": company.email,
        "region": company.region,
        "district": company.district,
        "is_active": company.is_active,
        "marketplace_agents_enabled": company.marketplace_agents_enabled,
        "created_at": str(company.created_at),
        "balance": float(company.balance or 0),
        "tariff_id": company.tariff_id,
        "tariff_name": company.tariff.name if company.tariff else None,
        "subscription_ends_at": sub_ends.isoformat() if sub_ends else None,
        "is_trial": bool(company.is_trial),
        "subscription_active": is_active_sub,
        "days_left": days_left,
        "stats": {
            "branches": len(branches_data),          # eski kalit = jami (orqaga moslik)
            "users": total_users,
            "warehouses": total_warehouses,
            "branches_total": len(branches_data),
            "branches_active": branches_active,
            "branches_inactive": len(branches_data) - branches_active,
            "users_no_branch": users_no_branch,
            "warehouses_no_branch": warehouses_no_branch,
        },
        "limits": limits_info["limits"],
        "usage": limits_info["usage"],
        "branches": branches_data,
        "unassigned_warehouses": [
            {"id": w.id, "name": w.name, "type": w.type.value if w.type else None} for w in unassigned_wh
        ],
        "company_packages": company_packages_data,
    }


def _company_member_map(db: Session, company_id: int) -> dict:
    """Korxona xodimlari: {user_id: filial_id|None}. `users.company_id == id` yoki faol `user_companies`
    a'zoligi (users.py dagi uc_exists mantig'i); filial: asosiy korxonada users.branch_id, qo'shimchada
    user_companies.branch_id."""
    result = {uid: bid for uid, bid in db.query(User.id, User.branch_id).filter(User.company_id == company_id)}
    for uid, bid in db.query(UserCompany.user_id, UserCompany.branch_id).filter(
        UserCompany.company_id == company_id, UserCompany.is_active == True,  # noqa: E712
    ):
        result.setdefault(uid, bid)
    return result


@router.get("/companies/{company_id}/users")
def list_company_users(
    company_id: int,
    branch_id: Optional[int] = None,
    no_branch: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """T3.2: korxonaning barcha xodimlari (filialsizlar bilan). `branch_id` yoki `no_branch=true` bilan filtr."""
    if not db.query(Company.id).filter(Company.id == company_id).first():
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    members = _company_member_map(db, company_id)
    if no_branch:
        members = {uid: bid for uid, bid in members.items() if bid is None}
    elif branch_id is not None:
        members = {uid: bid for uid, bid in members.items() if bid == branch_id}
    if not members:
        return []
    users = db.query(User).filter(User.id.in_(list(members))).order_by(User.id).all()
    used_branch_ids = {b for b in members.values() if b is not None}
    branch_names = (
        {bid: name for bid, name in db.query(Branch.id, Branch.name).filter(Branch.id.in_(used_branch_ids))}
        if used_branch_ids else {}
    )
    return [
        {
            "id": u.id, "name": u.name, "phone": u.phone,
            "role": u.role.value if u.role else None,
            "status": u.status.value if u.status else None,
            "branch_id": members[u.id],
            "branch_name": branch_names.get(members[u.id]),
        }
        for u in users
    ]


# ── Branches ─────────────────────────────────────────────

@router.get("/branches")
def list_all_branches(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    """Barcha filiallar (company bilan birgalikda)"""
    user_sub = (
        db.query(User.branch_id, func.count(User.id).label("cnt"))
        .group_by(User.branch_id)
        .subquery()
    )
    wh_sub = (
        db.query(Warehouse.branch_id, func.count(Warehouse.id).label("cnt"))
        .filter(Warehouse.is_active == True)
        .group_by(Warehouse.branch_id)
        .subquery()
    )
    rows = (
        db.query(
            Branch,
            func.coalesce(user_sub.c.cnt, 0).label("users_count"),
            func.coalesce(wh_sub.c.cnt, 0).label("warehouses_count"),
        )
        .outerjoin(user_sub, Branch.id == user_sub.c.branch_id)
        .outerjoin(wh_sub, Branch.id == wh_sub.c.branch_id)
        .options(joinedload(Branch.company))
        .order_by(Branch.id)
        .all()
    )
    result = []
    for b, users_count, warehouses_count in rows:
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

    # T3.2: himoya — faqat shu filial korxonasining xodimlari
    users = db.query(User).filter(
        User.branch_id == branch_id, User.company_id == branch.company_id,
    ).order_by(User.id).all()
    users_data = [
        {"id": u.id, "name": u.name, "phone": u.phone, "role": u.role.value if u.role else None, "status": u.status.value if u.status else None, "created_at": str(u.created_at)}
        for u in users
    ]

    warehouses = db.query(Warehouse).filter(Warehouse.branch_id == branch_id, Warehouse.is_active == True).all()
    warehouses_data = [
        {"id": w.id, "name": w.name, "type": w.type.value if w.type else None,
         "is_default": bool(w.is_default)}
        for w in warehouses
    ]

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


# ── Filial va ombor yozuvlari (T3.2) ─────────────────────
# Umumiy /branches va /warehouses endpointlari current_user.company_id bilan cheklangan (super admin
# uchun NULL), shuning uchun super admin uchun company_id URL dan olinadigan alohida endpointlar.

BRANCH_FOREIGN = "Filial shu korxonaga tegishli emas"
DUPLICATE_BRANCH_NAME = "Bu nomli faol filial allaqachon mavjud"


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    return company


def _ensure_branch_name_free(db: Session, company_id: int, name: str, exclude_id: Optional[int] = None) -> None:
    q = db.query(Branch.id).filter(
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
        func.lower(func.trim(Branch.name)) == (name or "").strip().lower(),
    )
    if exclude_id is not None:
        q = q.filter(Branch.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail=DUPLICATE_BRANCH_NAME)


def _commit_branch(db: Session) -> None:
    """commit(); faol filial nomi unikalligi buzilsa (poyga) 409."""
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if "uq_branches_company_name_active" in str(e.orig):
            raise HTTPException(status_code=409, detail=DUPLICATE_BRANCH_NAME)
        raise


def _branch_row(db: Session, branch: Branch) -> dict:
    wh_count = db.query(func.count(Warehouse.id)).filter(
        Warehouse.branch_id == branch.id, Warehouse.is_active == True,  # noqa: E712
    ).scalar() or 0
    return {
        "id": branch.id, "name": branch.name, "address": branch.address, "phone": branch.phone,
        "is_active": branch.is_active, "company_id": branch.company_id,
        "is_main": bool(branch.is_main), "warehouses_count": int(wh_count),
    }


def _wh_row(wh: Warehouse) -> dict:
    return {
        "id": wh.id, "name": wh.name, "type": wh.type.value if wh.type else None,
        "branch_id": wh.branch_id, "company_id": wh.company_id,
        "is_active": wh.is_active, "is_default": bool(wh.is_default),
    }


def _company_branch_or_400(db: Session, branch_id: int, company_id: int, *, require_active: bool = True) -> Branch:
    """Ombor `branch_id` si shu korxonaga tegishli (va faol) bo'lishi shart."""
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == company_id).first()
    if not branch:
        raise HTTPException(status_code=400, detail=BRANCH_FOREIGN)
    if require_active and not branch.is_active:
        raise HTTPException(status_code=400, detail="Filial faol emas")
    return branch


def _is_default_candidate(wh: Warehouse) -> bool:
    from app.services.branch_provisioning import DEFAULT_CANDIDATE_TYPES
    return wh.type in DEFAULT_CANDIDATE_TYPES and wh.is_active is not False


def _branch_has_default(db: Session, branch_id: int, exclude_id: Optional[int] = None) -> bool:
    q = db.query(Warehouse.id).filter(
        Warehouse.branch_id == branch_id,
        Warehouse.is_default == True,  # noqa: E712
        Warehouse.is_active == True,   # noqa: E712
    )
    if exclude_id is not None:
        q = q.filter(Warehouse.id != exclude_id)
    return q.first() is not None


@router.post("/companies/{company_id}/branches")
def create_company_branch(
    company_id: int,
    data: BranchCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """Super admin: korxonaga filial qo'shadi (company_id URL dan; tarif limitidan ozod)."""
    from app.services.branch_provisioning import provision_branch

    _get_company_or_404(db, company_id)
    check_branch_limit(db, company_id, admin)   # super_admin uchun cheklov yo'q
    _ensure_branch_name_free(db, company_id, data.name)
    branch = Branch(name=data.name, address=data.address, phone=data.phone, company_id=company_id)
    if not db.query(Branch.id).filter(Branch.company_id == company_id).first():
        branch.is_main = True
    db.add(branch)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "uq_branches_company_name_active" in str(e.orig):
            raise HTTPException(status_code=409, detail=DUPLICATE_BRANCH_NAME)
        raise
    wh, wallet = provision_branch(
        db, branch,
        create_warehouse=data.create_warehouse, create_wallet=data.create_wallet,
        warehouse_name=data.warehouse_name, wallet_name=data.wallet_name,
    )
    log_action(
        db, "CREATE", "branch", branch.id, user_id=admin.id,
        new_values={"name": branch.name, "address": branch.address, "phone": branch.phone,
                    "company_id": company_id, "by": "super_admin",
                    "warehouse_id": wh.id if wh else None, "wallet_id": wallet.id if wallet else None},
        company_id=company_id, branch_id=branch.id,
    )
    _commit_branch(db)
    db.refresh(branch)
    out = _branch_row(db, branch)
    out.update(warehouse_id=wh.id if wh else None, wallet_id=wallet.id if wallet else None)
    return out


@router.patch("/branches/{branch_id}")
def update_branch_super(
    branch_id: int,
    data: BranchUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """Super admin: istalgan korxona filialini tahrirlaydi (nom, manzil, telefon, faol/nofaol).
    `company_id` yuborilsa e'tiborsiz qoldiriladi."""
    from app.services.branch_helpers import BranchCloseBlocked, archive_branch, reopen_branch

    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items()
              if k in ("name", "address", "phone", "is_active")}
    if "name" in fields:
        if fields["name"] is None or not str(fields["name"]).strip():
            raise HTTPException(status_code=400, detail="Filial nomi bo'sh bo'lmasligi kerak")
        fields["name"] = fields["name"].strip()
    want_active = fields.pop("is_active", None)

    # Faol -> nofaol = arxivlash (ochiq smena/qoldiq/balans bo'lsa 409); nofaol -> faol = qayta ochish
    new_active = branch.is_active if want_active is None else want_active
    if new_active and ("name" in fields or (want_active is True and not branch.is_active)):
        _ensure_branch_name_free(db, branch.company_id, fields.get("name", branch.name), exclude_id=branch.id)
    extra = {}
    if want_active is False and branch.is_active:
        try:
            archive_branch(db, branch, admin, None, None)
        except BranchCloseBlocked as e:
            return JSONResponse(status_code=409, content={"detail": e.detail, "blockers": e.blockers})
    elif want_active is True and not branch.is_active:
        extra = reopen_branch(db, branch, admin)

    old_values = {k: getattr(branch, k) for k in fields}
    for field, value in fields.items():
        setattr(branch, field, value)
    if fields:
        log_action(
            db, "UPDATE", "branch", branch.id, user_id=admin.id,
            old_values=old_values, new_values={**fields, "by": "super_admin"},
            company_id=branch.company_id, branch_id=branch.id,
        )
    _commit_branch(db)
    db.refresh(branch)
    out = _branch_row(db, branch)
    out.update(extra)
    return out


@router.post("/companies/{company_id}/warehouses")
def create_company_warehouse(
    company_id: int,
    data: WarehouseCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """Super admin: korxonaga ombor qo'shadi. `branch_id` shu korxonaga tegishli bo'lishi shart (aks holda 400)."""
    from app.services.branch_provisioning import set_default_warehouse

    _get_company_or_404(db, company_id)
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Ombor nomi bo'sh bo'lmasligi kerak")
    if data.branch_id is not None:
        _company_branch_or_400(db, data.branch_id, company_id)
    wh = Warehouse(name=name, type=data.type, branch_id=data.branch_id, company_id=company_id)
    db.add(wh)
    db.flush()
    if wh.branch_id is not None:
        if data.is_default:
            set_default_warehouse(db, wh)
        elif _is_default_candidate(wh) and not _branch_has_default(db, wh.branch_id, exclude_id=wh.id):
            set_default_warehouse(db, wh)
    log_action(
        db, "CREATE", "warehouse", wh.id, user_id=admin.id,
        new_values={"name": wh.name, "branch_id": wh.branch_id, "is_default": bool(wh.is_default),
                    "company_id": company_id, "by": "super_admin"},
        company_id=company_id, branch_id=wh.branch_id,
    )
    db.commit()
    db.refresh(wh)
    return _wh_row(wh)


@router.patch("/warehouses/{wh_id}")
def update_warehouse_super(
    wh_id: int,
    data: WarehouseUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """Super admin: istalgan korxona omborini tahrirlaydi (nom, tur, filial, faol/nofaol, asosiy)."""
    from app.routers.warehouses import _assert_warehouse_closable
    from app.services.branch_provisioning import reassign_default_warehouse, set_default_warehouse

    wh = db.query(Warehouse).filter(Warehouse.id == wh_id).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    company_id = wh.company_id
    if company_id is None and wh.branch_id is not None:
        company_id = db.query(Branch.company_id).filter(Branch.id == wh.branch_id).scalar()

    old_values = {"name": wh.name, "type": wh.type.value if wh.type else None, "branch_id": wh.branch_id,
                  "is_active": wh.is_active, "is_default": bool(wh.is_default)}
    old_branch_id = wh.branch_id
    was_default = bool(wh.is_default)
    want_default = None
    if data.is_active is False and wh.is_active is not False:
        _assert_warehouse_closable(db, wh)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "is_default":
            want_default = value
            continue
        if value is None and field != "branch_id":
            continue
        if field == "name":
            value = value.strip()
            if not value:
                raise HTTPException(status_code=400, detail="Ombor nomi bo'sh bo'lmasligi kerak")
        if field == "branch_id" and value is not None:
            if company_id is None:
                raise HTTPException(status_code=400, detail=BRANCH_FOREIGN)
            _company_branch_or_400(db, value, company_id, require_active=value != wh.branch_id)
        setattr(wh, field, value)
    if wh.company_id is None and company_id is not None:
        wh.company_id = company_id

    branch_changed = wh.branch_id != old_branch_id
    if want_default is False and was_default and wh.is_active and not branch_changed and wh.branch_id is not None:
        raise HTTPException(status_code=400, detail="Filialda kamida bitta asosiy ombor bo'lishi kerak")
    if was_default and (branch_changed or wh.is_active is False):
        wh.is_default = False
        db.flush()
        reassign_default_warehouse(db, old_branch_id, exclude_id=wh.id)
    if want_default is True:
        if wh.branch_id is None:
            raise HTTPException(status_code=400, detail="Asosiy ombor filialga bog'langan bo'lishi kerak")
        if wh.is_active is False:
            raise HTTPException(status_code=400, detail="Nofaol omborni asosiy qilib bo'lmaydi")
        set_default_warehouse(db, wh)
    elif branch_changed and wh.branch_id is not None and _is_default_candidate(wh) \
            and not _branch_has_default(db, wh.branch_id, exclude_id=wh.id):
        set_default_warehouse(db, wh)
    log_action(
        db, "WAREHOUSE_UPDATE", "warehouse", wh.id, user_id=admin.id,
        old_values=old_values,
        new_values={"name": wh.name, "type": wh.type.value if wh.type else None, "branch_id": wh.branch_id,
                    "is_active": wh.is_active, "is_default": bool(wh.is_default), "by": "super_admin"},
        company_id=company_id, branch_id=wh.branch_id,
    )
    db.commit()
    db.refresh(wh)
    return _wh_row(wh)


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
        # Filialsiz/yangi korxona uchun ham filtr ishlashi shart: users.company_id yoki user_companies a'zoligi
        if not db.query(Company.id).filter(Company.id == company_id).first():
            raise HTTPException(status_code=404, detail="Korxona topilmadi")
        member_ids = db.query(UserCompany.user_id).filter(UserCompany.company_id == company_id)
        q = q.filter(or_(User.company_id == company_id, User.id.in_(member_ids)))
    users = q.order_by(User.id).all()
    return [
        {
            "id": u.id, "name": u.name, "phone": u.phone, "email": u.email,
            "role": u.role.value if u.role else None, "status": u.status.value if u.status else None,
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
def top_up_balance(data: TopUpRequest, db: Session = Depends(get_db), admin: User = Depends(require_super_admin)):
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Miqdor 0 dan katta bo'lishi kerak")
    company = db.query(Company).filter(Company.org_code == data.org_code.strip().upper()).first()
    if not company:
        raise HTTPException(status_code=404, detail="Tashkilot topilmadi")
    
    from datetime import datetime, timezone
    from app.models.billing import BalanceLog
    
    now = datetime.now(timezone.utc)
    company.balance = float(company.balance or 0) + data.amount
    
    log = BalanceLog(
        company_id=company.id,
        amount=data.amount,
        log_type="top_up",
        note=f"Balans to'ldirildi (Super Admin): +{data.amount:,.0f} so'm",
        created_by_id=admin.id,
        created_at=now,
    )
    db.add(log)
    db.commit()
    
    return {
        "company_name": company.name,
        "org_code": company.org_code,
        "added": data.amount,
        "new_balance": float(company.balance),
    }


# ── Platform Sozlamalari ──────────────────────────────────

SETTINGS_LABELS = {
    "card_number": "To'lov karta raqami",
    "card_owner":  "Karta egasining ismi",
    "tg_username": "Telegram username (@siz)",
    "phone":       "Telefon (ko'rsatish uchun)",
    "phone_raw":   "Telefon (tel: link uchun, raqamlar)",
}


@router.get("/platform-settings")
def get_platform_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Barcha platform sozlamalarini qaytaradi"""
    rows = db.query(PlatformSettings).all()
    existing = {r.key: r.value for r in rows}
    result = []
    for key, label in SETTINGS_LABELS.items():
        result.append({
            "key": key,
            "label": label,
            "value": existing.get(key, ""),
        })
    return result


class SettingsUpdate(BaseModel):
    values: dict  # { "card_number": "8600 ...", "tg_username": "eldor", ... }


@router.put("/platform-settings")
def update_platform_settings(
    data: SettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Platform sozlamalarini yangilash (karta, telegram, telefon)"""
    for key, value in data.values.items():
        if key not in SETTINGS_LABELS:
            continue
        existing = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()
        if existing:
            existing.value = str(value).strip()
        else:
            db.add(PlatformSettings(
                key=key,
                value=str(value).strip(),
                label=SETTINGS_LABELS.get(key, key),
            ))
    db.commit()
    return {"ok": True, "message": "Sozlamalar saqlandi"}


# ── Update / Delete Companies ─────────────────────────────────────────────

class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    org_code: Optional[str] = None
    region: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    marketplace_agents_enabled: Optional[bool] = None

@router.put("/companies/{company_id}")
def update_company_super(
    company_id: int,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin)
):
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    
    import sqlalchemy.exc
    try:
        if payload.name is not None: c.name = str(payload.name)
        if payload.org_code is not None: c.org_code = str(payload.org_code).strip() or None
        if payload.region is not None: c.region = str(payload.region).strip() or None
        if payload.district is not None: c.district = str(payload.district).strip() or None
        if payload.address is not None: c.address = str(payload.address).strip() or None
        if payload.phone is not None: c.phone = str(payload.phone).strip() or None
        if payload.email is not None: c.email = str(payload.email).strip() or None
        if payload.is_active is not None: c.is_active = payload.is_active
        if payload.marketplace_agents_enabled is not None: c.marketplace_agents_enabled = payload.marketplace_agents_enabled
        
        db.commit()
        return {"ok": True, "message": "Korxona ma'lumotlari yangilandi"}
    except sqlalchemy.exc.IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Bu ma'lumotlar (masalan: Kod) allaqachon boshqa korxonaga biriktirilgan.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Xatolik: {str(e)}")

@router.get("/companies/{company_id}/delete-preview")
def delete_company_preview(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin)
):
    """Korxona o'chirilsa nima o'chishini sanaydi (hech narsa o'zgarmaydi)."""
    from app.services.company_purge import preview_company_purge_ex, PurgeError
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    name, code = c.name, c.org_code
    try:
        res = preview_company_purge_ex(db, company_id)
    except PurgeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    counts, moved = res["counts"], res["moved"]
    # transactions_unattributed — transactions ning bir qismi (ma'lumot uchun), umumiy songa qo'shilmaydi
    total = sum(v for k, v in counts.items() if k != "transactions_unattributed")
    return {"id": company_id, "name": name, "org_code": code,
            "counts": counts, "total": total, "moved": moved}


@router.delete("/companies/{company_id}")
def delete_company_super(
    company_id: int,
    confirm: str = "",
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin)
):
    """Korxonani barcha ma'lumotlari bilan butunlay o'chirishni FONDA boshlaydi (confirm = korxona kodi yoki nomi).
    Javob darhol qaytadi: {job_id}; holat — GET /super-admin/purge-jobs/{job_id}."""
    from app.database import SessionLocal
    from app.services.company_purge import start_purge_job
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Korxona topilmadi")
    expected = {x.strip().lower() for x in (c.org_code, c.name) if x and x.strip()}
    if confirm.strip().lower() not in expected:
        raise HTTPException(status_code=400, detail="Tasdiqlash uchun korxona kodi yoki nomini aniq yozing")
    name = c.name
    db.close()   # fon vazifasi o'z sessiyasini ochadi; bu ulanish pulga qaytsin
    job = start_purge_job(company_id, name, SessionLocal, admin.id)
    return {"ok": True, "job_id": job["id"], "status": job["status"], "step": job.get("step")}


@router.get("/purge-jobs/{job_id}")
def get_purge_job(job_id: str, _: User = Depends(require_super_admin)):
    """Korxonani o'chirish vazifasining holati: running | done | error."""
    from app.services.company_purge import read_job
    job = read_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Vazifa topilmadi")
    return job


# ── Bildirish Nomalar (Announcements) ────────────────────────────────────────

from datetime import datetime, timezone as _tz
from app.models.announcement import Announcement, SurveyQuestion, SurveyAnswer
from typing import List, Dict, Any
import json


class SurveyQuestionCreate(BaseModel):
    text: str
    question_type: str  # 'text', 'single_choice', 'multiple_choice'
    options: Optional[List[str]] = None


class AnnouncementCreate(BaseModel):
    title: str
    message: str
    company_id: Optional[int] = None   # NULL = barcha korxonalar
    expires_at: Optional[str] = None   # ISO format string yoki None
    questions: Optional[List[SurveyQuestionCreate]] = None


class AnnouncementUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    is_active: Optional[bool] = None
    expires_at: Optional[str] = None


def _ann_dict(a: Announcement, company_name: Optional[str] = None) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "company_id": a.company_id,
        "company_name": company_name,
        "is_active": a.is_active,
        "has_survey": a.has_survey,
        "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/announcements")
def create_announcement(
    data: AnnouncementCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_super_admin),
):
    """Yangi bildirish noma yaratish"""
    expires = None
    if data.expires_at:
        try:
            expires = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="expires_at formati noto'g'ri")

    has_survey = bool(data.questions and len(data.questions) > 0)

    ann = Announcement(
        title=data.title.strip(),
        message=data.message.strip(),
        company_id=data.company_id,
        expires_at=expires,
        is_active=True,
        has_survey=has_survey,
        created_by=admin.id,
        created_at=datetime.now(_tz.utc),
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)

    if has_survey and data.questions:
        for q in data.questions:
            sq = SurveyQuestion(
                announcement_id=ann.id,
                text=q.text.strip(),
                question_type=q.question_type,
                options=json.dumps(q.options) if q.options else None
            )
            db.add(sq)
        db.commit()

    company_name = None
    if ann.company_id:
        c = db.query(Company).filter(Company.id == ann.company_id).first()
        company_name = c.name if c else None

    return _ann_dict(ann, company_name)


@router.get("/announcements")
def list_announcements(
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Barcha bildirish nomalar (super admin uchun)"""
    rows = db.query(Announcement).order_by(Announcement.id.desc()).all()
    result = []
    for a in rows:
        company_name = None
        if a.company_id:
            c = db.query(Company).filter(Company.id == a.company_id).first()
            company_name = c.name if c else None
        
        adict = _ann_dict(a, company_name)
        # Savollar sonini qo'shamiz
        if a.has_survey:
            questions_count = db.query(SurveyQuestion).filter(SurveyQuestion.announcement_id == a.id).count()
            answers_count = db.query(SurveyAnswer.company_id).join(SurveyQuestion).filter(SurveyQuestion.announcement_id == a.id).distinct().count()
            adict["questions_count"] = questions_count
            adict["answers_count"] = answers_count
            
        result.append(adict)
    return result


@router.patch("/announcements/{ann_id}")
def update_announcement(
    ann_id: int,
    data: AnnouncementUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Bildirish nomani tahrirlash / o'chirish"""
    ann = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Bildirish noma topilmadi")

    if data.title is not None:
        ann.title = data.title.strip()
    if data.message is not None:
        ann.message = data.message.strip()
    if data.is_active is not None:
        ann.is_active = data.is_active
    if data.expires_at is not None:
        try:
            ann.expires_at = datetime.fromisoformat(data.expires_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="expires_at formati noto'g'ri")

    db.commit()
    db.refresh(ann)
    return _ann_dict(ann)


@router.delete("/announcements/{ann_id}")
def delete_announcement(
    ann_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Bildirish nomani o'chirish"""
    ann = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not ann:
        raise HTTPException(status_code=404, detail="Bildirish noma topilmadi")
    db.delete(ann)
    db.commit()
    return {"ok": True}


# ── Foydalanuvchi uchun: aktiv bildirish nomalar ──────────────────────────────

@router.get("/announcements/active", tags=["Announcements"])
def get_active_announcements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Joriy foydalanuvchi korxonasiga tegishli aktiv xabarlarni qaytaradi"""
    now = datetime.now(_tz.utc)
    company_id = current_user.company_id

    q = db.query(Announcement).filter(
        Announcement.is_active == True,
        or_(
            Announcement.expires_at == None,
            Announcement.expires_at > now,
        ),
        or_(
            Announcement.company_id == None,          # Barcha korxonalarga
            Announcement.company_id == company_id,    # Faqat shu korxonaga
        ),
    ).order_by(Announcement.id.desc())

    announcements = q.all()
    result = []
    
    for a in announcements:
        adict = _ann_dict(a)
        adict["has_answered"] = False
        adict["questions"] = []
        
        if a.has_survey:
            # Check if this company already answered
            answered = db.query(SurveyAnswer).join(SurveyQuestion).filter(
                SurveyQuestion.announcement_id == a.id,
                SurveyAnswer.company_id == company_id
            ).first()
            
            if answered:
                adict["has_answered"] = True
            else:
                questions = db.query(SurveyQuestion).filter(SurveyQuestion.announcement_id == a.id).all()
                adict["questions"] = [
                    {
                        "id": q.id,
                        "text": q.text,
                        "question_type": q.question_type,
                        "options": json.loads(q.options) if q.options else None
                    }
                    for q in questions
                ]
                
        result.append(adict)

    return result


class SurveySubmit(BaseModel):
    answers: Dict[int, Any]  # question_id: answer_data

@router.post("/announcements/active/{ann_id}/submit-survey", tags=["Announcements"])
def submit_survey(
    ann_id: int,
    data: SurveySubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ann = db.query(Announcement).filter(Announcement.id == ann_id, Announcement.is_active == True).first()
    if not ann or not ann.has_survey:
        raise HTTPException(status_code=404, detail="So'rovnoma topilmadi yoki faol emas")
        
    company_id = current_user.company_id
    
    # Check if already answered
    answered = db.query(SurveyAnswer).join(SurveyQuestion).filter(
        SurveyQuestion.announcement_id == ann_id,
        SurveyAnswer.company_id == company_id
    ).first()
    if answered:
        raise HTTPException(status_code=400, detail="Siz allaqachon ushbu so'rovnomani to'ldirgansiz")

    questions = db.query(SurveyQuestion).filter(SurveyQuestion.announcement_id == ann_id).all()
    valid_q_ids = {q.id for q in questions}
    
    for q_id_str, answer_data in data.answers.items():
        q_id = int(q_id_str)
        if q_id not in valid_q_ids:
            continue
            
        ans = SurveyAnswer(
            question_id=q_id,
            company_id=company_id,
            user_id=current_user.id,
            answer_data=json.dumps(answer_data) if not isinstance(answer_data, str) else answer_data
        )
        db.add(ans)
        
    db.commit()
    return {"ok": True, "message": "Javobingiz qabul qilindi. Rahmat!"}


@router.get("/announcements/{ann_id}/survey-results", tags=["Super Admin"])
def get_survey_results(
    ann_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    ann = db.query(Announcement).filter(Announcement.id == ann_id).first()
    if not ann or not ann.has_survey:
        raise HTTPException(status_code=404, detail="So'rovnoma topilmadi")
        
    questions = db.query(SurveyQuestion).filter(SurveyQuestion.announcement_id == ann_id).all()
    results = []
    
    for q in questions:
        answers = db.query(SurveyAnswer, Company.name.label("company_name"), User.name.label("user_name"))\
            .join(Company, SurveyAnswer.company_id == Company.id)\
            .join(User, SurveyAnswer.user_id == User.id)\
            .filter(SurveyAnswer.question_id == q.id).all()
            
        ans_list = []
        for ans, comp_name, user_name in answers:
            ans_list.append({
                "company_name": comp_name,
                "user_name": user_name,
                "answer": ans.answer_data,
                "date": ans.created_at.isoformat() if ans.created_at else None
            })
            
        results.append({
            "question_id": q.id,
            "text": q.text,
            "type": q.question_type,
            "options": json.loads(q.options) if q.options else None,
            "answers": ans_list
        })
        
    return {
        "announcement": _ann_dict(ann),
        "results": results
    }
