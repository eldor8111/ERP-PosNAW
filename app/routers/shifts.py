"""
Shifts API: Manage cashier shifts.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from pydantic import BaseModel  # type: ignore
from decimal import Decimal
from datetime import datetime, timezone

from app.database import get_db  # type: ignore
from app.models.shift import Shift  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User  # type: ignore
from app.models.currency import Currency
from app.models.sale import Sale, SalePayment
from sqlalchemy import func, or_, and_

router = APIRouter(prefix="/shifts", tags=["shifts"])


def _shift_sale_filter(shift: "Shift"):
    """Sotuvni smenaga bog'lash sharti: yangi sotuvlar aniq shift_id orqali,
    eski (shift_id NULL) sotuvlar uchun avvalgi vaqt-oyna usuli zaxira."""
    return or_(
        Sale.shift_id == shift.id,
        and_(
            Sale.shift_id.is_(None),
            Sale.cashier_id == shift.cashier_id,
            Sale.created_at >= shift.opened_at,
        ),
    )


class ShiftOpen(BaseModel):
    branch_id: Optional[int] = None
    opening_cash: Decimal = Decimal("0")
    note: Optional[str] = None


class ShiftClose(BaseModel):
    closing_cash: Optional[Decimal] = None   # Kassir sanagan naqd pul
    wallet_id: Optional[int] = None          # Naqd tushadigan hamyon
    wallet_card_id: Optional[int] = None     # Plastik/Terminal tushadigan hamyon
    note: Optional[str] = None


ADMIN_ROLES = ("admin", "director")

@router.get("")
def list_shifts(
    branch_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Shift)
    if current_user.role.value != "super_admin":
        q = q.filter(Shift.company_id == current_user.company_id)
    # Non-admin: force filter to their own branch
    if current_user.role.value not in ADMIN_ROLES:
        if current_user.branch_id:
            q = q.filter(Shift.branch_id == current_user.branch_id)
    elif branch_id:
        q = q.filter(Shift.branch_id == branch_id)
    if status:
        q = q.filter(Shift.status == status)
    shifts = q.order_by(Shift.opened_at.desc()).all()
    return [
        {
            "id": s.id,
            "cashier_id": s.cashier_id,
            "cashier_name": s.cashier.name if s.cashier else None,
            "branch_id": s.branch_id,
            "opened_at": s.opened_at,
            "closed_at": s.closed_at,
            "opening_cash": s.opening_cash,
            "closing_cash": s.closing_cash,
            "status": s.status,
        }
        for s in shifts
    ]


@router.get("/current")
def get_current_shift(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Get the currently active (open) shift for the authenticated user, including totals."""
    shift = db.query(Shift).filter(Shift.cashier_id == user.id, Shift.status == "open").first()
    if not shift:
        return None
    
    # Calculate totals from sales during this shift per payment type
    payments = db.query(
        SalePayment.payment_type,
        func.coalesce(Currency.code, 'UZS').label("currency"),
        func.sum(SalePayment.amount).label("total")
    ).join(Sale, SalePayment.sale_id == Sale.id).outerjoin(Currency, Currency.id == Sale.currency_id).filter(
        _shift_sale_filter(shift),
        Sale.status != "cancelled"
    ).group_by(SalePayment.payment_type, Currency.code).all()

    balances_dec = {}
    total_sales_by_currency = {}
    for p in payments:
        ptype = p.payment_type
        curr = p.currency or 'UZS'
        if ptype not in balances_dec:
            balances_dec[ptype] = {}
        balances_dec[ptype][curr] = Decimal(str(p.total))
        total_sales_by_currency[curr] = float(total_sales_by_currency.get(curr, 0)) + float(p.total)

    # Qaytarishlar (-) va qarz to'lovlari (+) — kutilgan qoldiq real bo'lsin
    _apply_shift_adjustments(db, shift, balances_dec)

    balances = {
        ptype: {curr: str(amt) for curr, amt in curr_map.items()}
        for ptype, curr_map in balances_dec.items()
    }
    if "cash" not in balances:
        balances["cash"] = {}

    cash_uzs = balances_dec.get("cash", {}).get("UZS", Decimal("0"))
    expected_cash = shift.opening_cash + cash_uzs
    
    return {
        "id": shift.id,
        "cashier_id": shift.cashier_id,
        "cashier_name": shift.cashier.name if shift.cashier else None,
        "branch_id": shift.branch_id,
        "opened_at": shift.opened_at,
        "closed_at": shift.closed_at,
        "opening_cash": str(shift.opening_cash),
        "expected_cash": str(expected_cash),
        "balances": balances,
        "total_sales": total_sales_by_currency,
        "status": shift.status,
    }


@router.post("/open", status_code=201)
def open_shift(data: ShiftOpen, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Check if there's already an open shift for this cashier
    existing = db.query(Shift).filter(Shift.cashier_id == user.id, Shift.status == "open").first()
    if existing:
        raise HTTPException(status_code=400, detail="Kassir uchun faol smena allaqachon mavjud")
    # Auto-use user's branch if not explicitly provided
    branch_id = data.branch_id if data.branch_id is not None else user.branch_id
    shift = Shift(cashier_id=user.id, branch_id=branch_id, opening_cash=data.opening_cash, company_id=user.company_id)
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return {
        "id": shift.id,
        "cashier_id": shift.cashier_id,
        "branch_id": shift.branch_id,
        "opened_at": shift.opened_at,
        "status": shift.status,
    }


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
    from app.models.moliya import KassaMovement

    def _sub(ptype: str, curr: str, amt: Decimal):
        if amt <= 0:
            return
        if ptype not in balances:
            balances[ptype] = {}
        balances[ptype][curr] = balances[ptype].get(curr, Decimal("0")) - amt

    def _add(ptype: str, curr: str, amt: Decimal):
        if amt <= 0:
            return
        if ptype not in balances:
            balances[ptype] = {}
        balances[ptype][curr] = balances[ptype].get(curr, Decimal("0")) + amt

    # (a) Qaytarishlar. Faqat vazvrat HUJJATLARI (number 'R%') — to'liq
    # qaytarilgan original sotuvlar ham status=refunded bo'ladi, lekin
    # ularning paid_* qiymati kirim bo'lib qoladi (vazvrat hujjati ayiradi).
    refund_rows = db.query(
        Sale.payment_type,
        func.coalesce(Currency.code, 'UZS').label("currency"),
        func.coalesce(func.sum(Sale.paid_amount), 0).label("paid_total"),
        func.coalesce(func.sum(Sale.paid_cash), 0).label("cash_total"),
        func.coalesce(func.sum(Sale.paid_card), 0).label("card_total"),
    ).outerjoin(Currency, Currency.id == Sale.currency_id).filter(
        _shift_sale_filter(shift),
        Sale.status == "refunded",
        Sale.number.like("R%"),
    ).group_by(Sale.payment_type, Currency.code).all()

    for r in refund_rows:
        curr = r.currency or 'UZS'
        ptype = r.payment_type.value if hasattr(r.payment_type, 'value') else str(r.payment_type)
        if ptype == "mixed":
            _sub("cash", curr, Decimal(str(r.cash_total)))
            _sub("card", curr, Decimal(str(r.card_total)))
        elif ptype not in ("debt", "cashback"):
            _sub(ptype, curr, Decimal(str(r.paid_total)))

    # (b) Mijoz qarz to'lovlari — shu kassir qabul qilganlari.
    debt_rows = db.query(
        KassaMovement.payment_type,
        func.coalesce(KassaMovement.currency, 'UZS').label("currency"),
        func.coalesce(func.sum(KassaMovement.amount), 0).label("total"),
    ).filter(
        KassaMovement.created_by == shift.cashier_id,
        KassaMovement.created_at >= shift.opened_at,
        KassaMovement.reference_type == "customer_payment",
        KassaMovement.direction == "in",
    ).group_by(KassaMovement.payment_type, KassaMovement.currency).all()

    for r in debt_rows:
        ptype = r.payment_type or "cash"
        if ptype in ("debt", "cashback"):
            continue
        _add(ptype, r.currency or 'UZS', Decimal(str(r.total)))


def _calc_shift_payment_balances(db: Session, shift: Shift):
    """SalePayment jadvalidan smena davomidagi to'lovlarni hisoblaydi."""
    payments = db.query(
        SalePayment.payment_type,
        func.coalesce(Currency.code, 'UZS').label("currency"),
        func.sum(SalePayment.amount).label("total")
    ).join(Sale, SalePayment.sale_id == Sale.id).outerjoin(Currency, Currency.id == Sale.currency_id).filter(
        _shift_sale_filter(shift),
        Sale.status != "cancelled"
    ).group_by(SalePayment.payment_type, Currency.code).all()
    balances = {}
    for p in payments:
        ptype = p.payment_type
        curr = p.currency or 'UZS'
        if ptype not in balances:
            balances[ptype] = {}
        balances[ptype][curr] = Decimal(str(p.total))

    # Qaytarishlar (-) va qarz to'lovlari (+)
    _apply_shift_adjustments(db, shift, balances)

    cash_balances = balances.get("cash", {})
    cash_total = cash_balances.get("UZS", Decimal("0"))
    return cash_total, balances


def _do_close_shift(db: Session, shift: Shift, data: ShiftClose, user: "User") -> dict:
    """
    Smena yopish logikasi — ikkala endpoint uchun umumiy funksiya.
    close_current_shift va close_shift ikkisi ham shu funksiyani chaqiradi.
    """
    from app.models.moliya import Wallet, Transaction, WalletBalance

    cash_total, balances = _calc_shift_payment_balances(db, shift)

    shift.closed_at = datetime.now(timezone.utc)
    shift.closing_cash = data.closing_cash if data.closing_cash is not None else cash_total
    shift.status = "closed"

    # Naqd inkassatsiya
    if data.wallet_id and cash_total > 0:
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            wallet.balance = Decimal(str(wallet.balance or 0)) + cash_total
            wb = db.query(WalletBalance).filter(
                WalletBalance.wallet_id == wallet.id,
                WalletBalance.payment_type == "cash"
            ).first()
            if not wb:
                wb = WalletBalance(wallet_id=wallet.id, payment_type="cash", balance=cash_total)
                db.add(wb)
            else:
                wb.balance = Decimal(str(wb.balance or 0)) + cash_total

            db.add(Transaction(
                branch_id=shift.branch_id, company_id=shift.company_id,
                type="income", amount=cash_total, payment_type="cash",
                wallet_id=wallet.id, reference_type="shift", reference_id=shift.id,
                description=f"Smena yopilishi - inkassatsiya (Naqd, {user.name})"
            ))

    # Karta / Click / Humo / ... inkassatsiya
    if data.wallet_card_id:
        wallet_card = db.get(Wallet, data.wallet_card_id)
        if wallet_card:
            for p_type, curr_map in balances.items():
                if p_type == "cash":
                    continue
                # balances endi {ptype: {currency: Decimal}} tuzilmasida —
                # hamyon balansi UZS da yuritiladi, shu qismini olamiz.
                amount = curr_map.get("UZS", Decimal("0")) if isinstance(curr_map, dict) else Decimal(str(curr_map or 0))
                if amount <= 0:
                    continue
                wallet_card.balance = Decimal(str(wallet_card.balance or 0)) + amount
                wb = db.query(WalletBalance).filter(
                    WalletBalance.wallet_id == wallet_card.id,
                    WalletBalance.payment_type == p_type
                ).first()
                if not wb:
                    wb = WalletBalance(wallet_id=wallet_card.id, payment_type=p_type, balance=amount)
                    db.add(wb)
                else:
                    wb.balance = Decimal(str(wb.balance or 0)) + amount

                db.add(Transaction(
                    branch_id=shift.branch_id, company_id=shift.company_id,
                    type="income", amount=amount, payment_type=p_type,
                    wallet_id=wallet_card.id, reference_type="shift", reference_id=shift.id,
                    description=f"Smena yopilishi - inkassatsiya ({p_type}, {user.name})"
                ))

    db.commit()
    db.refresh(shift)
    return {"id": shift.id, "status": shift.status, "closed_at": shift.closed_at}


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


@router.post("/close")
def close_current_shift(
    request: Request,
    background_tasks: BackgroundTasks,
    data: ShiftClose = ShiftClose(),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Close the current user's active shift (no shift_id needed)."""
    shift = db.query(Shift).filter(Shift.cashier_id == user.id, Shift.status == "open").first()
    if not shift:
        raise HTTPException(status_code=404, detail="Faol smena topilmadi")
    result = _do_close_shift(db, shift, data, user)
    # ── Hippo Z-report ──
    factory_id = request.headers.get("X-Hippo-Factory-Id", "").strip()
    if factory_id:
        background_tasks.add_task(_hippo_z_close, factory_id)
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
    from app.models.user import UserRole
    if user.role not in (UserRole.super_admin, UserRole.admin, UserRole.director):
        if shift.cashier_id != user.id:
            raise HTTPException(status_code=403, detail="Boshqa kassirning smenasini yopa olmaysiz")
    if shift.status == "closed":
        raise HTTPException(status_code=400, detail="Smena allaqachon yopilgan")
    result = _do_close_shift(db, shift, data, user)
    # ── Hippo Z-report ──
    factory_id = request.headers.get("X-Hippo-Factory-Id", "").strip()
    if factory_id:
        background_tasks.add_task(_hippo_z_close, factory_id)
    return result


@router.get("/{shift_id}")
def get_shift(shift_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    shift = db.get(Shift, shift_id)
    if not shift or (user.role.value != "super_admin" and shift.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Not found")
    return shift
