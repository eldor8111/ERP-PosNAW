"""T3.18: filial to'lov terminallari (Payme, Click, Uzum, Uzcard, Humo) — ichki yozuv.

Provayder bilan haqiqiy integratsiya (webhook, sirli kalitlar) bu yerda YO'Q: terminal faqat filial/kassa bilan
bog'lanadi, sotuvdagi to'lov (`SalePayment`) esa terminal va provayder tranzaksiya raqami (`reference`) bilan
yoziladi. Shu raqamlar `payment_reconciliation` orqali provayder ko'chirmasi (CSV) bilan solishtiriladi."""
from decimal import Decimal
from types import SimpleNamespace
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.branch_context import build_branch_context
from app.core.dependencies import require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.moliya import Wallet
from app.models.payment_terminal import PaymentTerminal
from app.models.user import User, UserRole

router = APIRouter(prefix="/payment-terminals", tags=["Payment terminals"])

ADMIN_ROLES = (UserRole.admin, UserRole.director)
POS_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier)

# Tranzaksiya raqami (reference) talab qilinishi mumkin bo'lgan onlayn provayderlar
REFERENCE_PROVIDERS = ("click", "payme", "uzum")

TERMINAL_NOT_FOUND = "Terminal topilmadi"
REFERENCE_REQUIRED = "Tranzaksiya raqamini kiriting"

Provider = Literal["payme", "click", "uzum", "uzcard", "humo"]


class PaymentTerminalIn(BaseModel):
    provider: Provider
    branch_id: Optional[int] = None
    wallet_id: Optional[int] = None
    label: Optional[str] = Field(None, max_length=100)
    merchant_id: Optional[str] = Field(None, max_length=64)
    terminal_id: Optional[str] = Field(None, max_length=64)
    require_reference: bool = True
    is_active: bool = True


class PaymentTerminalUpdate(BaseModel):
    provider: Optional[Provider] = None
    branch_id: Optional[int] = None    # model_fields_set da bo'lsa o'zgaradi (None = butun korxona)
    wallet_id: Optional[int] = None    # model_fields_set da bo'lsa o'zgaradi (None = kassa biriktirilmagan)
    label: Optional[str] = Field(None, max_length=100)
    merchant_id: Optional[str] = Field(None, max_length=64)
    terminal_id: Optional[str] = Field(None, max_length=64)
    require_reference: Optional[bool] = None
    is_active: Optional[bool] = None


class PaymentTerminalOut(BaseModel):
    id: int
    provider: str
    branch_id: Optional[int] = None
    wallet_id: Optional[int] = None
    label: Optional[str] = None
    merchant_id: Optional[str] = None
    terminal_id: Optional[str] = None
    require_reference: bool
    is_active: bool

    model_config = {"from_attributes": True}


def _require_company(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def _check_branch(db: Session, cid: int, branch_id: Optional[int]) -> None:
    if branch_id is None:
        return
    if not db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first():
        raise HTTPException(status_code=404, detail="Filial topilmadi")


def _check_wallet(db: Session, cid: int, wallet_id: Optional[int]) -> None:
    if wallet_id is None:
        return
    if not db.query(Wallet.id).filter(Wallet.id == wallet_id, Wallet.company_id == cid).first():
        raise HTTPException(status_code=404, detail="Kassa topilmadi")


def _get_own(db: Session, cid: int, terminal_id: int) -> PaymentTerminal:
    t = db.query(PaymentTerminal).filter(PaymentTerminal.id == terminal_id, PaymentTerminal.company_id == cid).first()
    if not t:
        raise HTTPException(status_code=404, detail=TERMINAL_NOT_FOUND)
    return t


def _clean(v: Optional[str]) -> Optional[str]:
    return (v or "").strip() or None


def user_terminal_query(db: Session, user: User):
    """Foydalanuvchi ko'ra oladigan faol terminallar: o'z korxonasi, o'z filiali(lari) yoki butun korxona."""
    q = db.query(PaymentTerminal).filter(
        PaymentTerminal.company_id == user.company_id, PaymentTerminal.is_active == True,  # noqa: E712
    )
    ids = build_branch_context(db, user, None).scope_ids()
    if ids is not None:
        q = q.filter(or_(PaymentTerminal.branch_id.is_(None), PaymentTerminal.branch_id.in_(list(ids))))
    return q


# ── Sotuv bilan integratsiya (sales.py chaqiradi) ─────────────────────────────

def _provider_payment_items(data) -> list:
    """Sotuvdagi to'lov qatorlari: `payments[]`, bo'sh bo'lsa `paid_click/payme/uzum` maydonlari (reference'siz)."""
    items = list(getattr(data, "payments", None) or [])
    if items:
        return items
    legacy = []
    for field, ptype in (("paid_click", "click"), ("paid_payme", "payme"), ("paid_uzum", "uzum")):
        if (getattr(data, field, None) or Decimal("0")) > 0:
            legacy.append(SimpleNamespace(type=SimpleNamespace(value=ptype), reference=None, terminal_id=None))
    return legacy


def validate_sale_payment_terminals(db: Session, user: User, data, branch_id: Optional[int]) -> None:
    """Sotuv yaratilishidan OLDIN: `terminal_id` korxona/filialga tegishliligi va majburiy tranzaksiya raqami.

    - `terminal_id` berilsa: shu korxonaning faol terminali, butun korxonaniki yoki sotuv filialiniki
      (aks holda 404), provayderi to'lov turiga mos bo'lishi shart (aks holda 400).
    - click/payme/uzum to'lovida: `terminal_id` berilgan bo'lsa shu terminalning `require_reference` i,
      berilmasa shu filial/provayder uchun faol `require_reference` terminal bor-yo'qligi bo'yicha
      `reference` majburiy (400). Terminal bo'lmasa tekshiruv yo'q (orqaga moslik).
    """
    cid = user.company_id
    for p in _provider_payment_items(data):
        ptype = p.type.value
        term = None
        if p.terminal_id is not None:
            term = db.query(PaymentTerminal).filter(
                PaymentTerminal.id == p.terminal_id, PaymentTerminal.company_id == cid,
                PaymentTerminal.is_active == True,  # noqa: E712
            ).first()
            if term is None or (term.branch_id is not None and term.branch_id != branch_id):
                raise HTTPException(status_code=404, detail=TERMINAL_NOT_FOUND)
            if term.provider != ptype:
                raise HTTPException(status_code=400, detail="Terminal to'lov turiga mos kelmaydi")
        if ptype not in REFERENCE_PROVIDERS:
            continue
        if term is not None:
            need = bool(term.require_reference)
        else:
            q = db.query(PaymentTerminal.id).filter(
                PaymentTerminal.company_id == cid, PaymentTerminal.provider == ptype,
                PaymentTerminal.is_active == True, PaymentTerminal.require_reference == True,  # noqa: E712
            )
            if branch_id is not None:
                q = q.filter(or_(PaymentTerminal.branch_id.is_(None), PaymentTerminal.branch_id == branch_id))
            else:
                q = q.filter(PaymentTerminal.branch_id.is_(None))
            need = q.first() is not None
        if need and not (p.reference or "").strip():
            raise HTTPException(status_code=400, detail=REFERENCE_REQUIRED)


def attach_payment_references(db: Session, sale, data) -> None:
    """Sotuv yaratilgach: `payments[].reference/terminal_id` ni mos `SalePayment` qatoriga yozadi
    (tur + UZS summa bo'yicha moslashtiriladi). Hech narsa o'zgarmasa commit qilmaydi."""
    items = [p for p in (getattr(data, "payments", None) or []) if (p.reference or "").strip() or p.terminal_id is not None]
    if not items:
        return
    rows = sorted(sale.payments, key=lambda r: r.id)
    used = set()
    changed = False
    for p in items:
        ptype = p.type.value
        amt = Decimal(str(p.amount)) * Decimal(str(p.rate or 1))
        for r in rows:
            if r.id in used or r.payment_type != ptype:
                continue
            if abs(Decimal(str(r.amount or 0)) - amt) <= Decimal("0.02"):
                r.reference = (p.reference or "").strip() or None
                r.terminal_id = p.terminal_id
                used.add(r.id)
                changed = True
                break
    if changed:
        db.commit()


# ── Endpointlar ───────────────────────────────────────────────────────────────

@router.get("/mine", response_model=List[PaymentTerminalOut])
def my_payment_terminals(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*POS_ROLES)),
):
    """Kassir uchun: faqat o'z filiali (va butun korxonaga ochiq) faol terminallar."""
    _require_company(user)
    return user_terminal_query(db, user).order_by(PaymentTerminal.provider, PaymentTerminal.id).all()


@router.get("", response_model=List[PaymentTerminalOut])
def list_payment_terminals(
    branch_id: Optional[int] = Query(None),
    provider: Optional[Provider] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    q = db.query(PaymentTerminal).filter(PaymentTerminal.company_id == cid)
    if branch_id is not None:
        _check_branch(db, cid, branch_id)
        q = q.filter(PaymentTerminal.branch_id == branch_id)
    if provider:
        q = q.filter(PaymentTerminal.provider == provider)
    return q.order_by(PaymentTerminal.id).all()


@router.post("", response_model=PaymentTerminalOut, status_code=201)
def create_payment_terminal(
    data: PaymentTerminalIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    _check_branch(db, cid, data.branch_id)
    _check_wallet(db, cid, data.wallet_id)
    if data.merchant_id and db.query(PaymentTerminal.id).filter(
        PaymentTerminal.company_id == cid, PaymentTerminal.provider == data.provider,
        PaymentTerminal.merchant_id == data.merchant_id.strip(),
        PaymentTerminal.terminal_id == _clean(data.terminal_id),
    ).first():
        raise HTTPException(status_code=409, detail="Bunday terminal allaqachon mavjud")
    t = PaymentTerminal(
        company_id=cid, branch_id=data.branch_id, wallet_id=data.wallet_id, provider=data.provider,
        label=_clean(data.label), merchant_id=_clean(data.merchant_id), terminal_id=_clean(data.terminal_id),
        require_reference=data.require_reference, is_active=data.is_active,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.put("/{terminal_id}", response_model=PaymentTerminalOut)
def update_payment_terminal(
    terminal_id: int,
    data: PaymentTerminalUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    t = _get_own(db, cid, terminal_id)
    fields = data.model_fields_set
    if "provider" in fields and data.provider is not None:
        t.provider = data.provider
    if "branch_id" in fields:
        _check_branch(db, cid, data.branch_id)
        t.branch_id = data.branch_id
    if "wallet_id" in fields:
        _check_wallet(db, cid, data.wallet_id)
        t.wallet_id = data.wallet_id
    if "label" in fields:
        t.label = _clean(data.label)
    if "merchant_id" in fields:
        t.merchant_id = _clean(data.merchant_id)
    if "terminal_id" in fields:
        t.terminal_id = _clean(data.terminal_id)
    if "require_reference" in fields and data.require_reference is not None:
        t.require_reference = data.require_reference
    if "is_active" in fields and data.is_active is not None:
        t.is_active = data.is_active
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{terminal_id}")
def delete_payment_terminal(
    terminal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    cid = _require_company(user)
    t = _get_own(db, cid, terminal_id)
    db.delete(t)   # sale_payments.terminal_id -> NULL (FK ondelete SET NULL); reference saqlanib qoladi
    db.commit()
    return {"ok": True}
