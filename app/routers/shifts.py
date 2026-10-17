"""
Shifts API: Manage cashier shifts.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, BackgroundTasks  # type: ignore
from sqlalchemy.orm import Session, joinedload  # type: ignore
from sqlalchemy.exc import IntegrityError  # type: ignore
from pydantic import BaseModel, Field  # type: ignore
from decimal import Decimal
from datetime import date, datetime, timezone

from app.database import get_db  # type: ignore
from app.models.shift import Shift  # type: ignore
from app.core.dependencies import get_current_user, require_roles  # type: ignore
from app.core.branch_context import (
    BRANCH_BYPASS_ROLES, BRANCH_FORBIDDEN, BranchContext, apply_branch_scope, assigned_branch_ids,
    company_branch_exists, get_branch_context,
)
from app.models.user import User, UserRole  # type: ignore
from app.models.currency import Currency
from app.models.sale import Sale, SalePayment
from sqlalchemy import func, or_, and_

from app.services.wallet_resolver import resolve_wallet, assert_wallet_access
from app.services.tenant_guards import resolve_tx_branch
from app.utils.report_utils import is_return_doc, date_bounds

router = APIRouter(prefix="/shifts", tags=["shifts"])

# Haqiqiy pul tushmaydigan to'lov turlari — inkassatsiyaga kirmaydi (qarz, keshbek, aralash)
NON_CASH_PAYMENT_TYPES = ("debt", "cashback", "mixed")
HANDOVER_BRANCH_MISMATCH = "Kassalar turli filialga tegishli: inkassatsiya mumkin emas"
SHIFT_ALREADY_CLOSED = "Smena allaqachon yopilgan"
SHIFT_ALREADY_OPEN = "Kassir uchun faol smena allaqachon mavjud"
SELECT_BRANCH = "Filial tanlang"
WALLET_NOT_FOUND = "Kassa topilmadi"
WALLET_INACTIVE = "Kassa nofaol"
WALLET_OTHER_BRANCH = "Kassa boshqa filialga tegishli"
SHIFT_FORBIDDEN = "Bu smenani ko'rishga ruxsat yo'q"


def _branches_compatible(a, b) -> bool:
    """Ikkala filial ham bo'sh bo'lmasa va farqli bo'lsa mos emas."""
    return not (a and b and a != b)


def _handover_wallet_options(db: Session, company_id, source_wallet_id, branch_id, user_id=None) -> list:
    """Inkassatsiya uchun qabul qiluvchi kassalar: faol, shu korxona, filiali mos, manbadan boshqa.

    T2.8: `is_default` — `user_id` foydalanuvchisining default kassasi (UI faqat shuni oldindan tanlaydi,
    ro'yxatning birinchi elementini emas)."""
    from app.models.moliya import Wallet
    from app.models.user import UserWallet
    from app.services.wallet_access import find_company_wallet
    source = find_company_wallet(db, source_wallet_id, company_id)
    ref_branch = source.branch_id if source is not None else branch_id
    rows = db.query(Wallet).filter(
        Wallet.company_id == company_id,
        Wallet.is_active == True,  # noqa: E712
        Wallet.is_personal == False,  # noqa: E712  (T1.10: kuryer/agent qo'l kassasi qabul qiluvchi bo'lmaydi)
    ).order_by(Wallet.id.asc()).all()
    defaults = set()
    if user_id is not None:
        defaults = {
            r[0] for r in db.query(UserWallet.wallet_id).filter(
                UserWallet.user_id == user_id, UserWallet.is_default == True,  # noqa: E712
            ).all()
        }
    return [
        {
            "id": w.id, "name": w.name, "type": w.type,
            "branch_id": w.branch_id, "balance": float(w.balance or 0),
            "is_default": w.id in defaults,
        }
        for w in rows
        if w.id != source_wallet_id and _branches_compatible(ref_branch, w.branch_id)
    ]


def _shift_source_wallet_id(db: Session, cashier, shift) -> Optional[int]:
    """Inkassatsiya manbasi — kassirning kassasi (T1.10: `resolve_wallet`: biriktirilgan -> smena filiali kassasi).
    Topilmasa (yoki ko'p filialli korxonada kassa sozlanmagan bo'lsa) `None` — xato ko'tarilmaydi."""
    try:
        w = resolve_wallet(db, cashier, branch_id=shift.branch_id, purpose="shift_close")
    except HTTPException:
        return None
    return w.id if w is not None else None


def _shift_sale_filter(shift: "Shift"):
    """Sotuvni smenaga bog'lash sharti: yangi sotuvlar aniq shift_id orqali,
    eski (shift_id NULL) sotuvlar uchun avvalgi vaqt-oyna usuli zaxira.

    T1.11: zaxira tarmog'iga YUQORI chegara bor — smena yopilgach (`closed_at`) kassir qilgan
    smenasiz sotuvlar yopilgan smena hisobotiga tushmaydi."""
    fallback = [
        Sale.shift_id.is_(None),
        Sale.cashier_id == shift.cashier_id,
        Sale.created_at >= shift.opened_at,
    ]
    if shift.closed_at is not None:
        fallback.append(Sale.created_at <= shift.closed_at)
    return or_(Sale.shift_id == shift.id, and_(*fallback))


class ShiftOpen(BaseModel):
    branch_id: Optional[int] = None
    wallet_id: Optional[int] = None
    opening_cash: Decimal = Field(default=Decimal("0"), ge=0)
    note: Optional[str] = None


class ShiftClose(BaseModel):
    closing_cash: Optional[Decimal] = Field(default=None, ge=0)   # Kassir sanagan naqd pul
    wallet_id: Optional[int] = None          # Naqd tushadigan hamyon
    wallet_card_id: Optional[int] = None     # Plastik/Terminal tushadigan hamyon
    note: Optional[str] = None


ADMIN_ROLES = BRANCH_BYPASS_ROLES  # T1.1: yagona bypass rollar (super_admin ham)
MANAGER_ROLES = (UserRole.manager,)


def _role(user) -> Optional[UserRole]:
    r = getattr(user, "role", None)
    if isinstance(r, UserRole):
        return r
    try:
        return UserRole(r) if r else None
    except ValueError:
        return None


def _manager_branch_ids(db: Session, user) -> list:
    """Manager ko'ra oladigan filiallar (o'zi biriktirilgan). Bo'sh ro'yxat — filiali yo'q."""
    return assigned_branch_ids(db, user)


def _can_access_shift(db: Session, user, shift: "Shift") -> bool:
    """Smenani ko'rish/yopish huquqi: super_admin hamma; admin/director o'z korxonasida;
    manager o'z filiali smenasini; qolganlar faqat o'zinikini."""
    role = _role(user)
    if role == UserRole.super_admin:
        return True
    if shift.company_id != user.company_id:
        return False
    if role in ADMIN_ROLES:
        return True
    if shift.cashier_id == user.id:
        return True
    if role in MANAGER_ROLES:
        return shift.branch_id is not None and shift.branch_id in _manager_branch_ids(db, user)
    return False


def _money(v) -> Optional[float]:
    return float(v) if v is not None else None


def _shift_dict(s: "Shift") -> dict:
    """Smenaning yagona chiqish sxemasi (ro'yxat, `GET /shifts/{id}`, Z-hisobot)."""
    return {
        "id": s.id,
        "cashier_id": s.cashier_id,
        "cashier_name": s.cashier.name if s.cashier else None,
        "branch_id": s.branch_id,
        "branch_name": s.branch.name if s.branch else None,
        "wallet_id": s.wallet_id,
        "opened_at": s.opened_at,
        "closed_at": s.closed_at,
        "opening_cash": s.opening_cash,
        "closing_cash": s.closing_cash,
        "expected_cash": s.expected_cash,
        "cash_difference": s.cash_difference,
        "difference": s.cash_difference,
        "handover_cash_amount": s.handover_cash_amount,
        "closed_by": s.closed_by,
        "closed_by_name": s.closer.name if s.closer else None,
        "note_open": s.note_open,
        "note_close": s.note_close,
        "status": s.status,
    }


@router.get("")
def list_shifts(
    response: Response,
    branch_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    cashier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    q = db.query(Shift).options(joinedload(Shift.cashier), joinedload(Shift.branch))
    role = _role(current_user)
    if role != UserRole.super_admin:
        q = q.filter(Shift.company_id == current_user.company_id)
    if role in ADMIN_ROLES:
        # T1.1: yagona filial konteksti — bypass uchun `?branch_id=` header'dan ustun
        q = apply_branch_scope(q, ctx, Shift.branch_id, explicit_branch_id=branch_id)
    elif role in MANAGER_ROLES:
        # T1.11: manager faqat o'z filiali; filiali bo'lmasa faqat o'zi
        ids = _manager_branch_ids(db, current_user)
        if ids:
            q = q.filter(Shift.branch_id.in_(ids))
            q = apply_branch_scope(q, ctx, Shift.branch_id, explicit_branch_id=branch_id)
        else:
            q = q.filter(Shift.cashier_id == current_user.id)
    else:
        # T1.11: kassir va boshqa rollar faqat o'z smenalarini ko'radi
        q = q.filter(Shift.cashier_id == current_user.id)
        q = apply_branch_scope(q, ctx, Shift.branch_id, explicit_branch_id=branch_id)
    if status:
        q = q.filter(Shift.status == status)
    if cashier_id:
        q = q.filter(Shift.cashier_id == cashier_id)
    if date_from or date_to:
        start, end = date_bounds(date_from, date_to)
        q = q.filter(Shift.opened_at >= start, Shift.opened_at < end)
    total = q.order_by(None).count()
    response.headers["X-Total-Count"] = str(total)
    shifts = q.order_by(Shift.opened_at.desc(), Shift.id.desc()).offset(skip).limit(limit).all()
    return [_shift_dict(s) for s in shifts]


def _refund_by_payment(db: Session, shift: "Shift") -> dict:
    """Smena davomidagi qaytarish hujjatlari (R...) bo'yicha {ptype: {currency: Decimal}} va soni."""
    rows = db.query(
        Sale.payment_type,
        func.coalesce(Currency.code, 'UZS').label("currency"),
        func.coalesce(func.sum(Sale.paid_amount), 0).label("paid_total"),
        func.coalesce(func.sum(Sale.paid_cash), 0).label("cash_total"),
        func.coalesce(func.sum(Sale.paid_card), 0).label("card_total"),
        func.count(Sale.id).label("cnt"),
    ).outerjoin(Currency, Currency.id == Sale.currency_id).filter(
        _shift_sale_filter(shift),
        Sale.status == "refunded",
        Sale.number.like("R%"),
    ).group_by(Sale.payment_type, Currency.code).all()

    result: dict = {}
    count = 0

    def _put(ptype: str, curr: str, amt: Decimal):
        if amt <= 0:
            return
        result.setdefault(ptype, {})
        result[ptype][curr] = result[ptype].get(curr, Decimal("0")) + amt

    for r in rows:
        count += int(r.cnt or 0)
        curr = r.currency or 'UZS'
        ptype = r.payment_type.value if hasattr(r.payment_type, 'value') else str(r.payment_type)
        if ptype == "mixed":
            _put("cash", curr, Decimal(str(r.cash_total)))
            _put("card", curr, Decimal(str(r.card_total)))
        elif ptype not in ("debt", "cashback"):
            _put(ptype, curr, Decimal(str(r.paid_total)))
    return {"by_payment": result, "count": count}


def _debt_payments_by_payment(db: Session, shift: "Shift") -> dict:
    """Smena davomida shu kassir qabul qilgan mijoz qarz to'lovlari: {ptype: {currency: Decimal}}."""
    from app.models.moliya import KassaMovement
    conds = [
        KassaMovement.created_by == shift.cashier_id,
        KassaMovement.created_at >= shift.opened_at,
        KassaMovement.reference_type == "customer_payment",
        KassaMovement.direction == "in",
    ]
    if shift.closed_at is not None:
        conds.append(KassaMovement.created_at <= shift.closed_at)   # T1.11: yuqori chegara
    rows = db.query(
        KassaMovement.payment_type,
        func.coalesce(KassaMovement.currency, 'UZS').label("currency"),
        func.coalesce(func.sum(KassaMovement.amount), 0).label("total"),
    ).filter(*conds).group_by(KassaMovement.payment_type, KassaMovement.currency).all()
    result: dict = {}
    for r in rows:
        ptype = r.payment_type or "cash"
        if ptype in ("debt", "cashback"):
            continue
        amt = Decimal(str(r.total))
        if amt <= 0:
            continue
        result.setdefault(ptype, {})
        result[ptype][r.currency or 'UZS'] = result[ptype].get(r.currency or 'UZS', Decimal("0")) + amt
    return result


def _apply_shift_adjustments(db: Session, shift: Shift, balances: dict) -> None:
    """Smena balansiga sotuvdan tashqari pul oqimlarini kiritadi:

    (a) Qaytarishlar (vazvrat hujjatlari, number 'R...' bilan boshlanadi) —
        kassirdan mijozga qaytarilgan pul mos payment_type dan AYIRILADI.
        Aks holda naqd qaytarish bo'lgan smenada halol kassir "kamomad"
        bilan yopiladi.
    (b) Mijoz qarz to'lovlari (KassaMovement, reference_type=customer_payment)
        — kassir qabul qilgan pul QO'SHILADI. Aks holda hisobotda
        ko'rinmaydigan "ortiqcha" pul paydo bo'ladi.
    """
    # (a) Qaytarishlar. Faqat vazvrat HUJJATLARI (number 'R%') — to'liq
    # qaytarilgan original sotuvlar ham status=refunded bo'ladi, lekin
    # ularning paid_* qiymati kirim bo'lib qoladi (vazvrat hujjati ayiradi).
    for ptype, curr_map in _refund_by_payment(db, shift)["by_payment"].items():
        for curr, amt in curr_map.items():
            balances.setdefault(ptype, {})
            balances[ptype][curr] = balances[ptype].get(curr, Decimal("0")) - amt

    # (b) Mijoz qarz to'lovlari — shu kassir qabul qilganlari.
    for ptype, curr_map in _debt_payments_by_payment(db, shift).items():
        for curr, amt in curr_map.items():
            balances.setdefault(ptype, {})
            balances[ptype][curr] = balances[ptype].get(curr, Decimal("0")) + amt


def _collect_shift_components(db: Session, shift: Shift) -> dict:
    """Smena komponentlari (yagona manba): `/current`, smena yopilishi va Z-hisobot shuni ishlatadi.

    Qaytaradi: `balances` {ptype: {currency: Decimal}} (qaytarishlar ayirilgan, qarz to'lovlari qo'shilgan),
    `cash_total` (UZS naqd), `expected_cash` (boshlang'ich + naqd), `total_sales` {currency: float}."""
    payments = db.query(
        SalePayment.payment_type,
        func.coalesce(Currency.code, 'UZS').label("currency"),
        func.sum(SalePayment.amount).label("total")
    ).join(Sale, SalePayment.sale_id == Sale.id).outerjoin(Currency, Currency.id == Sale.currency_id).filter(
        _shift_sale_filter(shift),
        Sale.status != "cancelled"
    ).group_by(SalePayment.payment_type, Currency.code).all()

    balances: dict = {}
    total_sales: dict = {}
    for p in payments:
        curr = p.currency or 'UZS'
        balances.setdefault(p.payment_type, {})[curr] = Decimal(str(p.total))
        total_sales[curr] = float(total_sales.get(curr, 0)) + float(p.total)

    # Qaytarishlar (-) va qarz to'lovlari (+) — kutilgan qoldiq real bo'lsin
    _apply_shift_adjustments(db, shift, balances)

    cash_total = balances.get("cash", {}).get("UZS", Decimal("0"))
    expected_cash = Decimal(str(shift.opening_cash or 0)) + cash_total
    return {
        "balances": balances, "cash_total": cash_total,
        "expected_cash": expected_cash, "total_sales": total_sales,
    }


def _calc_shift_payment_balances(db: Session, shift: Shift):
    """SalePayment jadvalidan smena davomidagi to'lovlarni hisoblaydi: (UZS naqd jami, balances)."""
    comp = _collect_shift_components(db, shift)
    return comp["cash_total"], comp["balances"]


@router.get("/current")
def get_current_shift(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get the currently active (open) shift for the authenticated user, including totals."""
    shift = db.query(Shift).filter(
        Shift.cashier_id == user.id, Shift.status == "open", Shift.company_id == user.company_id,  # T1.1: korxona filtri
    ).first()
    if not shift:
        return None

    comp = _collect_shift_components(db, shift)
    balances = {
        ptype: {curr: str(amt) for curr, amt in curr_map.items()}
        for ptype, curr_map in comp["balances"].items()
    }
    if "cash" not in balances:
        balances["cash"] = {}
    expected_cash = comp["expected_cash"]

    # T0.28: inkassatsiya manbasi (kassir kassasi) va UI uchun mos qabul qiluvchi kassalar
    shift_company_id = shift.company_id or user.company_id
    cashier_wallet_id = _shift_source_wallet_id(db, shift.cashier or user, shift)
    handover_wallets = _handover_wallet_options(db, shift_company_id, cashier_wallet_id, shift.branch_id, user.id)

    return {
        "id": shift.id,
        "cashier_id": shift.cashier_id,
        "cashier_name": shift.cashier.name if shift.cashier else None,
        "branch_id": shift.branch_id,
        "branch_name": shift.branch.name if shift.branch else None,
        "wallet_id": shift.wallet_id,
        "opened_at": shift.opened_at,
        "closed_at": shift.closed_at,
        "opening_cash": str(shift.opening_cash),
        "expected_cash": str(expected_cash),
        "balances": balances,
        "total_sales": comp["total_sales"],
        "status": shift.status,
        "cashier_wallet_id": cashier_wallet_id,
        "handover_wallets": handover_wallets,
    }


@router.get("/summary")
def shifts_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    """Filial bo'yicha ochiq smenalar va kassalar xulosasi (admin/director/manager)."""
    from app.models.branch import Branch
    from app.models.moliya import Wallet
    q = db.query(Branch).filter(Branch.company_id == user.company_id, Branch.is_active == True)  # noqa: E712
    if _role(user) == UserRole.manager:
        ids = _manager_branch_ids(db, user)
        if ids:
            q = q.filter(Branch.id.in_(ids))
    branches = q.order_by(Branch.id.asc()).all()
    branch_ids = [b.id for b in branches]
    open_shifts = db.query(Shift).options(joinedload(Shift.cashier)).filter(
        Shift.company_id == user.company_id, Shift.status == "open", Shift.branch_id.in_(branch_ids or [0]),
    ).order_by(Shift.opened_at.asc()).all()
    wallets = db.query(Wallet).filter(
        Wallet.company_id == user.company_id, Wallet.is_active == True,  # noqa: E712
        Wallet.is_personal == False,  # noqa: E712
        Wallet.branch_id.in_(branch_ids or [0]),
    ).order_by(Wallet.id.asc()).all()
    by_shift: dict = {}
    for s in open_shifts:
        by_shift.setdefault(s.branch_id, []).append({
            "id": s.id, "cashier_name": s.cashier.name if s.cashier else None,
            "opened_at": s.opened_at, "wallet_id": s.wallet_id,
        })
    by_wallet: dict = {}
    for w in wallets:
        by_wallet.setdefault(w.branch_id, []).append({
            "id": w.id, "name": w.name, "balance": float(w.balance or 0), "is_open": bool(w.is_open),
        })
    return [
        {
            "branch_id": b.id, "branch_name": b.name,
            "open_shifts": by_shift.get(b.id, []), "wallets": by_wallet.get(b.id, []),
        }
        for b in branches
    ]


@router.get("/handover-wallets")
def handover_wallets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Inkassatsiya uchun kassalar: shu korxona, faol, filiali mos (yoki filialsiz) va shaxsiy
    (kuryer/agent qo'l kassasi) emas. Hech narsa avto-tanlanmaydi."""
    shift = db.query(Shift).filter(
        Shift.cashier_id == user.id, Shift.status == "open", Shift.company_id == user.company_id,  # T1.1: korxona filtri
    ).first()
    company_id = (shift.company_id if shift else None) or user.company_id
    branch_id = shift.branch_id if shift else None
    source_id = _shift_source_wallet_id(db, shift.cashier or user, shift) if shift else None
    return _handover_wallet_options(db, company_id, source_id, branch_id, user.id)


def _active_branch_count(db: Session, company_id) -> int:
    from app.models.branch import Branch
    return db.query(func.count(Branch.id)).filter(
        Branch.company_id == company_id, Branch.is_active == True,  # noqa: E712
    ).scalar() or 0


@router.post("/open", status_code=201)
def open_shift(
    data: ShiftOpen,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ctx: BranchContext = Depends(get_branch_context),
):
    # Check if there's already an open shift for this cashier
    existing = db.query(Shift).filter(
        Shift.cashier_id == user.id, Shift.status == "open", Shift.company_id == user.company_id,  # T1.1: korxona filtri
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=SHIFT_ALREADY_OPEN)
    # T1.1: non-bypass xodim faqat o'z (joriy) filialida smena ochadi — korxonaning boshqa faol
    # filiali so'ralsa 403; begona/mavjud emas/nofaol filial esa resolve_tx_branch da 400 (T0.9).
    # Bypass uchun aniq filial header'dan ustun; korxonaga tegishliligi resolve_tx_branch da (400).
    if not ctx.bypass and data.branch_id and ctx.allowed_branch_ids is not None \
            and data.branch_id not in ctx.allowed_branch_ids \
            and company_branch_exists(db, data.branch_id, user.company_id):
        raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
    explicit_branch_id = data.branch_id or ctx.branch_id
    # T1.11: filial aniqlanmasa va 2+ faol filial bo'lsa — jim birinchi filialga tushmaydi, tanlash so'raladi
    if not explicit_branch_id and not user.branch_id and _active_branch_count(db, user.company_id) > 1:
        raise HTTPException(status_code=400, detail=SELECT_BRANCH)
    # T0.9 + T0.7: aniq berilgan filial shu korxonaniki va faol bo'lishi shart (validate_branch);
    # berilmasa user filiali → korxonaning birinchi faol filiali. Shift.branch_id hech qachon NULL emas.
    branch_id = resolve_tx_branch(db, user, explicit_branch_id=explicit_branch_id)

    # T1.11: kassa (ixtiyoriy) — shu korxona, faol va smena filialiga mos (T1.10 qoidasi)
    wallet = None
    if data.wallet_id:
        from app.models.moliya import Wallet
        wallet = db.query(Wallet).filter(
            Wallet.id == data.wallet_id, Wallet.company_id == user.company_id,
        ).first()
        if wallet is None:
            raise HTTPException(status_code=404, detail=WALLET_NOT_FOUND)
        if wallet.is_active is False:
            raise HTTPException(status_code=400, detail=WALLET_INACTIVE)
        if wallet.branch_id is not None and wallet.branch_id != branch_id:
            raise HTTPException(status_code=400, detail=WALLET_OTHER_BRANCH)
        assert_wallet_access(user, wallet, db)

    shift = Shift(
        cashier_id=user.id, branch_id=branch_id, opening_cash=data.opening_cash, company_id=user.company_id,
        wallet_id=wallet.id if wallet is not None else None, note_open=data.note or None,
    )
    db.add(shift)
    try:
        db.flush()
    except IntegrityError:
        # Parallel ikki ochish: bazadagi "bir kassirda bitta ochiq smena" indeksi ikkinchisini rad etadi
        db.rollback()
        raise HTTPException(status_code=400, detail=SHIFT_ALREADY_OPEN)
    from app.core.audit import log_action
    log_action(
        db, "SHIFT_OPEN", "shift", shift.id, user_id=user.id,
        new_values={"opening_cash": str(data.opening_cash), "cashier_id": user.id},
        company_id=shift.company_id, branch_id=shift.branch_id,
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=SHIFT_ALREADY_OPEN)
    db.refresh(shift)
    return {
        "id": shift.id,
        "cashier_id": shift.cashier_id,
        "branch_id": shift.branch_id,
        "branch_name": shift.branch.name if shift.branch else None,
        "wallet_id": shift.wallet_id,
        "opened_at": shift.opened_at,
        "status": shift.status,
    }


def _do_close_shift(db: Session, shift: Shift, data: ShiftClose, user: "User") -> dict:
    """
    Smena yopish logikasi — ikkala endpoint uchun umumiy funksiya.
    close_current_shift va close_shift ikkisi ham shu funksiyani chaqiradi.

    Inkassatsiya DAROMAD EMAS (T0.28): tushum sotuv vaqtida kassir kassasiga allaqachon
    yozilgan, shuning uchun smena yopilganda u kassalararo ichki harakat sifatida
    (`cash_handover`: transfer_out/transfer_in + CashTransfer) qabul qiluvchi kassaga
    ko'chiriladi. Inkassatsiya `Transaction` yozmaydi, jami pul o'zgarmaydi.

    T1.11: inkassatsiya SANALGAN summa bilan (`closing_cash - opening_cash`), kamomad/ortiqcha esa
    mustaqil `Transaction(shift_shortage|shift_surplus)` bo'lib filial P&L ida ko'rinadi.
    """
    from app.services.wallet_access import get_company_wallet
    from app.services import cash_handover
    from app.core.audit import log_action
    from app.models.moliya import Transaction

    if shift.status == "closed":
        raise HTTPException(status_code=400, detail=SHIFT_ALREADY_CLOSED)

    # Hamyonlar smena yopilishidan OLDIN korxona bo'yicha tekshiriladi:
    # begona yoki nofaol kassa bo'lsa 404 va smena ochiq qoladi
    shift_company_id = shift.company_id or user.company_id
    cash_target = get_company_wallet(db, data.wallet_id, shift_company_id)
    card_target = get_company_wallet(db, data.wallet_card_id, shift_company_id)

    # T1.11: tanlangan kassa smena filialiga mos bo'lishi shart (kassa filialsiz bo'lsa — mos)
    for _t in (cash_target, card_target):
        if _t is not None and not _branches_compatible(shift.branch_id, _t.branch_id):
            raise HTTPException(status_code=400, detail=WALLET_OTHER_BRANCH)

    cashier = shift.cashier or user
    source_id = _shift_source_wallet_id(db, cashier, shift) if (cash_target or card_target) else None
    source = get_company_wallet(db, source_id, shift_company_id, require_active=False)

    if source is not None:
        for target in (cash_target, card_target):
            if target is not None and target.id != source.id and not _branches_compatible(source.branch_id, target.branch_id):
                raise HTTPException(status_code=400, detail=HANDOVER_BRANCH_MISMATCH)

    # T1.10: boshqa filial / shaxsiy kassa tanlangan bo'lsa 403 (smena ochiq qoladi)
    for _t in (cash_target, card_target):
        if _t is not None:
            assert_wallet_access(user, _t, db)

    comp = _collect_shift_components(db, shift)
    cash_total, balances = comp["cash_total"], comp["balances"]

    # Kutilgan naqd va farq (kassir sanagan summa − kutilgan; manfiy = kamomad)
    expected_cash = comp["expected_cash"]
    opening_cash = Decimal(str(shift.opening_cash or 0))
    if data.closing_cash is not None:
        closing_cash = Decimal(str(data.closing_cash))
        cash_difference = closing_cash - expected_cash
        handover_uzs = max(Decimal("0"), closing_cash - opening_cash)   # sanalgan summa (boshlang'ich naqd kassada qoladi)
    else:
        closing_cash = expected_cash
        cash_difference = Decimal("0")
        handover_uzs = cash_total

    warnings: list = []
    handover: list = []
    handover_cash_amount = Decimal("0")

    try:
        if (cash_target or card_target) and source is None:
            warnings.append("Kassir kassasi aniqlanmadi: inkassatsiya bajarilmadi")
        elif source is not None:
            plan = []  # (maqsad kassa, to'lov turi, valyuta, so'ralgan miqdor)
            if cash_target is not None:
                for curr, amt in (balances.get("cash") or {}).items():
                    plan.append((cash_target, "cash", curr, handover_uzs if curr == "UZS" else amt))
            if card_target is not None:
                for p_type, curr_map in balances.items():
                    if p_type == "cash" or p_type in NON_CASH_PAYMENT_TYPES:
                        continue
                    for curr, amt in (curr_map or {}).items():
                        plan.append((card_target, p_type, curr, amt))

            cash_handover.lock_wallets(db, [source.id] + [t.id for t, *_ in plan])
            same_noted = set()
            for target, p_type, curr, requested in plan:
                requested = Decimal(str(requested or 0))
                if requested <= 0:
                    continue
                if target.id == source.id:
                    if target.id not in same_noted:
                        same_noted.add(target.id)
                        warnings.append(f"\"{target.name}\" kassir kassasi bilan bir xil: pul harakati yozilmadi")
                    continue
                net = max(cash_handover.kassa_net(db, source.id, p_type, curr), Decimal("0"))
                amount = min(requested, net)
                if amount < requested:
                    warnings.append(
                        f"{p_type} ({curr}): so'ralgan {requested} o'rniga kassadagi mavjud {amount} ko'chirildi"
                    )
                if amount <= 0:
                    continue
                cash_handover.transfer_between_wallets(
                    db, company_id=shift_company_id, source=source, target=target,
                    amount=amount, currency=curr, payment_type=p_type, user=user,
                    note=f"Smena #{shift.id} inkassatsiyasi", ref=f"Smena #{shift.id}",
                )
                handover.append({
                    "wallet_id": target.id, "payment_type": p_type,
                    "currency": curr, "amount": amount,
                })
                if p_type == "cash" and curr == "UZS":
                    handover_cash_amount += amount

        shift.closed_at = datetime.now(timezone.utc)
        shift.status = "closed"
        shift.expected_cash = expected_cash
        shift.closing_cash = closing_cash
        shift.cash_difference = cash_difference
        shift.closed_by = user.id
        shift.note_close = data.note or None
        if shift.wallet_id is None and source is not None:
            shift.wallet_id = source.id
        shift.handover_wallet_id = cash_target.id if cash_target is not None else None
        shift.handover_card_wallet_id = card_target.id if card_target is not None else None
        shift.handover_cash_amount = handover_cash_amount if cash_target is not None else None

        if cash_difference != 0:
            # T1.11: kamomad xarajat, ortiqcha kirim sifatida filial bo'yicha yoziladi (P&L da ko'rinadi).
            # Inkassatsiya yozuvlaridan mustaqil: reference_type "shift_shortage" / "shift_surplus".
            short = cash_difference < 0
            db.add(Transaction(
                company_id=shift_company_id, branch_id=shift.branch_id,
                type="expense" if short else "income", amount=abs(cash_difference),
                payment_type="cash", currency_code="UZS",
                reference_type="shift_shortage" if short else "shift_surplus", reference_id=shift.id,
                description=f"Smena #{shift.id} yopilishidagi {'kamomad' if short else 'ortiqcha'}",
                user_id=user.id,
            ))
            log_action(
                db, "SHIFT_CASH_DIFF", "shift", shift.id, user_id=user.id,
                new_values={
                    "expected_cash": str(expected_cash), "closing_cash": str(closing_cash),
                    "cash_difference": str(cash_difference), "cashier_id": shift.cashier_id,
                },
                company_id=shift.company_id, branch_id=shift.branch_id,
            )

        # T1.19: smena yopilishi har doim auditga yoziladi (kim yopdi, kutilgan/haqiqiy naqd, inkassatsiya)
        log_action(
            db, "SHIFT_CLOSE", "shift", shift.id, user_id=user.id,
            old_values={"status": "open"},
            new_values={
                "expected_cash": str(expected_cash), "closing_cash": str(closing_cash),
                "cash_difference": str(cash_difference), "cashier_id": shift.cashier_id,
                "handover": [
                    {"wallet_id": h.get("wallet_id"), "payment_type": h.get("payment_type"),
                     "currency": h.get("currency"), "amount": str(h.get("amount"))}
                    for h in handover
                ],
            },
            company_id=shift.company_id, branch_id=shift.branch_id,
        )

        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(shift)
    handed_over_other: dict = {}
    for h in handover:
        if h["payment_type"] == "cash" and h["currency"] == "UZS":
            continue
        key = h["payment_type"] if h["currency"] == "UZS" else f"{h['payment_type']}:{h['currency']}"
        handed_over_other[key] = handed_over_other.get(key, Decimal("0")) + h["amount"]
    return {
        "id": shift.id, "status": shift.status, "closed_at": shift.closed_at,
        "expected_cash": expected_cash, "closing_cash": closing_cash,
        "difference": cash_difference, "cash_difference": cash_difference,
        "handed_over_cash": handover_cash_amount, "handed_over_other": handed_over_other,
        "handover": handover, "warnings": warnings,
    }


def _lock_shift(db: Session, shift_id: int) -> Shift:
    """Smena qatorini `FOR UPDATE` bilan qayta o'qiydi (holat yangilanadi)."""
    return db.query(Shift).filter(Shift.id == shift_id).with_for_update().populate_existing().one()


def _hippo_z_close(factory_id: str):
    """Hippo Z-report yopish — background task. Xatolik smena yopishni to'xtatmaydi."""
    try:
        import logging
        from app.utils.hippo_client import hippo_client, HippoClientError
        hippo_client.post("/report/v1/z-report/close", {"factory_id": factory_id})
        logging.getLogger("hippo.shift").info("[Hippo] Z-report yopildi. factory_id=%s", factory_id)
    except Exception as exc:
        import logging
        logging.getLogger("hippo.shift").warning("[Hippo] Z-report yopishda xato: %s", exc)


def _schedule_hippo_z_close(background_tasks: BackgroundTasks, request: Request, db: Session, user: User, shift: Shift):
    """C4.1 (T3.18/T4.2): Z-report faqat HIPPO_SERVER_ENABLED bo'lsa va qurilma smena filialiga ruxsat etilgan bo'lsa."""
    from app.config import settings
    if not settings.HIPPO_SERVER_ENABLED:
        return
    factory_id = request.headers.get("X-Hippo-Factory-Id", "").strip()
    if not factory_id:
        return
    from app.routers.fiscal_devices import company_has_active_devices, device_allowed_for_branch
    if company_has_active_devices(db, shift.company_id) and not device_allowed_for_branch(
        db, shift.company_id, factory_id, shift.branch_id,
    ):
        import logging
        logging.getLogger("hippo.shift").warning(
            "[Hippo] Z-report o'tkazib yuborildi: qurilma smena filialiga ruxsat etilmagan. factory_id=%s shift_id=%s branch_id=%s",
            factory_id, shift.id, shift.branch_id,
        )
        return
    background_tasks.add_task(_hippo_z_close, factory_id)


@router.post("/close")
def close_current_shift(
    request: Request,
    background_tasks: BackgroundTasks,
    data: ShiftClose = ShiftClose(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Close the current user's active shift (no shift_id needed)."""
    shift = db.query(Shift).filter(
        Shift.cashier_id == user.id, Shift.status == "open", Shift.company_id == user.company_id,  # T1.1: korxona filtri
    ).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Faol smena topilmadi")
    # Parallel ikki yopish: qator qulflanadi, ikkinchisi "yopilgan" holatni ko'radi (400)
    shift = _lock_shift(db, shift.id)
    result = _do_close_shift(db, shift, data, user)
    # ── Hippo Z-report ──
    _schedule_hippo_z_close(background_tasks, request, db, user, shift)
    return result


@router.post("/{shift_id}/close")
def close_shift(
    shift_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    data: ShiftClose = ShiftClose(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    shift = db.get(Shift, shift_id)
    if not shift or (user.role.value != "super_admin" and shift.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Smena topilmadi")
    # super_admin/admin/director — har kimning smenasi; manager — o'z filiali smenasi; qolganlar — faqat o'zinikini
    if not _can_access_shift(db, user, shift):
        raise HTTPException(status_code=403, detail="Boshqa kassirning smenasini yopa olmaysiz")
    if shift.status == "closed":
        raise HTTPException(status_code=400, detail=SHIFT_ALREADY_CLOSED)
    shift = _lock_shift(db, shift.id)
    result = _do_close_shift(db, shift, data, user)
    # ── Hippo Z-report ──
    _schedule_hippo_z_close(background_tasks, request, db, user, shift)
    return result


def _get_visible_shift(db: Session, user: User, shift_id: int) -> Shift:
    shift = db.query(Shift).options(
        joinedload(Shift.cashier), joinedload(Shift.branch), joinedload(Shift.closer),
    ).filter(Shift.id == shift_id).first()
    if not shift or (_role(user) != UserRole.super_admin and shift.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Smena topilmadi")
    if not _can_access_shift(db, user, shift):
        raise HTTPException(status_code=403, detail=SHIFT_FORBIDDEN)
    return shift


def _nested_float(m: dict) -> dict:
    return {p: {c: float(a) for c, a in cm.items()} for p, cm in m.items()}


@router.get("/{shift_id}")
def get_shift(shift_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = _get_visible_shift(db, user, shift_id)
    return _shift_dict(shift)


@router.get("/{shift_id}/z-report")
def get_shift_z_report(shift_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Smena Z-hisoboti (ochiq smena uchun X-hisobot): sotuvlar, qaytarishlar, qarz to'lovlari va naqd hisobi."""
    shift = _get_visible_shift(db, user, shift_id)

    # Sotuvlar: bekor qilinmagan va qaytarish hujjati (R...) bo'lmagan
    sale_filter = (_shift_sale_filter(shift), Sale.status != "cancelled", ~is_return_doc())
    cnt, total_amount, discount_total = db.query(
        func.count(Sale.id), func.coalesce(func.sum(Sale.total_amount), 0),
        func.coalesce(func.sum(Sale.discount_amount), 0),
    ).filter(*sale_filter).one()
    pay_rows = db.query(
        SalePayment.payment_type,
        func.coalesce(Currency.code, 'UZS').label("currency"),
        func.sum(SalePayment.amount).label("total"),
    ).join(Sale, SalePayment.sale_id == Sale.id).outerjoin(Currency, Currency.id == Sale.currency_id).filter(
        *sale_filter,
    ).group_by(SalePayment.payment_type, Currency.code).all()
    sales_by_payment: dict = {}
    for r in pay_rows:
        sales_by_payment.setdefault(r.payment_type, {})[r.currency or 'UZS'] = Decimal(str(r.total))

    refunds = _refund_by_payment(db, shift)
    debts = _debt_payments_by_payment(db, shift)

    def _uzs(m: dict, ptype: str) -> Decimal:
        return m.get(ptype, {}).get("UZS", Decimal("0"))

    opening = Decimal(str(shift.opening_cash or 0))
    cash_sales = _uzs(sales_by_payment, "cash")
    returns_cash = _uzs(refunds["by_payment"], "cash")
    debt_cash = _uzs(debts, "cash")
    expected = shift.expected_cash if shift.expected_cash is not None else opening + cash_sales - returns_cash + debt_cash
    difference = shift.cash_difference
    return {
        "shift": _shift_dict(shift),
        "sales": {
            "count": int(cnt or 0),
            "total_amount": float(total_amount or 0),
            "discount_total": float(discount_total or 0),
            "by_payment": _nested_float(sales_by_payment),
        },
        "returns": {"count": refunds["count"], "by_payment": _nested_float(refunds["by_payment"])},
        "debt_payments": {"by_payment": _nested_float(debts)},
        "cash": {
            "opening": float(opening),
            "cash_sales": float(cash_sales),
            "returns_cash": float(returns_cash),
            "debt_cash": float(debt_cash),
            "expected": float(expected),
            "counted": _money(shift.closing_cash) if shift.status == "closed" else None,
            "difference": _money(difference),
            "shortage": float(max(Decimal("0"), -Decimal(str(difference)))) if difference is not None else None,
            "surplus": float(max(Decimal("0"), Decimal(str(difference)))) if difference is not None else None,
            "handed_over": _money(shift.handover_cash_amount),
        },
        "generated_at": datetime.now(timezone.utc),
    }
