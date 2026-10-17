from datetime import datetime, timezone, date
from typing import Optional, List
from decimal import Decimal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator

from app.database import get_db
from app.core.dependencies import get_current_user, require_module_roles, require_roles
from app.models.user import UserRole
from app.services.tenant_guards import validate_branch
from app.services.wallet_access import user_can_use_wallet
from app.services.wallet_resolver import (
    assert_wallet_access, wallet_meta, validate_wallet_branch,
)
from app.services import cash_service, wallet_service
from app.services import approval_service, expense_service  # T4.6: xarajat limiti va tasdiqlash
from app.utils.report_utils import date_bounds
from app.core.audit import log_action, log_action_for
from app.models.moliya import (
    Wallet, KassaSession, KassaMovement, ExpenseCategory,
    Expense, Transaction, PAYMENT_TYPES, CashTransfer
)

# T0.5: butun router — admin/director/accountant (+ permissions.kassa == False bo'lsa 403).
# Pul chiqim/kirim va sozlash amallari alohida faqat admin/director (_ADMIN_ONLY).
router = APIRouter(
    prefix="/kassa",
    tags=["Kassa"],
    dependencies=[Depends(require_module_roles("kassa", UserRole.admin, UserRole.director, UserRole.accountant))],
)
_ADMIN_ONLY = [Depends(require_roles(UserRole.admin, UserRole.director))]


def _can_see_voided(user) -> bool:
    """T1.19: bekor qilingan (void) yozuvlarni faqat admin/director ko'ra oladi (include_voided=true)."""
    return user.role in (UserRole.admin, UserRole.director, UserRole.super_admin)

# ─── Schemas ─────────────────────────────────────────────────────────────────

class WalletCreate(BaseModel):
    name: str
    type: str = "cash"
    currency: str = "UZS"
    branch_id: Optional[int] = None
    opening_balance: float = 0

class WalletUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    # T1.10: filialga bog'lash; yuborilsa va null bo'lsa — umumiy (filialsiz) kassa
    branch_id: Optional[int] = None

class OpenKassaIn(BaseModel):
    opening_balance: float = 0
    currency: str = "UZS"
    note: Optional[str] = None

class CloseKassaIn(BaseModel):
    # Example format: {"cash": {"UZS": 50000, "USD": 100}, "card": {"UZS": 120000}}
    actual_amounts: dict  
    note: Optional[str] = None

class TransferLineIn(BaseModel):
    # T0.35: summa musbat (Decimal, 2 xona), valyuta — 3 harfli kod, to'lov turi — PAYMENT_TYPES ichida
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field("UZS", pattern=r"^[A-Z]{3}$")
    payment_type: str = "cash"

    @field_validator("payment_type")
    @classmethod
    def _check_payment_type(cls, v: str) -> str:
        if v not in PAYMENT_TYPES:
            raise ValueError("To'lov turi noto'g'ri")
        return v

class TransferOutIn(TransferLineIn):
    receiver_wallet_id: int
    note: Optional[str] = None

class TransferOutBatchIn(BaseModel):
    receiver_wallet_id: int
    note: Optional[str] = None
    lines: List[TransferLineIn] = Field(min_length=1, max_length=50)

class TransferStatusIn(BaseModel):
    transfer_id: int

class InvestIn(BaseModel):
    amount: float
    payment_type: str = "cash"
    currency: str = "UZS"
    description: Optional[str] = None

class WithdrawIn(BaseModel):
    amount: float
    payment_type: str = "cash"
    currency: str = "UZS"
    description: Optional[str] = None

class ExpenseCategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ExpenseCreate(BaseModel):
    wallet_id: int
    category_id: int
    amount: float
    payment_type: str = "cash"
    currency: str = "UZS"
    description: Optional[str] = None

class ExpenseUpdate(BaseModel):
    category_id: Optional[int] = None
    amount: Optional[float] = None
    payment_type: Optional[str] = None
    currency: Optional[str] = None
    description: Optional[str] = None

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _balances_from_rows(rows) -> dict:
    """`(payment_type, currency, direction, sum)` qatorlaridan balans lug'ati.

    Kalitlar: avval PAYMENT_TYPES (harakati bo'lmasa ham bo'sh ro'yxat), so'ng bazada
    uchragan boshqa turlar — noma'lum tur balansdan yo'qolmasin (T0.29)."""
    # {payment_type: {currency: balans}}
    acc: dict = {}
    for ptype, currency, direction, amount in rows:
        if ptype is None:
            continue
        value = float(amount or 0)
        by_curr = acc.setdefault(ptype, {})
        sign = 1 if direction == "in" else (-1 if direction == "out" else 0)
        by_curr[currency] = by_curr.get(currency, 0.0) + sign * value

    ordered = list(PAYMENT_TYPES) + sorted(k for k in acc if k not in PAYMENT_TYPES and k != "total")
    result = {}
    total = {}
    for ptype in ordered:
        currency_balances = []
        for currency, balance in acc.get(ptype, {}).items():
            if balance != 0:
                currency_balances.append({"currency": currency, "value": balance})
                # Total hisoblash (barcha valyutalar bo'yicha alohida)
                total[currency] = total.get(currency, 0) + balance
        result[ptype] = currency_balances

    result["total"] = [{"currency": k, "value": v} for k, v in total.items() if v != 0]
    return result


def get_kassa_balances_bulk(db: Session, wallet_ids) -> dict:
    """Bir nechta kassa balansi — BITTA `GROUP BY (wallet_id, payment_type, currency, direction)` so'rovi
    (so'rovlar soni kassalar, to'lov turlari va valyutalar soniga bog'liq emas, T2.8).
    Qaytaradi: `{wallet_id: get_kassa_balances natijasi}` (harakati yo'q kassa uchun bo'sh balans)."""
    ids = sorted({int(i) for i in wallet_ids if i is not None})
    if not ids:
        return {}
    rows = db.query(
        KassaMovement.wallet_id,
        KassaMovement.payment_type,
        KassaMovement.currency,
        KassaMovement.direction,
        func.sum(KassaMovement.amount),
    ).filter(
        KassaMovement.wallet_id.in_(ids)
    ).group_by(
        KassaMovement.wallet_id, KassaMovement.payment_type, KassaMovement.currency, KassaMovement.direction
    ).all()
    per_wallet: dict = {wid: [] for wid in ids}
    for wid, ptype, currency, direction, amount in rows:
        per_wallet[wid].append((ptype, currency, direction, amount))
    return {wid: _balances_from_rows(per_wallet[wid]) for wid in ids}


def get_kassa_balances(wallet_id: int, db: Session) -> dict:
    """Har bir payment_type uchun valyutalar bo'yicha balans hisoblash (bitta kassa uchun `get_kassa_balances_bulk`
    ning o'rami — bitta GROUP BY so'rovi)."""
    return get_kassa_balances_bulk(db, [wallet_id]).get(wallet_id) or _balances_from_rows([])


def open_session_ids(db: Session, wallet_ids) -> dict:
    """`{wallet_id: ochiq sessiya id}` — bitta so'rov."""
    ids = [i for i in wallet_ids if i is not None]
    if not ids:
        return {}
    rows = db.query(KassaSession.wallet_id, func.min(KassaSession.id)).filter(
        KassaSession.wallet_id.in_(ids), KassaSession.status == "open",
    ).group_by(KassaSession.wallet_id).all()
    return {wid: sid for wid, sid in rows}


def wallet_out(wallet, db, current_user, meta=None, balances=None, session_id=...):
    """Kassa javobi. Ro'yxatda `balances` va `session_id` oldindan bulk hisoblanib beriladi (N+1 yo'q);
    `session_id=...` (berilmagan) bo'lsa alohida so'raladi."""
    if balances is None:
        balances = get_kassa_balances(wallet.id, db)
    if meta is None:
        meta = wallet_meta(db, current_user, [wallet]).get(wallet.id, {})
    if session_id is ...:
        session_id = open_session_ids(db, [wallet.id]).get(wallet.id)
    return {
        "id": wallet.id,
        "name": wallet.name,
        "type": wallet.type,
        "is_active": wallet.is_active,
        "is_open": wallet.is_open,
        "company_id": wallet.company_id,
        "branch_id": wallet.branch_id,
        "branch_name": meta.get("branch_name"),
        "is_personal": meta.get("is_personal", bool(getattr(wallet, "is_personal", False))),
        "is_default_for_me": meta.get("is_default_for_me", False),
        "is_default": bool(meta.get("is_default_for_me", False)),
        "opening_balance": float(wallet.opening_balance or 0),
        "opened_at": wallet.opened_at,
        "closed_at": wallet.closed_at,
        "created_at": wallet.created_at,
        "balances": balances,
        "session_id": session_id,
    }


# ─── Foydalanuvchi ↔ Kassa ───────────────────────────────────────────────────
# T0.4: /kassa/user-wallets va /kassa/assign-wallet (GET/POST/DELETE) o'chirildi — ular
# /users/{id}/wallets... ning tekshiruvsiz dublikati edi (rol va korxona tekshiruvi yo'q).
# Foydalanuvchi-kassa biriktirish faqat app/routers/users.py orqali.


# ─── Xarajat kategoriyalari (FIXED PATHS — oldin yoziladi!) ──────────────────

@router.get("/categories")
def list_expense_categories(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # T2.2: Moliya sahifasi bilan bitta manba - faqat shu korxona kategoriyalari (umumiy NULL qatorlarsiz)
    from app.routers.finance import company_expense_categories
    cats = company_expense_categories(db, current_user.company_id)
    return [{"id": c.id, "name": c.name, "description": c.description} for c in cats]


@router.post("/categories")
def create_expense_category(data: ExpenseCategoryCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    # T2.2: nom takrorlansa 409 (Moliya sahifasi bilan bir xil qoida)
    from app.routers.finance import create_company_category
    cat = create_company_category(db, current_user.company_id, data.name, data.description)
    db.commit()
    db.refresh(cat)
    return {"id": cat.id, "name": cat.name, "description": cat.description}


def _expense_category_or_404(db: Session, category_id: int, company_id: int) -> ExpenseCategory:
    """Kategoriya shu korxonaniki (yoki umumiy NULL) bo'lishi shart, aks holda 404 (begona resurs ko'rinmaydi)."""
    cat = db.query(ExpenseCategory).filter(
        ExpenseCategory.id == category_id,
        (ExpenseCategory.company_id == company_id) | (ExpenseCategory.company_id.is_(None)),
    ).first()
    if not cat:
        raise HTTPException(404, "Kategoriya topilmadi")
    return cat


CLOSED_SESSION_LOCKED = "Yopilgan kassa sessiyasidagi yozuvni o'zgartirib bo'lmaydi"


def _assert_expense_session_open(db: Session, expense_id: int) -> None:
    """T1.11: xarajatning kassa harakati YOPILGAN kassa sessiyasiga tegishli bo'lsa — 409
    (yopilgan kun raqamlari keyin o'zgartirilmasin)."""
    closed = db.query(KassaMovement.id).join(
        KassaSession, KassaSession.id == KassaMovement.session_id,
    ).filter(
        KassaMovement.reference_type == "expense",
        KassaMovement.reference_id == expense_id,
        KassaSession.status == "closed",
    ).first()
    if closed:
        raise HTTPException(status_code=409, detail=CLOSED_SESSION_LOCKED)


@router.post("/do-expense")
def create_expense(data: ExpenseCreate, background_tasks: BackgroundTasks, response: Response,
                   db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == data.wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    if data.amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")
    # T2.2: kategoriya korxonaga tekshiriladi; filial - yagona qoida: kassa filiali -> xodim filiali ->
    # korxonaning asosiy/birinchi faol filiali (T1.4, T1.12); hech biri bo'lmasa 400
    cat = _expense_category_or_404(db, data.category_id, current_user.company_id)
    from app.services.branch_attribution import resolve_money_branch_id
    from app.services.currency_service import get_rate, require_active_currency
    branch_id = resolve_money_branch_id(db, current_user, wallet=w)
    # T2.7: valyuta korxonada faol bo'lishi shart; kurs va UZS ekvivalent xarajatda saqlanadi
    currency = require_active_currency(db, current_user.company_id, data.currency)
    rate = get_rate(db, current_user.company_id, currency)
    # T4.6: yagona xarajat mantiqi (limit tekshiruvi, created_by/approved_by, T2.8 `post_cash`). Limitdan katta
    # xarajat `pending` bo'ladi: KassaMovement, Transaction va Wallet.balance tasdiqdan keyin yoziladi.
    exp, req = expense_service.create_expense(
        db, user=current_user, wallet=w, branch_id=branch_id, category_id=data.category_id,
        category_name=cat.name if cat else None, amount=data.amount, currency=currency, rate=rate,
        description=data.description, payment_type=data.payment_type,
    )
    log_action_for(
        db, current_user, "EXPENSE_CREATE", "expense", exp.id,
        new_values={"wallet_id": data.wallet_id, "category_id": data.category_id, "amount": float(data.amount),
                    "payment_type": data.payment_type, "currency": currency, "description": data.description,
                    "status": exp.status},
        branch_id=branch_id,
    )
    db.commit()
    if req is not None:
        # Javobdan keyin: menejer/direktorga tugmali Telegram xabari va push
        background_tasks.add_task(approval_service.notify_approvers_by_id, req.id)
        response.status_code = 202
        return {"ok": True, "status": "pending", "expense_id": exp.id, "approval_request_id": req.id}
    return {"ok": True, "expense_id": exp.id}


@router.put("/expense/{expense_id}", dependencies=_ADMIN_ONLY)
def update_expense(expense_id: int, data: ExpenseUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    exp = db.query(Expense).execution_options(include_unapproved_expenses=True).filter(
        Expense.id == expense_id, Expense.company_id == current_user.company_id, Expense.voided_at.is_(None),
    ).first()
    if not exp:
        raise HTTPException(404, "Xarajat topilmadi")
    _assert_expense_session_open(db, exp.id)
    old_values = {"category_id": exp.category_id, "amount": float(exp.amount or 0), "description": exp.description}
    # T4.6: tasdiq kutayotgan/rad etilgan xarajatda pul yozuvi yo'q — o'zgartirish tasdiq oqimini buzadi
    if exp.status != "approved":
        raise HTTPException(409, "Tasdiq kutayotgan yoki rad etilgan xarajatni o'zgartirib bo'lmaydi")
    # T4.6: summa oshirilsa limit qayta tekshiriladi (tahrirda tasdiq oqimi yo'q: oshsa 403)
    if data.amount is not None and Decimal(str(data.amount)) > Decimal(str(exp.amount or 0)):
        _v = approval_service.evaluate_expense(
            db, current_user, exp.branch_id, Decimal(str(data.amount)) * Decimal(str(exp.exchange_rate or 1)),
        )
        if _v is not None:
            raise HTTPException(403, detail=_v.detail("limit_exceeded"))

    w = db.query(Wallet).filter(Wallet.id == exp.wallet_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")

    # T2.7: eski summani hamyonga qaytarish faqat UZS xarajat uchun (valyutali xarajat Wallet.balance ga tegmagan)
    from app.services.currency_service import get_rate, norm_code, require_active_currency
    if norm_code(exp.currency) == "UZS":
        w.balance = Decimal(str(w.balance or 0)) + Decimal(str(exp.amount))

    # Update Expense fields
    if data.category_id is not None:
        _expense_category_or_404(db, data.category_id, current_user.company_id)
        exp.category_id = data.category_id
    if data.amount is not None:
        if data.amount <= 0:
            raise HTTPException(400, "Summa musbat bo'lishi kerak")
        exp.amount = data.amount
    if data.description is not None:
        exp.description = data.description
    # T2.7: valyuta o'zgarsa kurs qayta olinadi; faqat summa o'zgarsa saqlangan kurs qoladi (kurs yo'q bo'lsa — joriy)
    new_currency = norm_code(exp.currency)
    if data.currency is not None:
        new_currency = require_active_currency(db, current_user.company_id, data.currency)
    if new_currency != norm_code(exp.currency) or exp.exchange_rate is None:
        exp.exchange_rate = get_rate(db, current_user.company_id, new_currency)
    exp.currency = new_currency
    exp.amount_uzs = (Decimal(str(exp.amount)) * Decimal(str(exp.exchange_rate))).quantize(Decimal("0.01"))

    # Find category name for description fallback
    cat_name = "Xarajat"
    if exp.category_id:
        cat = db.get(ExpenseCategory, exp.category_id)
        if cat:
            cat_name = cat.name

    desc = exp.description or cat_name

    # Yangi summani hamyonga qo'llash — faqat UZS xarajat uchun
    if exp.currency == "UZS":
        w.balance = Decimal(str(w.balance or 0)) - Decimal(str(exp.amount))

    # Update related KassaMovement
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense", KassaMovement.reference_id == exp.id).first()
    if mv:
        if data.amount is not None:
            mv.amount = exp.amount
        if data.payment_type is not None:
            mv.payment_type = data.payment_type
        if data.currency is not None:
            mv.currency = exp.currency
        mv.description = desc

    # Update related Transaction
    tx = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == exp.id).first()
    if tx:
        if data.amount is not None:
            tx.amount = exp.amount
        if data.payment_type is not None:
            tx.payment_type = data.payment_type
        if data.currency is not None:
            tx.currency_code = exp.currency
        tx.description = desc

    log_action_for(
        db, current_user, "EXPENSE_UPDATE", "expense", exp.id,
        old_values=old_values,
        new_values={"category_id": exp.category_id, "amount": float(exp.amount or 0), "description": exp.description,
                    "payment_type": data.payment_type, "currency": exp.currency},
        branch_id=exp.branch_id,
    )
    db.commit()
    return {"ok": True, "message": "Xarajat yangilandi"}


@router.delete("/expense/{expense_id}", dependencies=_ADMIN_ONLY)
def delete_expense(expense_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Xarajatni bekor qilish (void). T1.19: yozuvlar bazadan o'chirilmaydi — `Expense.voided_at/voided_by`
    qo'yiladi, kassaga teskari `in` harakat (reference_type="expense_void") yoziladi, hamyon balansi qaytariladi."""
    exp = db.query(Expense).execution_options(include_unapproved_expenses=True).filter(
        Expense.id == expense_id, Expense.company_id == current_user.company_id,
    ).first()
    if not exp:
        raise HTTPException(404, "Xarajat topilmadi")
    if exp.voided_at is not None:
        raise HTTPException(400, "Xarajat allaqachon bekor qilingan")
    _assert_expense_session_open(db, exp.id)

    # T4.6: tasdiq kutayotgan/rad etilgan xarajatda pul yozuvi yo'q — balansga teskari yozuv KERAK EMAS
    if exp.status != "approved":
        _old_status = exp.status
        expense_service.cancel_pending_expense(db, exp, current_user)
        exp.voided_at = datetime.now(timezone.utc)
        exp.voided_by = current_user.id
        log_action_for(
            db, current_user, "EXPENSE_VOID", "expense", exp.id,
            old_values={"status": _old_status, "amount": float(exp.amount or 0)}, new_values={"voided": True},
            branch_id=exp.branch_id,
        )
        db.commit()
        return {"ok": True, "message": "Xarajat bekor qilindi"}

    now = datetime.now(timezone.utc)
    cid = current_user.company_id

    void_note = f"Xarajat bekor qilindi (ID: {exp.id})"
    w = db.query(Wallet).filter(Wallet.id == exp.wallet_id).first()
    # Revert expense amount to wallet balance (T2.7: valyutali xarajat Wallet.balance ga tegmagan)
    cash_service.apply_wallet_balance(w, "in", exp.amount, exp.currency)

    # Asl KassaMovement o'chirilmaydi — teskari kirim harakati yoziladi (kassa balansi shundan hisoblanadi)
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense", KassaMovement.reference_id == exp.id).first()
    if mv:
        cash_service.reverse_movement(db, mv, current_user, "expense_void", exp.id, void_note)

    # Asl Transaction va teskari (income) yozuv — ikkalasi ham voided: hisobotlar ularni hisobga olmaydi
    tx = db.query(Transaction).filter(
        Transaction.reference_type == "expense", Transaction.reference_id == exp.id,
        Transaction.voided_at.is_(None),
    ).first()
    if tx:
        cash_service.void_transaction(db, tx, current_user, now, "expense_void", exp.id, void_note)

    exp.voided_at = now
    exp.voided_by = current_user.id
    log_action_for(
        db, current_user, "EXPENSE_VOID", "expense", exp.id,
        old_values={"wallet_id": exp.wallet_id, "category_id": exp.category_id, "amount": float(exp.amount or 0),
                    "description": exp.description},
        new_values={"voided": True},
        branch_id=exp.branch_id,
    )
    db.commit()
    return {"ok": True, "message": "Xarajat bekor qilindi"}


# ─── Kassa O'tkazmalari (Transfers) ──────────────────────────────────────────
# T0.35: ikki bosqichli. `transfer/out` pulni yuboruvchidan darhol chiqaradi (pending, "yo'lda"),
# qabul qiluvchiga faqat `transfer/in` bilan tushadi; `transfer/reject` yuboruvchiga qaytaradi.
# in/reject CashTransfer qatorini FOR UPDATE bilan qulflaydi — parallel chaqiruvda faqat bittasi ishlaydi.

def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _lock_wallets(db: Session, company_id: int, *wallet_ids) -> dict:
    """Kassalarni korxona bo'yicha `id` tartibida qulflab oladi (deadlock bo'lmasligi uchun)."""
    ids = sorted({i for i in wallet_ids if i})
    if not ids:
        return {}
    rows = db.query(Wallet).filter(
        Wallet.id.in_(ids), Wallet.company_id == company_id
    ).order_by(Wallet.id).with_for_update().all()
    return {w.id: w for w in rows}


def _assert_receiver_branch(user, receiver) -> None:
    """T3.14: admin/director bo'lmagan xodim faqat o'z filiali kassasiga kelgan topshiriqni
    qabul qiladi/rad etadi (ikkala tomonda filial bo'lsa va ular farq qilsa — 403)."""
    role = getattr(user.role, "value", user.role)
    if role in ("admin", "director", "super_admin"):
        return
    ub = getattr(user, "branch_id", None)
    rb = getattr(receiver, "branch_id", None)
    if ub is not None and rb is not None and ub != rb:
        raise HTTPException(403, "Bu filial kassasi")


def _lock_transfer(db: Session, transfer_id: int, company_id: int):
    ct = db.query(CashTransfer).filter(
        CashTransfer.id == transfer_id, CashTransfer.company_id == company_id
    ).with_for_update().populate_existing().first()
    if not ct:
        raise HTTPException(404, "Transfer topilmadi")
    return ct


def _balance_of(balances: dict, payment_type: str, currency: str) -> Decimal:
    for item in balances.get(payment_type, []):
        if item["currency"] == currency:
            return Decimal(str(item["value"])).quantize(Decimal("0.01"))
    return Decimal("0.00")


def _send_transfers(db: Session, current_user, request: Request, sender_id: int,
                    receiver_id: int, note: Optional[str], lines: list) -> list:
    """Bir yoki bir nechta qatorni BITTA tranzaksiyada `pending` o'tkazma qilib yozadi.
    Avval hamma qator tekshiriladi, keyin yoziladi — birortasi xato bo'lsa hech narsa saqlanmaydi."""
    company_id = current_user.company_id
    wallets = _lock_wallets(db, company_id, sender_id, receiver_id)
    sender = wallets.get(sender_id)
    if not sender:
        raise HTTPException(404, "Kassa topilmadi")
    if not user_can_use_wallet(db, current_user, sender):
        raise HTTPException(403, "Bu kassadan o'tkazma qilishga ruxsat yo'q")
    assert_wallet_access(current_user, sender, db)  # T1.10: boshqa filial / shaxsiy kassa -> 403
    if sender_id == receiver_id:
        raise HTTPException(400, "Yuboruvchi va qabul qiluvchi kassa bir xil bo'lishi mumkin emas")
    receiver = wallets.get(receiver_id)
    if not receiver:
        raise HTTPException(404, "Kassa topilmadi")
    if sender.is_active is False or receiver.is_active is False:
        raise HTTPException(400, "Kassa faol emas")
    if not sender.is_open:
        raise HTTPException(400, "Yuboruvchi kassa yopiq")

    # Qoldiq: tur + valyuta bo'yicha jami (xuddi withdraw kabi)
    need: dict = {}
    for ln in lines:
        key = (ln.payment_type, ln.currency)
        need[key] = need.get(key, Decimal("0")) + Decimal(ln.amount)
    balances = get_kassa_balances(sender.id, db)
    for (ptype, curr), total in need.items():
        if _balance_of(balances, ptype, curr) < total.quantize(Decimal("0.01")):
            raise HTTPException(400, f"{ptype} ({curr}) bo'yicha balans yetarli emas")

    ip = _client_ip(request)
    created = []
    for ln in lines:
        amount = Decimal(ln.amount)
        ct = CashTransfer(
            company_id=company_id,
            sender_wallet_id=sender.id,
            receiver_wallet_id=receiver.id,
            sender_branch_id=sender.branch_id,
            receiver_branch_id=receiver.branch_id,
            amount=amount,
            currency=ln.currency,
            payment_type=ln.payment_type,
            status="pending",
            sent_by=current_user.id,
            received_by=None,
            received_at=None,
            note=note,
        )
        db.add(ct)
        db.flush()
        # Faqat yuboruvchi tomoni yoziladi (Transaction yo'q — P&L ga kirmaydi); qabul qiluvchiga — transfer/in da.
        # T2.8: `cash_service.post_cash` (kassa jurnali + Wallet.balance faqat UZS)
        cash_service.post_cash(
            db, user=current_user, wallet=sender, direction="out", amount=amount, currency=ln.currency,
            payment_type=ln.payment_type, reference_type="transfer_out", reference_id=ct.id,
            description=f"Transfer to {receiver.name}: {note or ''}", with_transaction=False,
        )
        log_action(
            db, "CASH_TRANSFER_OUT", "cash_transfer", ct.id, current_user.id,
            new_values={
                "sender_wallet_id": sender.id, "receiver_wallet_id": receiver.id,
                "sender_branch_id": sender.branch_id, "receiver_branch_id": receiver.branch_id,
                "amount": str(amount), "currency": ln.currency, "payment_type": ln.payment_type,
                "status": "pending",
            },
            ip_address=ip, company_id=company_id, branch_id=sender.branch_id,
        )
        created.append(ct)
    db.commit()
    return created


@router.post("/{wallet_id}/transfer/out-batch")
def transfer_out_batch(
    wallet_id: int,
    data: TransferOutBatchIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Bir nechta to'lov turi/valyuta qatorini atomar `pending` o'tkazma qilib yuborish."""
    created = _send_transfers(db, current_user, request, wallet_id, data.receiver_wallet_id, data.note, data.lines)
    return {"ok": True, "transfer_ids": [ct.id for ct in created]}


@router.post("/{wallet_id}/transfer/out")
def transfer_out(
    wallet_id: int,
    data: TransferOutIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Qat'iy 2-bosqichli transfer: pul yuboruvchidan chiqadi, o'tkazma `pending` (qabul qilinishini kutadi)"""
    created = _send_transfers(db, current_user, request, wallet_id, data.receiver_wallet_id, data.note, [data])
    return {"ok": True, "transfer_id": created[0].id, "status": "pending"}

@router.get("/{wallet_id}/transfers/pending")
def pending_transfers(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Shu kassaga yuborilgan, hali qabul qilinmagan o'tkazmalar (kuryer/agent topshiruvi)."""
    from sqlalchemy.orm import joinedload
    rows = db.query(CashTransfer).options(joinedload(CashTransfer.sender_wallet)).filter(
        CashTransfer.company_id == current_user.company_id,
        CashTransfer.receiver_wallet_id == wallet_id,
        CashTransfer.status == "pending",
    ).order_by(CashTransfer.id.desc()).all()
    return [
        {
            "id": ct.id, "amount": float(ct.amount), "currency": ct.currency, "payment_type": ct.payment_type,
            "note": ct.note, "sender_wallet_id": ct.sender_wallet_id,
            "sender_name": ct.sender_wallet.name if ct.sender_wallet else None,
            # T2.8: CashTransfer da `created_at` yo'q — yuborilgan vaqt `sent_at`; eski klientlar uchun `created_at` ham
            "sent_at": ct.sent_at.isoformat() if ct.sent_at else None,
            "created_at": ct.sent_at.isoformat() if ct.sent_at else None,
        }
        for ct in rows
    ]

@router.post("/transfer/in")
def transfer_in(
    data: TransferStatusIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Transfer qabul qilish"""
    company_id = current_user.company_id
    ct = _lock_transfer(db, data.transfer_id, company_id)
    receiver = _lock_wallets(db, company_id, ct.receiver_wallet_id).get(ct.receiver_wallet_id)
    if not receiver:
        raise HTTPException(400, "Qabul qiluvchi kassa topilmadi")
    if not user_can_use_wallet(db, current_user, receiver):
        raise HTTPException(403, "Bu kassaga kelgan o'tkazmani qabul qilishga ruxsat yo'q")
    _assert_receiver_branch(current_user, receiver)  # T3.14
    if ct.status != "pending":
        raise HTTPException(409, "Transfer allaqachon qayta ishlangan")
    if not receiver.is_open:
        raise HTTPException(400, "Qabul qiluvchi kassa yopiq")

    sender_name = ct.sender_wallet.name if ct.sender_wallet else ""

    # 1. Transfer holatini o'zgartirish
    ct.status = "completed"
    ct.received_by = current_user.id
    ct.received_at = datetime.now(timezone.utc)

    # 2. Qabul qiluvchiga KassaMovement (T2.8: `cash_service.post_cash`, Transaction yo'q; Wallet.balance faqat UZS)
    cash_service.post_cash(
        db, user=current_user, wallet=receiver, direction="in", amount=ct.amount, currency=ct.currency,
        payment_type=ct.payment_type, reference_type="transfer_in", reference_id=ct.id,
        description=f"Transfer from {sender_name}: {ct.note or ''}", with_transaction=False,
    )

    log_action(
        db, "CASH_TRANSFER_IN", "cash_transfer", ct.id, current_user.id,
        old_values={"status": "pending"},
        new_values={
            "status": "completed", "receiver_wallet_id": receiver.id, "amount": str(ct.amount),
            "currency": ct.currency, "payment_type": ct.payment_type,
        },
        ip_address=_client_ip(request), company_id=company_id, branch_id=receiver.branch_id,
    )
    db.commit()
    return {"ok": True}

@router.post("/transfer/reject")
def transfer_reject(
    data: TransferStatusIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Transferni bekor qilish va pulni yuboruvchiga qaytarish"""
    company_id = current_user.company_id
    ct = _lock_transfer(db, data.transfer_id, company_id)
    wallets = _lock_wallets(db, company_id, ct.sender_wallet_id, ct.receiver_wallet_id)
    sender = wallets.get(ct.sender_wallet_id)
    receiver = wallets.get(ct.receiver_wallet_id)
    if not (user_can_use_wallet(db, current_user, receiver) or user_can_use_wallet(db, current_user, sender)):
        raise HTTPException(403, "Bu o'tkazmani rad etishga ruxsat yo'q")
    # T3.14: qabul qiluvchi tomondan rad etish — qabul qiluvchi kassa filialiga mos bo'lishi shart
    # (yuboruvchi o'z topshirig'ini bekor qilishi bundan mustasno)
    if ct.sent_by != current_user.id:
        _assert_receiver_branch(current_user, receiver)
    if ct.status != "pending":
        raise HTTPException(409, "Transfer allaqachon qayta ishlangan")
    if not sender or sender.is_active is False:
        raise HTTPException(400, "Yuboruvchi kassa topilmadi")

    # Status o'zgarishi, pulni yuboruvchiga qaytarish va audit — mobil "Bekor qilish" bilan umumiy
    from app.services.mobile_service import reject_pending_transfer
    reject_pending_transfer(db, current_user, ct, sender, ip_address=_client_ip(request))
    db.commit()
    return {"ok": True}


# ─── X-Report (Oraliq Hisobot) ───────────────────────────────────────────────

@router.get("/{wallet_id}/x-report")
def get_x_report(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Kassani yopmasdan kutilayotgan qoldiqni ko'rish (router darajasida: admin/director/accountant)"""
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    if not w.is_open:
        raise HTTPException(400, "Kassa yopiq")
        
    session = db.query(KassaSession).filter(KassaSession.wallet_id == wallet_id, KassaSession.status == "open").first()
    calculated = get_kassa_balances(wallet_id, db)
    
    return {
        "wallet_name": w.name,
        "opened_at": session.opened_at if session else None,
        "calculated_balances": calculated
    }



# ─── Kunlik yopilishlar (Z-jamlama) — /{wallet_id} dan OLDIN e'lon qilinadi ──

@router.get("/sessions")
def list_company_sessions(
    branch_id: Optional[int] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """T1.11: korxona yoki filial bo'yicha kassa sessiyalari (kunlik yopilishlar) va umumiy farq.
    `totals.difference` = {to'lov turi: {valyuta: farq}} (kamomad > 0, ortiqcha < 0)."""
    from sqlalchemy.orm import joinedload
    from app.core.branch_context import build_branch_context
    from app.utils.report_utils import _date_range
    q = db.query(KassaSession).options(joinedload(KassaSession.wallet)).filter(
        KassaSession.company_id == current_user.company_id,
    )
    if branch_id:
        validate_branch(db, branch_id, current_user.company_id, require_active=False)
    ctx = build_branch_context(db, current_user)
    scope = ctx.scope_ids()
    if scope is not None:
        q = q.filter(KassaSession.branch_id.in_(list(scope)))
    if branch_id:
        q = q.filter(KassaSession.branch_id == branch_id)
    if status:
        q = q.filter(KassaSession.status == status)
    if date_from or date_to:
        start, end = _date_range(date_from, date_to)
        q = q.filter(KassaSession.opened_at >= start, KassaSession.opened_at < end)

    total = q.order_by(None).count()
    diff_total: dict = {}
    for (ds,) in q.order_by(None).with_entities(KassaSession.difference_summary).all():
        if not isinstance(ds, dict):
            continue
        for ptype, cmap in ds.items():
            if not isinstance(cmap, dict):
                continue
            for curr, val in cmap.items():
                bucket = diff_total.setdefault(ptype, {})
                bucket[curr] = round(bucket.get(curr, 0.0) + float(val or 0), 2)

    rows = q.order_by(KassaSession.opened_at.desc(), KassaSession.id.desc()).offset(skip).limit(limit).all()
    return {
        "items": [
            {
                "id": s.id,
                "wallet_id": s.wallet_id,
                "wallet_name": s.wallet.name if s.wallet else None,
                "branch_id": s.branch_id,
                "opened_at": s.opened_at,
                "closed_at": s.closed_at,
                "status": s.status,
                "opening_balance": float(s.opening_balance or 0),
                "expected_summary": s.expected_summary,
                "closing_summary": s.closing_summary,
                "difference_summary": s.difference_summary,
                "closed_by": s.closed_by,
            }
            for s in rows
        ],
        "total": total,
        "totals": {"difference": diff_total},
    }


# ─── Kassalar CRUD ────────────────────────────────────────────────────────────

@router.get("")
def list_wallets(
    branch_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    usable: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """T1.10: standart — faol kassalar; `branch_id` — shu filial kassalari, `usable=true` bilan umumiy
    (filialsiz) kassalar ham; `include_inactive` — nofaollar ham. Shaxsiy ("qo'l") kassalar faqat egasiga ko'rinadi."""
    wallets = wallet_service.list_wallets(
        db, current_user, branch_id=branch_id, active_only=not include_inactive, usable=usable,
    )
    meta = wallet_meta(db, current_user, wallets)
    # T2.8: N+1 yo'q — barcha kassalar balansi va ochiq sessiyalari bittadan so'rov bilan
    ids = [w.id for w in wallets]
    balances = get_kassa_balances_bulk(db, ids)
    sessions = open_session_ids(db, ids)
    return [
        wallet_out(w, db, current_user, meta.get(w.id), balances=balances.get(w.id), session_id=sessions.get(w.id))
        for w in wallets
    ]


@router.get("/reconcile")
def reconcile_wallets(
    branch_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """T2.8: kassa keshi bilan jurnalni solishtirish (admin/director/accountant — router darajasida).

    Har kassa uchun: `cached` — `Wallet.balance`, `ledger` — UZS `KassaMovement` sof (kirim - chiqim),
    `diff = cached - ledger`. `diff != 0` bo'lsa kesh jurnalga mos emas (`deploy/recalc_wallet_balances.py`)."""
    wallets = wallet_service.list_wallets(
        db, current_user, branch_id=branch_id, active_only=not include_inactive,
    )
    ids = [w.id for w in wallets]
    ledger: dict = {}
    if ids:
        rows = db.query(
            KassaMovement.wallet_id, KassaMovement.direction, func.sum(KassaMovement.amount),
        ).filter(
            KassaMovement.wallet_id.in_(ids), KassaMovement.currency == "UZS",
        ).group_by(KassaMovement.wallet_id, KassaMovement.direction).all()
        for wid, direction, amount in rows:
            sign = 1 if direction == "in" else (-1 if direction == "out" else 0)
            ledger[wid] = ledger.get(wid, Decimal("0")) + sign * Decimal(str(amount or 0))
    items = []
    for w in wallets:
        cached = Decimal(str(w.balance or 0))
        led = ledger.get(w.id, Decimal("0"))
        items.append({
            "wallet_id": w.id, "name": w.name, "branch_id": w.branch_id, "is_active": w.is_active,
            "cached": float(cached), "ledger": float(led), "diff": float(cached - led),
        })
    return {"items": items, "mismatched": sum(1 for i in items if abs(i["diff"]) >= 0.01)}


def _create_wallet(db: Session, user, data: WalletCreate) -> Wallet:
    """Kassa yaratish mantig'i (POST /kassa va POST /kassa/bulk uchun umumiy; commit chaqiruvchida)."""
    # T2.8: /finance/wallets bilan bir xil qoida (`wallet_service.create_wallet`): filial shu korxonaniki va faol
    # (T0.9), kassa yopiq (`is_open=False`) yaratiladi, boshlang'ich balans kassa jurnaliga `post_cash` bilan yoziladi
    w = wallet_service.create_wallet(
        db, user, name=data.name, type=data.type, branch_id=data.branch_id,
        opening_balance=data.opening_balance, currency=data.currency,
    )
    log_action_for(
        db, user, "WALLET_CREATE", "wallet", w.id,
        new_values={"name": w.name, "type": w.type, "branch_id": w.branch_id,
                    "opening_balance": float(data.opening_balance or 0), "currency": data.currency},
        branch_id=w.branch_id,
    )
    return w


@router.post("", dependencies=_ADMIN_ONLY)
def create_wallet(data: WalletCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = _create_wallet(db, current_user, data)
    db.commit()
    db.refresh(w)
    return wallet_out(w, db, current_user)


WALLET_BULK_MAX = 100


@router.post("/bulk", dependencies=_ADMIN_ONLY)
def create_wallets_bulk(rows: List[WalletCreate], db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """T4.5: filial kassalarini boshlang'ich qoldiq bilan ommaviy yaratish (ko'pi bilan 100 qator).

    Har qator `create_wallet` bilan bir xil mantiq (Kassa + `KassaMovement(reference_type="opening")`) va
    alohida savepoint ichida: xato qator qolganlarni to'xtatmaydi. Mavjud kassalar balansiga tegilmaydi.
    Javob: `{created, wallet_ids, errors: [{row, name, error}]}`."""
    if not rows:
        raise HTTPException(status_code=400, detail="Kassalar ro'yxati bo'sh")
    if len(rows) > WALLET_BULK_MAX:
        raise HTTPException(status_code=400, detail=f"Bir martada ko'pi bilan {WALLET_BULK_MAX} ta kassa yaratish mumkin")
    created_ids: list = []
    errors: list = []
    for idx, row in enumerate(rows, start=1):
        name = (row.name or "").strip()
        if not name:
            errors.append({"row": idx, "name": row.name, "error": "Kassa nomi majburiy"})
            continue
        if (row.opening_balance or 0) < 0:
            errors.append({"row": idx, "name": name, "error": "Boshlang'ich balans manfiy bo'lishi mumkin emas"})
            continue
        row.name = name
        try:
            with db.begin_nested():
                w = _create_wallet(db, current_user, row)
            created_ids.append(w.id)
        except HTTPException as e:
            errors.append({"row": idx, "name": name, "error": str(e.detail)})
    db.commit()
    return {"created": len(created_ids), "wallet_ids": created_ids, "errors": errors}


@router.get("/{wallet_id}")
def get_wallet(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(
        Wallet.id == wallet_id,
        Wallet.company_id == current_user.company_id
    ).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    return wallet_out(w, db, current_user)


@router.patch("/{wallet_id}", dependencies=_ADMIN_ONLY)
def update_wallet(wallet_id: int, data: WalletUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    old_values = {"name": w.name, "is_active": w.is_active, "branch_id": w.branch_id}
    if data.name is not None:
        w.name = data.name
    if data.is_active is not None:
        if data.is_active:
            w.is_active = True
        else:
            # T2.8: nofaol qilish DELETE bilan bir xil qoida (ochiq sessiya/o'tkazma/qoldiq bo'lsa 409)
            wallet_service.deactivate_wallet(db, current_user, w)
    if "branch_id" in data.model_fields_set:
        # T1.10: filial shu korxonaniki bo'lishi shart (begona/mavjud emas: 404), null — umumiy kassa
        w.branch_id = validate_wallet_branch(db, data.branch_id, current_user.company_id)
    log_action_for(
        db, current_user, "WALLET_UPDATE", "wallet", w.id,
        old_values=old_values, new_values={"name": w.name, "is_active": w.is_active, "branch_id": w.branch_id},
        branch_id=w.branch_id,
    )
    db.commit()
    return wallet_out(w, db, current_user)


@router.delete("/{wallet_id}", dependencies=_ADMIN_ONLY)
def delete_wallet(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    # T2.8: yumshoq o'chirish — `wallet_service.deactivate_wallet` (ochiq sessiya, kutilayotgan o'tkazma yoki
    # qoldiq bo'lsa 409; xodimlarga biriktirish tozalanadi, T1.10)
    old_active = wallet_service.deactivate_wallet(db, current_user, w)
    log_action_for(
        db, current_user, "WALLET_DELETE", "wallet", w.id,
        old_values={"name": w.name, "is_active": old_active}, new_values={"is_active": False},
        branch_id=w.branch_id,
    )
    db.commit()
    return {"ok": True}


# ─── Kassa ochish/yopish ─────────────────────────────────────────────────────

@router.post("/{wallet_id}/open")
def open_kassa(wallet_id: int, data: OpenKassaIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    if w.is_open:
        raise HTTPException(400, "Kassa allaqachon ochiq")

    now = datetime.now(timezone.utc)
    w.is_open = True
    w.opened_at = now
    w.opened_by = current_user.id
    w.closed_at = None

    session = KassaSession(
        wallet_id=w.id,
        company_id=current_user.company_id,
        branch_id=w.branch_id,
        opened_by=current_user.id,
        opening_balance=data.opening_balance,
        note=data.note,
        status="open",
    )
    db.add(session)
    db.flush()

    if data.opening_balance > 0:
        # Yopilishdagi inkasso (close_kassa) bu pulni balansdan ayiradi — simmetriya uchun ochilishda qo'shamiz
        # (T2.8: `post_cash` — kassa jurnali yangi sessiya bilan, Wallet.balance faqat UZS)
        cash_service.post_cash(
            db, user=current_user, wallet=w, direction="in", amount=data.opening_balance, currency=data.currency,
            payment_type="cash", reference_type="opening", description="Kassa ochilishi — boshlang'ich balans",
            with_transaction=False,
        )

    log_action_for(
        db, current_user, "KASSA_OPEN", "wallet", w.id,
        new_values={"session_id": session.id, "opening_balance": float(data.opening_balance or 0),
                    "currency": data.currency, "note": data.note},
        branch_id=w.branch_id,
    )
    db.commit()
    return {"ok": True, "session_id": session.id, "opened_at": now}


@router.post("/{wallet_id}/close")
def close_kassa(wallet_id: int, data: CloseKassaIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    if not w.is_open:
        raise HTTPException(400, "Kassa allaqachon yopiq")

    calculated = get_kassa_balances(wallet_id, db)
    now = datetime.now(timezone.utc)

    session = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet_id,
        KassaSession.status == "open"
    ).first()

    from app.core.branch_context import effective_branch_id
    _close_branch_id = (session.branch_id if session else None) or w.branch_id or effective_branch_id(db, current_user)

    # actual_amounts — foydalanuvchi haqiqatda sanab bergan summa (Blind Close).
    # { "cash": {"UZS": 1000, "USD": 50}, "card": {"UZS": 5000} }
    diff_summary = {}

    # PAYMENT_TYPES (bank/visa ham) + bazada uchragan boshqa turlar; "total" — jami, tur emas
    for ptype in [k for k in calculated if k != "total"]:
        ptype_diffs = {}
        calc_list = calculated.get(ptype, [])
        calc_map = {item["currency"]: float(item["value"]) for item in calc_list} if isinstance(calc_list, list) else {}
        
        act_map = data.actual_amounts.get(ptype, {})
        if not isinstance(act_map, dict):
            # Backward compatibility agar eski client oddiy raqam yuborsa
            act_map = {"UZS": float(act_map)} if act_map else {}

        all_currencies = set(calc_map.keys()).union(act_map.keys())
        
        for curr in all_currencies:
            c_val = calc_map.get(curr, 0.0)
            a_val = float(act_map.get(curr, 0.0))
            diff = (Decimal(str(c_val)) - Decimal(str(a_val))).quantize(Decimal("0.01"))   # diff > 0 -> kam topildi -> out harakati

            # 1. Kassir sanab bergan pulni "inkasso" sifatida kassa balansidan chiqarish
            if a_val > 0:
                # T2.8: `post_cash` — kassa jurnali (Transaction yo'q: pul sotuvda allaqachon hisoblangan) + Wallet.balance (UZS)
                cash_service.post_cash(
                    db, user=current_user, wallet=w, direction="out", amount=a_val, currency=curr,
                    payment_type=ptype, reference_type="closing_inkasso",
                    description=f"Yopilish (inkasso, {curr}): {a_val}", with_transaction=False,
                )

            # 2. Farqni (kamomad yoki ortiqcha) adjustment sifatida yozish
            if abs(diff) >= Decimal("0.01"):
                ptype_diffs[curr] = diff
                direction = "out" if diff > 0 else "in"
                
                mv_adj = KassaMovement(
                    wallet_id=wallet_id,
                    company_id=current_user.company_id,
                    session_id=session.id if session else None,
                    direction=direction,
                    payment_type=ptype,
                    amount=abs(diff),
                    currency=curr,
                    reference_type="closing_adjustment",
                    description=f"Yopilish farqi ({ptype}, {curr}): kutilgan={c_val}, haqiqiy={a_val}",
                    created_by=current_user.id,
                )
                db.add(mv_adj)
                # T1.11: kamomad/ortiqcha filial bo'yicha Transaction bo'lib yoziladi (P&L da ko'rinadi);
                # create_expense bilan bir xil naqsh: type + reference_type + branch_id + wallet_id + valyuta
                db.add(Transaction(
                    company_id=current_user.company_id,
                    branch_id=_close_branch_id,
                    wallet_id=wallet_id,
                    type="expense" if diff > 0 else "income",
                    amount=abs(diff),
                    payment_type=ptype,
                    currency_code=curr,
                    reference_type="closing_shortage" if diff > 0 else "closing_surplus",
                    reference_id=session.id if session else None,
                    description=f"Kassa yopilishidagi {'kamomad' if diff > 0 else 'ortiqcha'} ({ptype}, {curr})",
                    user_id=current_user.id,
                ))
                
                if curr == "UZS":
                    w.balance = Decimal(str(w.balance or 0)) + (-diff) # Agar kamomad bo'lsa (diff>0) ayiramiz, aks holda qo'shamiz
        
        if ptype_diffs:
            diff_summary[ptype] = ptype_diffs

    # Sessionni yopish
    if session:
        session.closed_at = now
        session.closed_by = current_user.id
        session.status = "closed"
        if session.branch_id is None:
            session.branch_id = w.branch_id
        session.expected_summary = calculated
        session.difference_summary = {p: {c: float(v) for c, v in d.items()} for p, d in diff_summary.items()}
        session.closing_summary = {
            "calculated": calculated,
            "actual": data.actual_amounts,
            "note": data.note,
        }

    w.is_open = False
    w.closed_at = now
    w.closed_by = current_user.id

    log_action_for(
        db, current_user, "KASSA_CLOSE", "wallet", w.id,
        old_values={"calculated": calculated},
        new_values={"session_id": session.id if session else None, "actual": data.actual_amounts,
                    "difference": {p: {c: float(v) for c, v in d.items()} for p, d in diff_summary.items()},
                    "note": data.note},
        branch_id=w.branch_id,
    )
    db.commit()

    final_balances = get_kassa_balances(wallet_id, db)
    return {
        "ok": True,
        "closed_at": now,
        "calculated_balances": calculated,
        "actual_amounts": data.actual_amounts,
        "difference": {p: {c: float(v) for c, v in d.items()} for p, d in diff_summary.items()},
        "final_balances": final_balances,
        "session_id": session.id if session else None,
    }




# ─── Investitsiya / Chiqarish ─────────────────────────────────────────────────

@router.post("/{wallet_id}/invest", dependencies=_ADMIN_ONLY)
def invest(wallet_id: int, data: InvestIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    if data.amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")

    from app.services.currency_service import norm_code
    data.currency = norm_code(data.currency)

    # T2.8: `post_cash` — faqat kassa jurnali (Transaction ataylab yo'q: investitsiya P&L ga kirmaydi);
    # T2.7: Wallet.balance faqat UZS, valyutali investitsiya KassaMovement.currency da
    cash_service.post_cash(
        db, user=current_user, wallet=w, direction="in", amount=data.amount, currency=data.currency,
        payment_type=data.payment_type, reference_type="invest", description=data.description or "Investitsiya",
        with_transaction=False,
    )
    log_action_for(
        db, current_user, "KASSA_INVEST", "wallet", w.id,
        new_values={"amount": float(data.amount), "payment_type": data.payment_type,
                    "currency": data.currency, "description": data.description},
        branch_id=w.branch_id,
    )
    db.commit()
    return {"ok": True}


@router.post("/{wallet_id}/withdraw", dependencies=_ADMIN_ONLY)
def withdraw(wallet_id: int, data: WithdrawIn, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    if data.amount <= 0:
        raise HTTPException(400, "Summa musbat bo'lishi kerak")

    from app.services.currency_service import norm_code
    data.currency = norm_code(data.currency)
    balances = get_kassa_balances(wallet_id, db)
    # Balansni valyuta bo'yicha tekshirish
    payment_type_balances = balances.get(data.payment_type, [])
    currency_balance = 0
    for item in payment_type_balances:
        if item["currency"] == data.currency:
            currency_balance = item["value"]
            break
    if Decimal(str(currency_balance)).quantize(Decimal("0.01")) < Decimal(str(data.amount)).quantize(Decimal("0.01")):
        raise HTTPException(400, f"{data.payment_type} ({data.currency}) bo'yicha balans yetarli emas")

    # T2.8: `post_cash` — faqat kassa jurnali (Transaction ataylab yo'q: chiqarish P&L ga kirmaydi);
    # T2.7: Wallet.balance faqat UZS, valyutali chiqarish KassaMovement.currency da
    cash_service.post_cash(
        db, user=current_user, wallet=w, direction="out", amount=data.amount, currency=data.currency,
        payment_type=data.payment_type, reference_type="withdraw", description=data.description or "Chiqarish",
        with_transaction=False,
    )
    log_action_for(
        db, current_user, "KASSA_WITHDRAW", "wallet", w.id,
        new_values={"amount": float(data.amount), "payment_type": data.payment_type,
                    "currency": data.currency, "description": data.description},
        branch_id=w.branch_id,
    )
    db.commit()
    return {"ok": True}


# ─── Kassa tarixi ─────────────────────────────────────────────────────────────

@router.get("/{wallet_id}/history")
def kassa_history(
    wallet_id: int,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    direction: Optional[str] = Query(None),  # in | out
    payment_type: Optional[str] = Query(None),
    reference_type: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Company isolation
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)

    q = db.query(KassaMovement).filter(
        KassaMovement.wallet_id == wallet_id,
        KassaMovement.company_id == current_user.company_id,
    )
    # T2.8: yagona sana chegarasi — yarim ochiq `[date_from 00:00, date_to + 1 kun 00:00)`, Toshkent vaqti
    # (Moliya va Hisobotlar bilan bir xil kun oralig'i)
    if date_from or date_to:
        start, end = date_bounds(date_from, date_to)
        q = q.filter(KassaMovement.created_at >= start, KassaMovement.created_at < end)
    if direction:
        q = q.filter(KassaMovement.direction == direction)
    if payment_type:
        q = q.filter(KassaMovement.payment_type == payment_type)
    if reference_type:
        q = q.filter(KassaMovement.reference_type == reference_type)

    total = q.count()
    items = q.order_by(KassaMovement.created_at.desc()).offset(skip).limit(limit).all()

    # Summary — T2.8: yuqoridagi filtrlarga (sana, yo'nalish, to'lov turi, havola) mos va valyuta bo'yicha ajratilgan
    # (turli valyutalar qo'shilmaydi): {"UZS": {total_in, total_out, balance}, "USD": {...}}. Eski
    # `total_in/total_out/balance` kalitlari UZS uchun saqlanadi (moslik).
    by_currency: dict = {}
    for currency, dirn, amount in q.order_by(None).with_entities(
        KassaMovement.currency, KassaMovement.direction, func.sum(KassaMovement.amount),
    ).group_by(KassaMovement.currency, KassaMovement.direction).all():
        c = by_currency.setdefault(currency or "UZS", {"total_in": 0.0, "total_out": 0.0, "balance": 0.0})
        if dirn == "in":
            c["total_in"] += float(amount or 0)
        elif dirn == "out":
            c["total_out"] += float(amount or 0)
        c["balance"] = c["total_in"] - c["total_out"]
    uzs = by_currency.get("UZS", {"total_in": 0.0, "total_out": 0.0, "balance": 0.0})

    return {
        "total": total,
        "summary": {
            "total_in": uzs["total_in"],
            "total_out": uzs["total_out"],
            "balance": uzs["balance"],
            **by_currency,
        },
        "items": [
            {
                "id": m.id,
                "direction": m.direction,
                "payment_type": m.payment_type,
                "amount": float(m.amount),
                "currency": m.currency,
                "reference_type": m.reference_type,
                "reference_id": m.reference_id,
                "description": m.description,
                "created_at": m.created_at,
            }
            for m in items
        ],
    }


@router.get("/{wallet_id}/summary")
def kassa_summary(wallet_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    return get_kassa_balances(wallet_id, db)


# ─── Sessiyalar tarixi ────────────────────────────────────────────────────────

@router.get("/{wallet_id}/sessions")
def kassa_sessions(wallet_id: int, skip: int = 0, limit: int = 20, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    sessions = db.query(KassaSession).filter(
        KassaSession.wallet_id == wallet_id,
        KassaSession.company_id == current_user.company_id,
    ).order_by(KassaSession.opened_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": s.id,
            "status": s.status,
            "opened_at": s.opened_at,
            "closed_at": s.closed_at,
            "opening_balance": float(s.opening_balance or 0),
            "expected_summary": s.expected_summary,
            "closing_summary": s.closing_summary,
            "difference_summary": s.difference_summary,
            "branch_id": s.branch_id,
            "closed_by": s.closed_by,
            "note": s.note,
        }
        for s in sessions
    ]


# (Expense endpoints moved above — before /{wallet_id} routes)


@router.get("/{wallet_id}/expenses")
def list_expenses(
    wallet_id: int,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = 0, limit: int = 50,
    include_voided: bool = Query(False),
    status: Optional[str] = Query(None, description="approved (standart) | pending | rejected | all"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    w = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.company_id == current_user.company_id).first()
    if not w:
        raise HTTPException(404, "Kassa topilmadi")
    assert_wallet_access(current_user, w, db)
    q = db.query(Expense).execution_options(include_unapproved_expenses=True).filter(
        Expense.wallet_id == wallet_id, Expense.company_id == current_user.company_id,
    )
    # T4.6: standart — faqat tasdiqlangan xarajatlar (eski mijozlar uchun o'zgarmaydi); pending/rejected/all so'ralganda
    if status != "all":
        q = q.filter(Expense.status == (status if status in ("pending", "rejected") else "approved"))
    # T1.19: bekor qilingan (void) xarajatlar ko'rsatilmaydi; include_voided=true — faqat admin/director
    show_voided = include_voided and _can_see_voided(current_user)
    if not show_voided:
        q = q.filter(Expense.voided_at.is_(None))
    if date_from or date_to:
        start, end = date_bounds(date_from, date_to)
        q = q.filter(Expense.created_at >= start, Expense.created_at < end)
    total = q.count()
    items = q.order_by(Expense.created_at.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "currency": e.currency or "UZS",
                "amount_uzs": float(e.amount_uzs if e.amount_uzs is not None else e.amount),
                "category": e.category.name if e.category else None,
                "description": e.description,
                "created_at": e.created_at,
                "voided_at": e.voided_at,
                "status": e.status,
                "created_by": e.created_by,
                "approved_by": e.approved_by,
                "approval_request_id": e.approval_request_id,
            }
            for e in items
        ],
    }
