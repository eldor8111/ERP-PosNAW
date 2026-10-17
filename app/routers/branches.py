from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.audit import log_action
from app.core.branch_context import BranchContext, _own_branch_id, get_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.company import Company
from app.models.user import User, UserRole, UserStatus
from app.models.warehouse import Warehouse
from app.schemas.branch import (
    BranchArchive, BranchContextOut, BranchCreate, BranchCreateOut, BranchOut, BranchReassignIn,
    BranchReceiptTemplates, BranchUpdate,
)
from app.services.branch_helpers import (
    BranchCloseBlocked, archive_branch, branch_close_blockers, clear_closed_fields, has_blockers, reopen_branch,
)
from app.services.branch_provisioning import get_default_warehouse, provision_branch
from app.services.tariff_guard import check_branch_limit

router = APIRouter(prefix="/branches", tags=["Branches"])

ADMIN_ROLES = (UserRole.admin, UserRole.director, UserRole.super_admin)

# PATCH orqali o'zgartirish mumkin bo'lgan maydonlar (company_id kirmaydi)
_UPDATABLE_FIELDS = ("name", "address", "phone", "is_active",
                     "code", "legal_name", "stir", "tax_regime", "working_hours")  # T4.2

# POST /branches da Branch(...) ga uzatilmaydigan provisioning maydonlari (T1.4)
_PROVISION_FIELDS = {"create_warehouse", "create_wallet", "warehouse_name", "wallet_name"}


DUPLICATE_NAME_DETAIL = "Bu nomli faol filial allaqachon mavjud"
DUPLICATE_CODE_DETAIL = "Bu kodli filial allaqachon mavjud"   # T4.2


def _ensure_name_free(db: Session, company_id: int, name: str, exclude_id: int = None) -> None:
    """T1.13: korxonada shu nomli (katta-kichik harf va chetdagi probellarsiz) faol filial bo'lsa 409.
    Poyga holatida oxirgi himoya — bazadagi uq_branches_company_name_active indeksi."""
    q = db.query(Branch.id).filter(
        Branch.company_id == company_id,
        Branch.is_active == True,  # noqa: E712
        func.lower(func.trim(Branch.name)) == (name or "").strip().lower(),
    )
    if exclude_id is not None:
        q = q.filter(Branch.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail=DUPLICATE_NAME_DETAIL)


def _ensure_code_free(db: Session, company_id: int, code, exclude_id: int = None) -> None:
    """T4.2: korxonada shu kodli (katta-kichik harfsiz) filial bo'lsa 409. Bo'sh kod cheklanmaydi.
    Poyga holatida oxirgi himoya — bazadagi uq_branches_company_code indeksi."""
    code = (code or "").strip()
    if not code:
        return
    q = db.query(Branch.id).filter(Branch.company_id == company_id, func.lower(Branch.code) == code.lower())
    if exclude_id is not None:
        q = q.filter(Branch.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail=DUPLICATE_CODE_DETAIL)


def _commit_or_conflict(db: Session) -> None:
    """commit(); faol filial nomi unikalligi buzilsa (poyga) 409, boshqa IntegrityError esa o'zgarishsiz qoladi."""
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if "uq_branches_company_name_active" in str(e.orig):
            raise HTTPException(status_code=409, detail=DUPLICATE_NAME_DETAIL)
        if "uq_branches_company_code" in str(e.orig):
            raise HTTPException(status_code=409, detail=DUPLICATE_CODE_DETAIL)
        raise


def _users_counts(db: Session, company_id, branch_ids) -> dict:
    """T3.1: {branch_id: faol xodimlar soni} — korxona bo'yicha (user_companies.branch_id ∪ user_branches ∪
    legacy users.branch_id). Bitta xodim bir filialda bir marta sanaladi."""
    from app.models.user_branch import UserBranch
    from app.models.user_company import UserCompany
    if not branch_ids:
        return {}
    pairs = set()
    for uid, bid in db.query(UserCompany.user_id, UserCompany.branch_id).join(
        User, User.id == UserCompany.user_id,
    ).filter(
        UserCompany.company_id == company_id, UserCompany.is_active == True,  # noqa: E712
        UserCompany.branch_id.in_(branch_ids), User.status == UserStatus.active,
    ).all():
        pairs.add((uid, bid))
    for uid, bid in db.query(UserBranch.user_id, UserBranch.branch_id).join(
        User, User.id == UserBranch.user_id,
    ).filter(
        UserBranch.company_id == company_id, UserBranch.branch_id.in_(branch_ids),
        User.status == UserStatus.active,
    ).all():
        pairs.add((uid, bid))
    for uid, bid in db.query(User.id, User.branch_id).filter(
        User.company_id == company_id, User.branch_id.in_(branch_ids), User.status == UserStatus.active,
    ).all():
        pairs.add((uid, bid))
    counts: dict = {}
    for _uid, bid in pairs:
        counts[bid] = counts.get(bid, 0) + 1
    return counts


def _branch_out(db: Session, branch: Branch, **extra) -> dict:
    """BranchOut + T1.4 maydonlari (`default_warehouse_id`, `warehouse_count`) — bitta filial uchun."""
    count = db.query(func.count(Warehouse.id)).filter(
        Warehouse.branch_id == branch.id, Warehouse.is_active == True,  # noqa: E712
    ).scalar() or 0
    dw = get_default_warehouse(db, branch.company_id, branch.id)
    out = BranchOut.model_validate(branch).model_dump()
    out.update(
        default_warehouse_id=dw.id if dw else None, warehouse_count=int(count), warehouses_count=int(count),
        users_count=_users_counts(db, branch.company_id, [branch.id]).get(branch.id, 0), **extra,
    )
    return out


@router.get("", response_model=List[BranchOut])
def list_branches(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # T1.2: include_inactive=true — xodim/ombor nofaol filialga biriktirilgan bo'lsa nomi ko'rinsin
    # T1.13: company_name uchun korxona bitta so'rovda yuklanadi (N+1 bo'lmasligi uchun)
    # T3.1: nofaol filiallar faqat admin/director/super_admin uchun; boshqa rollarga majburan faqat faollar
    if current_user.role not in ADMIN_ROLES:
        include_inactive = False
    q = db.query(Branch).options(joinedload(Branch.company))
    if not include_inactive:
        q = q.filter(Branch.is_active == True)  # noqa: E712
    q = q.filter(Branch.company_id == current_user.company_id)
    branches = q.order_by(Branch.name).all()
    if not branches:
        return []

    # T1.4: faol omborlar soni va asosiy (default) ombor — bitta agregat so'rov bilan
    ids = [b.id for b in branches]
    rows = db.query(Warehouse.branch_id, Warehouse.id, Warehouse.type, Warehouse.is_default).filter(
        Warehouse.branch_id.in_(ids),
        Warehouse.is_active == True,  # noqa: E712
    ).order_by(Warehouse.id).all()
    counts: dict = {}
    explicit: dict = {}
    fallback: dict = {}
    for bid, wid, wtype, is_def in rows:
        counts[bid] = counts.get(bid, 0) + 1
        if is_def:
            explicit.setdefault(bid, wid)
        if getattr(wtype, "value", wtype) in ("main", "shop"):
            fallback.setdefault(bid, wid)
    users_counts = _users_counts(db, current_user.company_id, ids)
    result = []
    for b in branches:
        out = BranchOut.model_validate(b).model_dump()
        out.update(
            default_warehouse_id=explicit.get(b.id) or fallback.get(b.id),
            warehouse_count=counts.get(b.id, 0),
            warehouses_count=counts.get(b.id, 0),   # T3.1: faol omborlar (warehouse_count bilan bir xil)
            users_count=users_counts.get(b.id, 0),
        )
        result.append(out)
    return result


@router.post("", response_model=BranchCreateOut)
def create_branch(
    data: BranchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    if current_user.role == UserRole.super_admin:
        # Super admin: company_id majburiy va korxona mavjud bo'lishi shart (yetim filial bo'lmasin)
        if not data.company_id:
            raise HTTPException(status_code=400, detail="Korxona ko'rsating")
        if not db.query(Company).filter(Company.id == data.company_id).first():
            raise HTTPException(status_code=404, detail="Korxona topilmadi")
        company_id = data.company_id
    else:
        company_id = current_user.company_id

    # Tarif limit tekshiruvi (korxona qatorini qulflaydi — parallel so'rovlardan himoya)
    check_branch_limit(db, company_id, current_user)
    _ensure_name_free(db, company_id, data.name)
    _ensure_code_free(db, company_id, data.code)   # T4.2

    branch = Branch(**data.model_dump(exclude=_PROVISION_FIELDS))
    branch.company_id = company_id
    # T1.4: korxonaning birinchi filiali — asosiy filial
    if not db.query(Branch.id).filter(Branch.company_id == company_id).first():
        branch.is_main = True
    db.add(branch)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "uq_branches_company_name_active" in str(e.orig):
            raise HTTPException(status_code=409, detail=DUPLICATE_NAME_DETAIL)
        if "uq_branches_company_code" in str(e.orig):
            raise HTTPException(status_code=409, detail=DUPLICATE_CODE_DETAIL)
        raise
    # T1.4: default ombor va kassa — filial bilan bitta tranzaksiyada
    wh, wallet = provision_branch(
        db, branch,
        create_warehouse=data.create_warehouse, create_wallet=data.create_wallet,
        warehouse_name=data.warehouse_name, wallet_name=data.wallet_name,
    )
    log_action(
        db, "CREATE", "branch", branch.id, user_id=current_user.id,
        new_values={
            "name": branch.name, "address": branch.address, "phone": branch.phone,
            "code": branch.code, "legal_name": branch.legal_name, "stir": branch.stir,
            "company_id": branch.company_id,
            "warehouse_id": wh.id if wh else None, "wallet_id": wallet.id if wallet else None,
        },
        company_id=branch.company_id, branch_id=branch.id,
    )
    _commit_or_conflict(db)
    db.refresh(branch)
    return _branch_out(
        db, branch,
        warehouse_id=wh.id if wh else None, wallet_id=wallet.id if wallet else None,
    )


@router.get("/my-context", response_model=BranchContextOut)
def my_branch_context(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    """T1.1: joriy foydalanuvchining filial konteksti (frontend BranchContext uchun).
    `/{branch_id}` dan OLDIN e'lon qilingan — aks holda "my-context" int ga tushib 422 beradi."""
    q = db.query(Branch).filter(Branch.is_active == True)  # noqa: E712
    q = q.filter(Branch.company_id == current_user.company_id)
    branches = q.order_by(Branch.name).all()
    if ctx.allowed_branch_ids is not None:
        branches = [b for b in branches if b.id in ctx.allowed_branch_ids]
    can_select_all = ctx.allowed_branch_ids is None
    return {
        "branches": [{"id": b.id, "name": b.name} for b in branches],
        "current_branch_id": ctx.branch_id,
        # T1.2: joriy korxona bo'yicha asosiy filial (user_companies.branch_id, legacy users.branch_id)
        "assigned_branch_id": _own_branch_id(db, current_user),
        "can_select_all": can_select_all,
        # super_admin uchun header e'tiborsiz — almashtirgich ko'rsatilmaydi;
        # T1.2: bir nechta filialga biriktirilgan xodim ham ular orasida almashtira oladi
        "can_switch": (can_select_all or len(branches) > 1) and current_user.role != UserRole.super_admin,
        "needs_branch_assignment": ctx.needs_assignment,
    }


@router.get("/{branch_id}", response_model=BranchOut)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Branch).filter(Branch.id == branch_id)
    q = q.filter(Branch.company_id == current_user.company_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    return _branch_out(db, branch)


def _branch_header(branch: Branch) -> dict:
    """T4.2: chek sarlavhasi uchun filial rekvizitlari (POS oflayn chekda ham ishlatadi)."""
    return {
        "id": branch.id, "name": branch.name, "legal_name": branch.legal_name,
        "address": branch.address, "phone": branch.phone, "stir": branch.stir,
        "tax_regime": branch.tax_regime, "working_hours": branch.working_hours,
    }


@router.get("/{branch_id}/receipt_templates")
def get_branch_receipt_templates(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """T4.2: filial chek shablonlari (`{"r58":{}, "r80":{}, "nak":{}}`; bo'sh = korxona shabloni) va filial rekvizitlari.
    Kassir ham o'qiy oladi — POS chekni oflayn rejimda ham filial rekvizitlari bilan chop etadi."""
    branch = db.query(Branch).filter(
        Branch.id == branch_id, Branch.company_id == current_user.company_id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    return {"receipt_templates": branch.receipt_templates or {}, "branch": _branch_header(branch)}


@router.put("/{branch_id}/receipt_templates")
def update_branch_receipt_templates(
    branch_id: int,
    data: BranchReceiptTemplates,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """T4.2: filial chek shablonlarini saqlash. Hammasi bo'sh bo'lsa NULL yoziladi (korxona shabloniga qaytadi)."""
    from app.routers.companies import _validate_receipt_cfg   # korxona shabloni bilan bir xil tekshiruv
    branch = db.query(Branch).filter(
        Branch.id == branch_id, Branch.company_id == current_user.company_id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    out = {}
    for name in ("r58", "r80", "nak"):
        cfg = getattr(data, name)
        if not cfg:
            continue
        try:
            out[name] = _validate_receipt_cfg(name, cfg)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    old_has = bool(branch.receipt_templates)
    branch.receipt_templates = out or None
    log_action(
        db, "UPDATE", "branch", branch.id, user_id=current_user.id,
        old_values={"receipt_templates": old_has}, new_values={"receipt_templates": sorted(out)},
        company_id=branch.company_id, branch_id=branch.id,
    )
    db.commit()
    return {"ok": True, "receipt_templates": branch.receipt_templates or {}}


@router.patch("/{branch_id}", response_model=BranchOut)
def update_branch(
    branch_id: int,
    data: BranchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    q = db.query(Branch).filter(Branch.id == branch_id)
    q = q.filter(Branch.company_id == current_user.company_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")

    # Oq ro'yxat: company_id va boshqa maydonlar hech qachon o'zgartirilmaydi
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _UPDATABLE_FIELDS}

    if "name" in fields and (fields["name"] is None or not str(fields["name"]).strip()):
        raise HTTPException(status_code=400, detail="Filial nomi bo'sh bo'lmasligi kerak")
    # is_active ustuni NOT NULL emas, lekin null yuborilsa holat o'zgarmaydi
    if fields.get("is_active") is None:
        fields.pop("is_active", None)

    # T1.12: faol filialni nofaol qilish = arxivlash (ochiq smena/qoldiq/balans/... bo'lsa 409)
    if fields.get("is_active") is False and branch.is_active:
        blocked = _archive_or_409(db, branch, current_user, None, None)
        if blocked is not None:
            return blocked
        fields.pop("is_active")
    elif fields.get("is_active") is False:
        fields.pop("is_active")   # allaqachon nofaol

    # Nofaol filialni qayta yoqishda tarif limiti tekshiriladi
    reopening = fields.get("is_active") is True and not branch.is_active
    if reopening:
        check_branch_limit(db, branch.company_id, current_user, exclude_branch_id=branch.id)

    # T1.13: yangi nom yoki qayta yoqish natijasida faol nomlar to'qnashmasligi kerak
    if (fields.get("is_active", branch.is_active)) and ("name" in fields or fields.get("is_active") is True):
        _ensure_name_free(db, branch.company_id, fields.get("name", branch.name), exclude_id=branch.id)

    # T4.2: kod noyobligi (maydon bo'shatilsa tekshirilmaydi)
    if fields.get("code"):
        _ensure_code_free(db, branch.company_id, fields["code"], exclude_id=branch.id)

    old_values = {k: getattr(branch, k) for k in fields}
    for field, value in fields.items():
        setattr(branch, field, value)
    if reopening:
        clear_closed_fields(branch)   # T1.12
    if fields:
        log_action(
            db, "UPDATE", "branch", branch.id, user_id=current_user.id,
            old_values=old_values, new_values=fields,
            company_id=branch.company_id, branch_id=branch.id,
        )
    _commit_or_conflict(db)
    db.refresh(branch)
    return _branch_out(db, branch)


def _archive_or_409(db: Session, branch: Branch, user: User, reason, reassign_to, action: str = "ARCHIVE"):
    """T1.12: `archive_branch`; blokerlar bo'lsa 409 JSONResponse (`detail` matn + `blockers`), aks holda `None`.
    Hech narsa o'zgarmaganda (blokerlar) sessiya ifloslanmaydi, shuning uchun rollback shart emas."""
    try:
        archive_branch(db, branch, user, reason, reassign_to, action=action)
    except BranchCloseBlocked as e:
        return JSONResponse(status_code=409, content={"detail": e.detail, "blockers": e.blockers})
    return None


def _get_company_branch(db: Session, branch_id: int, current_user: User) -> Branch:
    q = db.query(Branch).filter(Branch.id == branch_id)
    if current_user.role != UserRole.super_admin:
        q = q.filter(Branch.company_id == current_user.company_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    return branch


@router.get("/{branch_id}/close-check")
def branch_close_check(
    branch_id: int,
    reassign_users_to_branch_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """T1.12: filialni yopishdan oldin tekshiruv — nima to'sqinlik qilayotgani."""
    branch = _get_company_branch(db, branch_id, current_user)
    blockers = branch_close_blockers(
        db, branch, reassign_users=reassign_users_to_branch_id is not None, exclude_user_id=current_user.id)
    return {"can_close": not has_blockers(blockers), "blockers": blockers}


@router.post("/{branch_id}/archive")
def branch_archive(
    branch_id: int,
    data: Optional[BranchArchive] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """T1.12: filialni arxivlash (blokerlar bo'lsa 409). Xodimlar `reassign_users_to_branch_id` ga ko'chadi."""
    data = data or BranchArchive()
    branch = _get_company_branch(db, branch_id, current_user)
    if not branch.is_active:
        raise HTTPException(status_code=400, detail="Filial allaqachon yopilgan")
    blocked = _archive_or_409(db, branch, current_user, data.reason, data.reassign_users_to_branch_id)
    if blocked is not None:
        return blocked
    db.commit()
    db.refresh(branch)
    return _branch_out(db, branch)


@router.post("/{branch_id}/reopen")
def branch_reopen(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """T1.12: nofaol filialni qayta faollashtirish (tarif limiti: 403). Omborlar/kassalar avto-yoqilmaydi."""
    branch = _get_company_branch(db, branch_id, current_user)
    _ensure_name_free(db, branch.company_id, branch.name, exclude_id=branch.id)
    extra = reopen_branch(db, branch, current_user)
    _commit_or_conflict(db)
    db.refresh(branch)
    return _branch_out(db, branch, **extra)


@router.delete("/{branch_id}", status_code=204)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    q = db.query(Branch).filter(Branch.id == branch_id)
    q = q.filter(Branch.company_id == current_user.company_id)
    branch = q.first()
    if not branch:
        raise HTTPException(status_code=404, detail="Filial topilmadi")
    # T1.12: o'chirish = arxivlash (ochiq smena/qoldiq/balans/xodim... bo'lsa 409)
    if branch.is_active:
        blocked = _archive_or_409(db, branch, current_user, None, None, action="DELETE")
        if blocked is not None:
            return blocked
    db.commit()


# ── T4.5: ommaviy qayta biriktirish (mijoz / xodim / ombor / kassa) ───────────────────────────

REASSIGN_MAX_IDS = 1000
WAREHOUSE_REASSIGN_NEEDS_SNAPSHOT = "Sotuv filial snapshoti kerak: omborda filial belgisi yo'q sotuvlar bor"
WALLET_REASSIGN_OPEN_SHIFT = "Ochiq smenali kassani boshqa filialga ko'chirib bo'lmaydi"


def _reassign_customers(db: Session, user: User, ids: list, to_branch_id: int, ctx: dict) -> int:
    from app.models.customer import Customer

    rows = db.query(Customer).filter(Customer.id.in_(ids), Customer.company_id == user.company_id).all()
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")
    updated = 0
    for c in rows:
        if c.branch_id == to_branch_id:
            ctx["skipped"].append({"id": c.id, "reason": "Allaqachon shu filialda"})
            continue
        ctx["old"][c.id] = c.branch_id
        c.branch_id = to_branch_id
        updated += 1
    return updated


def _reassign_users(db: Session, user: User, ids: list, to_branch_id: int, ctx: dict) -> int:
    from sqlalchemy import and_, or_

    from app.models.user_company import UserCompany
    from app.routers.users import _sync_personal_wallet_branch

    cid = user.company_id
    rows = db.query(User).outerjoin(
        UserCompany, and_(UserCompany.user_id == User.id, UserCompany.company_id == cid),
    ).filter(
        User.id.in_(ids), or_(User.company_id == cid, UserCompany.id.isnot(None)),
    ).all()
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    ucs = {uc.user_id: uc for uc in db.query(UserCompany).filter(
        UserCompany.user_id.in_(ids), UserCompany.company_id == cid).all()}
    updated = 0
    for u in rows:
        if u.role == UserRole.super_admin:
            ctx["skipped"].append({"id": u.id, "reason": "Super admin filialga biriktirilmaydi"})
            continue
        uc = ucs.get(u.id)
        mirror = u.company_id == cid          # users.branch_id - faqat asosiy korxona ko'zgusi (T1.2)
        old = uc.branch_id if uc is not None else None
        if old is None and mirror:
            old = u.branch_id
        if old == to_branch_id and (not mirror or u.branch_id == to_branch_id):
            ctx["skipped"].append({"id": u.id, "reason": "Allaqachon shu filialda"})
            continue
        ctx["old"][u.id] = old
        if uc is not None:
            uc.branch_id = to_branch_id
        if mirror:
            u.branch_id = to_branch_id
        _sync_personal_wallet_branch(db, u.id, cid, to_branch_id)
        updated += 1
        if u.id == user.id:
            ctx["warnings"].append("Siz o'zingizni boshqa filialga ko'chirdingiz: keyingi so'rovlarda "
                                   "joriy filial o'zgaradi")
    return updated


def _reassign_wallets(db: Session, user: User, ids: list, to_branch_id: int, ctx: dict) -> int:
    from app.models.moliya import KassaSession, Wallet

    rows = db.query(Wallet).filter(Wallet.id.in_(ids), Wallet.company_id == user.company_id).all()
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="Kassa topilmadi")
    moving = [w for w in rows if w.branch_id != to_branch_id]
    open_ids = {w.id for w in moving if w.is_open}
    if moving:
        open_ids |= {r[0] for r in db.query(KassaSession.wallet_id).filter(
            KassaSession.wallet_id.in_([w.id for w in moving]), KassaSession.status == "open",
        ).all()}
    if open_ids:
        names = ", ".join(w.name for w in moving if w.id in open_ids)
        raise HTTPException(status_code=409, detail=f"{WALLET_REASSIGN_OPEN_SHIFT}: {names}")
    for w in rows:
        if w.branch_id == to_branch_id:
            ctx["skipped"].append({"id": w.id, "reason": "Allaqachon shu filialda"})
    for w in moving:
        ctx["old"][w.id] = w.branch_id
        w.branch_id = to_branch_id
    return len(moving)


def _reassign_warehouses(db: Session, user: User, ids: list, to_branch_id, ctx: dict) -> int:
    from app.models.sale import Sale
    from app.services.branch_provisioning import (
        DEFAULT_CANDIDATE_TYPES, reassign_default_warehouse, set_default_warehouse,
    )

    rows = db.query(Warehouse).filter(Warehouse.id.in_(ids), Warehouse.company_id == user.company_id).all()
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    moving = [w for w in rows if w.branch_id != to_branch_id]
    for w in rows:
        if w.branch_id == to_branch_id:
            ctx["skipped"].append({"id": w.id, "reason": "Allaqachon shu filialda"})
    if not moving:
        return 0
    # Hisobotlar filialni ombor orqali aniqlaydi: filial belgisi (T1.9 snapshot) yo'q sotuvlar
    # bo'lsa, ko'chirish o'tmishdagi sotuvlar filialini ham o'zgartirib yuboradi -> 409
    sale_branch = getattr(Sale, "branch_id", None)
    if sale_branch is None or db.query(Sale.id).filter(
        Sale.warehouse_id.in_([w.id for w in moving]), sale_branch.is_(None),
    ).first() is not None:
        raise HTTPException(status_code=409, detail=WAREHOUSE_REASSIGN_NEEDS_SNAPSHOT)
    for wh in moving:
        old_branch = wh.branch_id
        was_default = bool(wh.is_default)
        ctx["old"][wh.id] = old_branch
        wh.branch_id = to_branch_id
        if was_default:
            wh.is_default = False
            db.flush()
            reassign_default_warehouse(db, old_branch, exclude_id=wh.id)
        if to_branch_id is not None and wh.type in DEFAULT_CANDIDATE_TYPES and wh.is_active is not False:
            has_default = db.query(Warehouse.id).filter(
                Warehouse.branch_id == to_branch_id, Warehouse.is_default == True,  # noqa: E712
                Warehouse.is_active == True, Warehouse.id != wh.id,  # noqa: E712
            ).first() is not None
            if not has_default:
                set_default_warehouse(db, wh)
        db.flush()
        log_action(db, "WAREHOUSE_BRANCH_CHANGE", "warehouse", wh.id, user_id=user.id,
                   old_values={"branch_id": old_branch},
                   new_values={"branch_id": to_branch_id, "source": "bulk-reassign"},
                   company_id=user.company_id, branch_id=to_branch_id)
    return len(moving)


_REASSIGNERS = {
    "customers": _reassign_customers,
    "users": _reassign_users,
    "wallets": _reassign_wallets,
    "warehouses": _reassign_warehouses,
}


@router.post("/reassign")
def reassign_to_branch(
    data: BranchReassignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """T4.5: mijoz / xodim / ombor / kassalarni ommaviy boshqa filialga ko'chirish (ko'pi bilan 1000 id).

    Barcha `ids` korxonaga tegishli bo'lishi shart, aks holda 404 va hech narsa o'zgarmaydi.
    `to_branch_id=null` faqat `warehouses` uchun (filialdan ajratish). Ochiq smenali kassa va filial
    snapshoti yo'q sotuvli ombor - 409. Javob: `{updated, skipped: [{id, reason}], warnings}`."""
    ids = list(dict.fromkeys(data.ids))
    to_branch_id = data.to_branch_id
    if to_branch_id is None:
        if data.entity != "warehouses":
            raise HTTPException(status_code=400, detail="Maqsad filial ko'rsatilishi shart")
    else:
        from app.services.branch_helpers import get_active_branch
        get_active_branch(db, to_branch_id, current_user.company_id)

    ctx = {"old": {}, "skipped": [], "warnings": []}
    # Tekshiruvlar (404/409) o'zgartirishdan OLDIN bajariladi - xatoda hech narsa o'zgarmaydi
    updated = _REASSIGNERS[data.entity](db, current_user, ids, to_branch_id, ctx)
    log_action(
        db, "BULK_REASSIGN", data.entity, None, user_id=current_user.id,
        old_values={"count": len(ids), "ids": ids, "branch_ids": {str(k): v for k, v in ctx["old"].items()}},
        new_values={"to_branch_id": to_branch_id, "updated": updated, "skipped": len(ctx["skipped"])},
        company_id=current_user.company_id, branch_id=to_branch_id,
    )
    db.commit()
    return {"updated": updated, "skipped": ctx["skipped"], "warnings": ctx["warnings"]}
