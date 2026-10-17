"""
Finance API — 3-bosqich: Moliya moduli, P&L, Debitor/Kreditor boshqaruvi
"""
# pyright: reportMissingImports=false
# pyright: reportMissingModuleSource=false
from datetime import date, datetime, timedelta
from typing import Literal, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response  # type: ignore
from sqlalchemy.orm import Session, joinedload  # type: ignore
from sqlalchemy import and_, func, or_  # type: ignore
from pydantic import BaseModel, Field, field_validator  # type: ignore
from sqlalchemy.orm.attributes import flag_modified  # type: ignore
from decimal import Decimal

from starlette import status

from app.core.audit import log_action_for  # type: ignore
from app.database import get_db  # type: ignore
from app.models.moliya import ExpenseCategory, Expense, Transaction, Wallet  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.sale import Sale  # type: ignore
from app.models.supplier import Supplier  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User, UserRole, UserWallet  # type: ignore
from app.core.dependencies import require_roles, require_module_roles  # type: ignore
from app.admin_tg_bot.notifications import trigger_instant_notification
from app.admin_tg_bot.message_utils import describe_location
from app.utils.telegram_text import esc
from app.services.wallet_access import get_company_wallet, find_company_wallet  # type: ignore
from app.utils.report_utils import tx_not_internal, tx_cash_flow_filter, date_bounds  # type: ignore
from app.services import cash_service, wallet_service  # type: ignore
from app.services import approval_service, expense_service  # type: ignore  # T4.6: xarajat limiti va tasdiqlash
from app.services import customer_ledger as cust_ledger, supplier_ledger as sup_ledger  # type: ignore  # T2.6
from app.services.pnl_service import branch_condition  # type: ignore
from app.core.branch_context import BRANCH_FORBIDDEN, BranchContext, get_branch_context  # type: ignore
from app.core.dependencies import require_roles_allow_expired  # type: ignore
from app.core.report_scope import effective_ctx, resolve_company_id, resolve_report_scope  # type: ignore
from app.core.roles import FINANCE_ROLES  # type: ignore

router = APIRouter(prefix="/finance", tags=["Finance"])

# Mijoz qarzini to'lash: kassir ham qabul qiladi (mobil rollar dependencies.py da bloklangan)
DEBT_PAY_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.accountant, UserRole.cashier)
# Ta'minotchi qarzi bilan bog'langan tranzaksiyalar (o'chirish/tahrirlash maxsus mantiq bilan)
SUPPLIER_TX_TYPES = ("purchase_order", "supplier_payment", "return_to_supplier")
# Tizim yaratgan tranzaksiyalar — Moliya sahifasidan PUT/DELETE qilib bo'lmaydi
SYSTEM_TX_TYPES = ("sale", "sale_refund", "shift")
SYSTEM_TX_LOCKED = "Tizim yaratgan yozuvni o'zgartirib bo'lmaydi: tegishli bo'limdan bekor qiling"
# POST /finance/transactions uchun ruxsat etilgan havola turlari (qo'lda kiritiladigan kirim/chiqim)
MANUAL_TX_REFERENCE_TYPES = (None, "other_income", "other_expense")
NO_BRANCH = "Korxonada filial yo'q"


# ─── Yordamchi: satrdan datetime ─────────────────────────────────────────────

def _parse_dt_start(date_str: Optional[str]) -> datetime:
    """'YYYY-MM-DD' → kun boshi (Toshkent 00:00, tz-aware). T2.8: yagona `report_utils.date_bounds`."""
    return date_bounds(date_str, None)[0]


def _parse_dt_end(date_str: Optional[str]) -> datetime:
    """'YYYY-MM-DD' → ertasi kun 00:00 (yarim ochiq `[start, end)` chegarasi, tz-aware)."""
    return date_bounds(None, date_str)[1]


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ExpenseCategoryIn(BaseModel):
    name: str
    description: Optional[str] = None


class WalletIn(BaseModel):
    name: str
    type: str = "cash"
    branch_id: Optional[int] = None
    is_active: bool = True

class ExpenseIn(BaseModel):
    branch_id: Optional[int] = None  # bo'sh bo'lsa serverda aniqlanadi (kassa → foydalanuvchi → korxona filiali)
    category_id: int
    amount: Decimal = Field(gt=0)
    wallet_id: Optional[int] = None
    description: Optional[str] = None
    currency: Optional[str] = "UZS"  # T2.7: xarajat valyutasi (korxonada faol bo'lishi shart)

    @field_validator("wallet_id", "branch_id", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        # Bo'sh satr ('') — tanlanmagan; 422 o'rniga None (himoya qatlami, T3.6)
        return None if isinstance(v, str) and not v.strip() else v


class TransactionIn(BaseModel):
    branch_id: Optional[int] = None
    type: Literal["income", "expense"]
    amount: Decimal = Field(gt=0)
    wallet_id: Optional[int] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None  # e'tiborga olinmaydi — qo'lda havola berib bo'lmaydi
    description: Optional[str] = None
    payment_type: Optional[str] = "cash"
    currency_code: Optional[str] = "UZS"

    @field_validator("wallet_id", "branch_id", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


class DebtPaymentIn(BaseModel):
    amount: Decimal = Field(gt=0)
    description: Optional[str] = None
    currency: Optional[str] = "UZS"
    wallet_id: Optional[int] = None
    payment_type: Optional[str] = "cash"

    @field_validator("wallet_id", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v


# ─── Yordamchilar: filial, kassa sessiyasi, eski xarajat tranzaksiyasi ───────

def _resolve_tx_branch(db: Session, user, explicit_branch_id: Optional[int] = None, wallet=None) -> int:
    """Xarajat/tranzaksiya filiali — yagona `resolve_money_branch_id` (T2.2).

    Tartib: body dagi `branch_id` (korxonaga tekshiriladi, begona bo'lsa 400) -> kassa filiali ->
    foydalanuvchi filiali (T1.2) -> korxonaning asosiy/birinchi FAOL filiali (T1.4, T1.12).
    Topilmasa 400 "Korxonada filial yo'q"; `0` qaytarilmaydi.
    """
    from app.services.branch_attribution import resolve_money_branch_id
    return resolve_money_branch_id(db, user, wallet=wallet, explicit_branch_id=explicit_branch_id)


# T2.8: kassa jurnali yordamchilari `cash_service` da (yagona joy)
_open_session_id = cash_service.open_session_id


def _find_legacy_expense_tx(db: Session, exp):
    """Eski (reference_id siz) xarajat tranzaksiyasi: bir xil summa, kassa, filial va
    yaratilish vaqti 10 soniya ichida. Faqat bitta nomzod bo'lsa qaytariladi."""
    q = db.query(Transaction).filter(
        Transaction.reference_type == "expense",
        Transaction.reference_id.is_(None),
        Transaction.type == "expense",
        Transaction.amount == exp.amount,
        Transaction.branch_id == exp.branch_id,
    )
    if exp.wallet_id:
        q = q.filter(Transaction.wallet_id == exp.wallet_id)
    else:
        q = q.filter(Transaction.wallet_id.is_(None))
    cands = []
    for t in q.all():
        if exp.created_at and t.created_at:
            if abs((t.created_at - exp.created_at).total_seconds()) >= 10:
                continue
        cands.append(t)
    return cands[0] if len(cands) == 1 else None


def _find_tx_kassa_movement(db: Session, tx):
    """Tranzaksiyaning kassa harakati: havola bo'yicha, havolasiz qo'lda kiritilgan yozuvlarda esa
    tranzaksiya id si bo'yicha (`cash_service.find_kassa_movement`)."""
    return cash_service.find_kassa_movement(db, tx)


def _can_see_voided(user) -> bool:
    """T1.19: bekor qilingan (void) yozuvlarni faqat admin/director ko'ra oladi (include_voided=true)."""
    return user.role in (UserRole.admin, UserRole.director, UserRole.super_admin)


# T1.19 teskari yozuvlar `cash_service` da: asl harakat/tranzaksiya o'chirilmaydi
_reverse_kassa_movement = cash_service.reverse_movement
_void_tx_pair = cash_service.void_transaction


def _tx_audit(tx) -> dict:
    """Audit uchun tranzaksiya ko'rinishi."""
    return {
        "type": tx.type, "amount": float(tx.amount or 0), "wallet_id": tx.wallet_id,
        "payment_type": tx.payment_type, "currency_code": tx.currency_code,
        "reference_type": tx.reference_type, "reference_id": tx.reference_id,
        "description": tx.description,
    }


# ─── Wallets ──────────────────────────────────────────────────────────────────

@router.get("/wallets")
def list_wallets(
    branch_id: Optional[int] = Query(None),
    include_inactive: bool = Query(False),
    usable: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """T1.10: `/kassa` ro'yxati bilan bir xil to'plam (`wallet_service.list_wallets`) — standart faol kassalar,
    `id` bo'yicha tartiblangan, shaxsiy ("qo'l") kassalar faqat egasiga; `branch_id` / `usable` (shu filial +
    umumiy kassalar) / `include_inactive` parametrlari. `super_admin` uchun ham korxona filtri qo'llanadi.
    T2.8: `is_default` — joriy foydalanuvchining default kassasi (UI hech narsani `data[0]` deb tanlamasin);
    `detailed_balances` (WalletBalance) olib tashlandi."""
    from app.services.wallet_resolver import wallet_meta
    # T0.5: FINANCE_ROLES da bo'lmaganlar (kassir va h.k.) balanssiz oladi; user_wallets
    # biriktirmasi bo'lsa faqat shu kassalar, bo'lmasa o'z filiali (va umumiy) faol kassalari.
    see_balance = user.role == UserRole.super_admin or user.role in FINANCE_ROLES
    wallets = wallet_service.list_wallets(
        db, user, branch_id=branch_id, active_only=not include_inactive, usable=usable,
    )
    if not see_balance:
        assigned = {
            r[0] for r in db.query(UserWallet.wallet_id).filter(UserWallet.user_id == user.id).all()
        }
        if assigned:
            wallets = [w for w in wallets if w.id in assigned]
    meta = wallet_meta(db, user, wallets)
    result = []
    for w in wallets:
        item = {
            "id": w.id,
            "name": w.name,
            "type": w.type,
            "is_active": w.is_active,
            "branch_id": w.branch_id,
            **meta.get(w.id, {}),
        }
        item["is_default"] = bool(item.get("is_default_for_me", False))
        if see_balance:
            item["balance"] = float(w.balance)
        result.append(item)
    return result

@router.post("/wallets", status_code=201)
def create_wallet(
    data: WalletIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    # T2.8: /kassa bilan bir xil qoida (`wallet_service.create_wallet`): filial korxonaga tekshiriladi
    # (begona/mavjud emas: 400 "Filial topilmadi", T0.3; nofaol: 400, T0.9), kassa YOPIQ (`is_open=False`)
    # va sessiyasiz yaratiladi — ochish Kassa sahifasidan (`POST /kassa/{id}/open`)
    w = wallet_service.create_wallet(
        db, user, name=data.name, type=data.type, branch_id=data.branch_id, is_active=data.is_active,
        strict_lookup=True,
    )
    log_action_for(
        db, user, "WALLET_CREATE", "wallet", w.id,
        new_values={"name": w.name, "type": w.type, "branch_id": w.branch_id},
        branch_id=w.branch_id,
    )
    db.commit()
    db.refresh(w)
    return w

@router.delete("/wallets/{wallet_id}", status_code=204)
def delete_wallet(
    wallet_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    w = get_company_wallet(db, wallet_id, user.company_id, require_active=False)
    # Qattiq o'chirilmaydi — faqat nofaol qilinadi (`wallet_service.deactivate_wallet`): ochiq sessiya,
    # kutilayotgan o'tkazma yoki qoldiq bo'lsa 409; xodimlarga biriktirish tozalanadi (T1.10)
    old_active = wallet_service.deactivate_wallet(db, user, w)
    log_action_for(
        db, user, "WALLET_DELETE", "wallet", w.id,
        old_values={"name": w.name, "is_active": old_active}, new_values={"is_active": False},
        branch_id=w.branch_id,
    )
    db.commit()


# ─── Expense Categories ───────────────────────────────────────────────────────

CATEGORY_DUPLICATE = "Bunday nomli kategoriya allaqachon mavjud"
CATEGORY_HAS_EXPENSES = "Kategoriyada xarajatlar bor"
CATEGORY_NAME_INVALID = "Kategoriya nomi 1-50 belgidan iborat bo'lishi kerak"


def company_expense_categories(db: Session, company_id: Optional[int]):
    """Korxonaning xarajat kategoriyalari (nom bo'yicha). `/kassa/categories` ham shuni ishlatadi, shuning uchun
    Kassa va Moliya sahifalari bitta ro'yxatni ko'radi (umumiy `company_id IS NULL` qatorlar qaytmaydi)."""
    return (
        db.query(ExpenseCategory)
        .filter(ExpenseCategory.company_id == company_id)
        .order_by(ExpenseCategory.name)
        .all()
    )


def clean_category_name(name: Optional[str]) -> str:
    """Nomni tozalaydi (bo'sh joylar); bo'sh yoki 50 belgidan uzun bo'lsa 400."""
    clean = (name or "").strip()
    if not clean or len(clean) > 50:
        raise HTTPException(status_code=400, detail=CATEGORY_NAME_INVALID)
    return clean


def assert_category_name_free(db: Session, company_id: Optional[int], name: str, exclude_id: Optional[int] = None) -> None:
    """`(company_id, lower(btrim(name)))` takrorlansa 409."""
    q = db.query(ExpenseCategory.id).filter(
        func.lower(func.trim(ExpenseCategory.name)) == name.strip().lower(),
    )
    q = q.filter(ExpenseCategory.company_id.is_(None) if company_id is None else ExpenseCategory.company_id == company_id)
    if exclude_id is not None:
        q = q.filter(ExpenseCategory.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail=CATEGORY_DUPLICATE)


def create_company_category(db: Session, company_id: Optional[int], name: str, description: Optional[str]) -> ExpenseCategory:
    """Kategoriya yaratadi (nom tozalanadi, takror bo'lsa 409). Commit chaqiruvchida."""
    clean = clean_category_name(name)
    assert_category_name_free(db, company_id, clean)
    cat = ExpenseCategory(name=clean, description=description, company_id=company_id)
    db.add(cat)
    db.flush()
    return cat


@router.get("/expense-categories")
def list_expense_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    if user.role.value == "super_admin":
        return db.query(ExpenseCategory).order_by(ExpenseCategory.name).all()
    return company_expense_categories(db, user.company_id)


@router.post("/expense-categories", status_code=201)
def create_expense_category(
    data: ExpenseCategoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    cat = create_company_category(db, user.company_id, data.name, data.description)
    db.commit()
    db.refresh(cat)
    return cat


def _own_category_or_404(db: Session, cat_id: int, user) -> ExpenseCategory:
    cat = db.get(ExpenseCategory, cat_id)  # SQLAlchemy 2.0 usuli
    if not cat or (user.role.value != "super_admin" and cat.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Not found")
    return cat


@router.put("/expense-categories/{cat_id}")
def update_expense_category(
    cat_id: int,
    data: ExpenseCategoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    """Kategoriya nomi/izohini o'zgartirish (nom takrorlansa 409)."""
    cat = _own_category_or_404(db, cat_id, user)
    clean = clean_category_name(data.name)
    assert_category_name_free(db, cat.company_id, clean, exclude_id=cat.id)
    cat.name = clean
    if data.description is not None:
        cat.description = data.description
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/expense-categories/{cat_id}", status_code=204)
def delete_expense_category(
    cat_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    cat = _own_category_or_404(db, cat_id, user)
    # Xarajati bor kategoriyani o'chirib bo'lmaydi (Expense.category_id NOT NULL FK, aks holda 500)
    if db.query(Expense.id).execution_options(include_unapproved_expenses=True).filter(Expense.category_id == cat.id).first():
        raise HTTPException(status_code=409, detail=CATEGORY_HAS_EXPENSES)
    db.delete(cat)
    db.commit()


# ─── Expenses ─────────────────────────────────────────────────────────────────

@router.get("/expenses")
def list_expenses(
    branch_id: Optional[int] = None,
    category_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_voided: bool = False,
    status: Optional[str] = Query(None, description="approved (standart) | pending | rejected | all"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    response: Response = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    """T2.8: `skip/limit` (standart 500, eng ko'pi 2000); jami soni `X-Total-Count` sarlavhasida (javob massiv).
    T4.6: standart — faqat tasdiqlangan xarajatlar (pending/rejected P&L va kassaga kirmaydi); `status=pending|rejected|all`."""
    q = db.query(Expense).execution_options(include_unapproved_expenses=True)
    if status != "all":
        q = q.filter(Expense.status == (status if status in ("pending", "rejected") else "approved"))
    # T1.19: bekor qilingan (void) xarajatlar ko'rsatilmaydi; include_voided=true — faqat admin/director
    if not (include_voided and _can_see_voided(user)):
        q = q.filter(Expense.voided_at.is_(None))
    if user.role.value != "super_admin":
        q = q.filter(Expense.company_id == user.company_id)
    branch_id = resolve_report_scope(db, user, branch_id).branch_id  # T2.1: cheklangan menejer — o'z filiali
    if branch_id:  # -1 — filialsiz guruh (T2.2)
        q = q.filter(branch_condition(Expense.branch_id, user.company_id, branch_id))
    if category_id:
        q = q.filter(Expense.category_id == category_id)
    if date_from:
        q = q.filter(Expense.created_at >= _parse_dt_start(date_from))
    if date_to:
        q = q.filter(Expense.created_at < _parse_dt_end(date_to))
    if response is not None:
        response.headers["X-Total-Count"] = str(q.order_by(None).count())
    results = (
        q.options(joinedload(Expense.branch), joinedload(Expense.category), joinedload(Expense.wallet))
        .order_by(Expense.created_at.desc(), Expense.id.desc()).offset(skip).limit(limit).all()
    )
    return [
        {
            "id": e.id,
            "branch_id": e.branch_id,
            "branch_name": e.branch.name if e.branch else None,
            "wallet_id": e.wallet_id,
            "wallet_name": e.wallet.name if e.wallet else None,
            "category_id": e.category_id,
            "category_name": e.category.name if e.category else None,
            "amount": float(e.amount),
            "currency": e.currency or "UZS",
            "amount_uzs": float(e.amount_uzs if e.amount_uzs is not None else e.amount),
            "description": e.description,
            "approved_by": e.approved_by,  # T4.6: haqiqiy tasdiqlovchi (NULL — avto-tasdiq)
            "created_by": e.created_by,
            "status": e.status,
            "approval_request_id": e.approval_request_id,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "voided_at": e.voided_at.isoformat() if e.voided_at else None,
        }
        for e in results
    ]


@router.post("/expenses", status_code=201)
def create_expense(
    data: ExpenseIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    # Kategoriya — o'z korxonasiniki yoki umumiy (company_id NULL), aks holda 404 (begona resurs ko'rinmaydi)
    category = db.query(ExpenseCategory).filter(
        ExpenseCategory.id == data.category_id,
        (ExpenseCategory.company_id == user.company_id) | (ExpenseCategory.company_id.is_(None)),
    ).first()
    if not category:
        raise HTTPException(status_code=404, detail="Kategoriya topilmadi")
    # Kassa — o'z korxonasiniki va faol bo'lishi shart (begona bo'lsa 404)
    wallet = get_company_wallet(db, data.wallet_id, user.company_id, for_update=True)
    # Filial — body dagi (korxonaga tekshirilgan) → kassa → foydalanuvchi → korxona filiali
    branch_id = _resolve_tx_branch(db, user, explicit_branch_id=data.branch_id, wallet=wallet)

    # T2.7: valyuta korxonada faol bo'lishi shart; kurs va UZS ekvivalent xarajatda saqlanadi
    from app.services.currency_service import get_rate, require_active_currency
    currency = require_active_currency(db, user.company_id, data.currency)
    rate = get_rate(db, user.company_id, currency)

    # T4.6: yagona xarajat mantiqi (`expense_service`): limit tekshiruvi, created_by (yaratuvchi) va approved_by
    # (tasdiqlovchi) alohida. T2.8 `post_cash` (Transaction + KassaMovement + Wallet.balance) limit ichida
    # darhol, limitdan katta xarajatda (`pending`) esa tasdiqdan keyin yoziladi.
    expense, approval_req = expense_service.create_expense(
        db, user=user, wallet=wallet, branch_id=branch_id, category_id=data.category_id,
        category_name=category.name, amount=data.amount, currency=currency, rate=rate,
        description=data.description, payment_type="cash",
    )
    log_action_for(
        db, user, "EXPENSE_CREATE", "expense", expense.id,
        new_values={"wallet_id": wallet.id if wallet else None, "category_id": data.category_id,
                    "amount": float(data.amount), "currency": currency, "description": data.description,
                    "status": expense.status},
        branch_id=branch_id,
    )
    db.commit()
    db.refresh(expense)

    if approval_req is not None:
        # Tasdiq kutilmoqda: "Yangi xarajat" xabari o'rniga tugmali tasdiq so'rovi yuboriladi
        background_tasks.add_task(approval_service.notify_approvers_by_id, approval_req.id)
        return expense

    # ── Telegram bildirishnoma ──
    try:
        cat_name = expense.category.name if getattr(expense, 'category', None) else "Noma'lum"
        # Filial: xarajat filiali (body → kassa → foydalanuvchi), kassa nomi bilan (T3.16)
        location = describe_location(db, branch_id=branch_id, wallet_id=expense.wallet_id)
        msg = "📉 <b>Yangi Xarajat</b>\n" + (f"{location}\n" if location else "")
        msg += f"🗂 Kategoriya: {esc(cat_name)}\n💰 Summa: {float(expense.amount):,.0f} {esc(expense.currency or 'UZS')}\n📝 Izoh: {esc(expense.description or '-')}"
        # Javobdan keyin yuboriladi — Telegram kechikishi so'rovni ushlab turmaydi
        background_tasks.add_task(trigger_instant_notification, user.company_id, msg, "finance", branch_id)
    except Exception as e:
        print(f"Telegram notification error: {e}")

    return expense


@router.delete("/expenses/{exp_id}", status_code=204)
def delete_expense(
    exp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    """Xarajatni bekor qilish (void). T1.19: Expense/Transaction/KassaMovement bazadan o'chirilmaydi —
    `voided_at/voided_by` qo'yiladi, kassaga teskari harakat yoziladi, hamyon balansi qaytariladi."""
    exp = db.get(Expense, exp_id, execution_options={"include_unapproved_expenses": True})  # SQLAlchemy 2.0 usuli
    if not exp or (user.role.value != "super_admin" and (exp.company_id is None or exp.company_id != user.company_id)):
        raise HTTPException(status_code=404, detail="Not found")
    if exp.voided_at is not None:
        raise HTTPException(status_code=400, detail="Xarajat allaqachon bekor qilingan")

    # T4.6: tasdiq kutayotgan/rad etilgan xarajatda pul yozuvi yo'q — balansga teskari yozuv KERAK EMAS
    if exp.status != "approved":
        _old_status = exp.status
        expense_service.cancel_pending_expense(db, exp, user)
        exp.voided_at = datetime.utcnow()
        exp.voided_by = user.id
        log_action_for(
            db, user, "EXPENSE_VOID", "expense", exp.id,
            old_values={"status": _old_status, "amount": float(exp.amount or 0)}, new_values={"voided": True},
            branch_id=exp.branch_id, company_id=exp.company_id,
        )
        db.commit()
        return

    now = datetime.utcnow()

    # Moliya tranzaksiyasi: havola bo'yicha, topilmasa eski (reference_id siz) yozuv
    tx = db.query(Transaction).filter(
        Transaction.reference_type == "expense",
        Transaction.reference_id == exp.id,
        Transaction.company_id == exp.company_id,
        Transaction.type == "expense",
        Transaction.voided_at.is_(None),
    ).first()
    if not tx:
        tx = _find_legacy_expense_tx(db, exp)

    # Kassa balansi qaytadi (avval o'chirishda tiklanmasdi) — T2.7: faqat UZS xarajat uchun
    if exp.wallet_id:
        wallet = find_company_wallet(db, exp.wallet_id, exp.company_id)
        cash_service.apply_wallet_balance(wallet, "in", exp.amount, exp.currency)

    # Kassa harakati o'chmaydi — teskari kirim harakati yoziladi
    from app.models.moliya import KassaMovement
    for mv in db.query(KassaMovement).filter(
        KassaMovement.reference_type == "expense",
        KassaMovement.reference_id == exp.id,
        KassaMovement.company_id == exp.company_id,
    ).all():
        _reverse_kassa_movement(db, mv, user, "expense_void", exp.id, f"Xarajat bekor qilindi (ID: {exp.id})")

    if tx:
        _void_tx_pair(db, tx, user, now, "expense_void", exp.id, f"Xarajat bekor qilindi (ID: {exp.id})")
    exp.voided_at = now
    exp.voided_by = user.id
    log_action_for(
        db, user, "EXPENSE_VOID", "expense", exp.id,
        old_values={"wallet_id": exp.wallet_id, "category_id": exp.category_id,
                    "amount": float(exp.amount or 0), "description": exp.description},
        new_values={"voided": True}, branch_id=exp.branch_id, company_id=exp.company_id,
    )
    db.commit()


# ─── Cash Balance ──────────────────────────────────────────────────────────────

@router.get("/cash-balance")
def get_cash_balance(
    branch_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    company_id: Optional[int] = Query(None, description="Faqat super_admin uchun (majburiy)"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles_allow_expired(*FINANCE_ROLES)),
):
    """T2.1: rol tekshiruvi (`FINANCE_ROLES`) obuna tugagan bo'lsa ham ishlaydi; cheklangan menejer faqat o'z
    filiali; `super_admin` uchun `company_id` majburiy (korxonalar yig'indisi aralashmaydi)."""
    cid = resolve_company_id(user, company_id)
    branch_id = resolve_report_scope(db, user, branch_id).branch_id

    def _by_currency(tx_type: str):
        q = db.query(
            Transaction.currency_code,
            func.coalesce(func.sum(Transaction.amount), 0).label("total")
        ).filter(
            Transaction.type == tx_type, tx_cash_flow_filter(), Transaction.voided_at.is_(None),
            Transaction.company_id == cid,
        )
        if branch_id:
            q = q.filter(branch_condition(Transaction.branch_id, cid, branch_id))
        if date_from:
            q = q.filter(Transaction.created_at >= _parse_dt_start(date_from))
        if date_to:
            q = q.filter(Transaction.created_at < _parse_dt_end(date_to))
        q = q.group_by(Transaction.currency_code)
        result = {}
        for row in q.all():
            curr = (row.currency_code or "UZS").upper()
            result[curr] = result.get(curr, 0.0) + float(row.total or 0)
        return result

    income_by_curr = _by_currency("income")
    expense_by_curr = _by_currency("expense")

    # T2.7: jami summalar UZS ekvivalentida (avval turli valyutalar to'g'ridan-to'g'ri qo'shilardi)
    from app.services.currency_service import rate_map, to_uzs
    _rates = rate_map(db, cid)
    income = float(sum((to_uzs(v, c, _rates) for c, v in income_by_curr.items()), Decimal("0")))
    expense = float(sum((to_uzs(v, c, _rates) for c, v in expense_by_curr.items()), Decimal("0")))

    from app.models.company import Company
    comp = db.query(Company).filter(Company.id == cid).first() if cid else None

    balance_by_curr = {k: income_by_curr.get(k, 0) - expense_by_curr.get(k, 0) for k in set(income_by_curr) | set(expense_by_curr)}

    return {
        "company_name": comp.name if comp else "Tizim",
        "org_code": comp.org_code if comp else "-",
        "total_income": income,
        "total_expense": expense,
        "total_income_uzs": income,
        "total_expense_uzs": expense,
        "balance_uzs": income - expense,
        "income_by_currency": income_by_curr,
        "expense_by_currency": expense_by_curr,
        "balance_by_currency": balance_by_curr,
        "balance": float(str(comp.balance or 0)) if comp else 0,
    }


# ─── Transactions ──────────────────────────────────────────────────────────────

def _scope_tx_branch(q, ctx: BranchContext, user: User, branch_id: Optional[int]):
    """To'lovlar ro'yxatiga filial filtri (T2.5). `branch_id` ixtiyoriy (-1 — filialsiz); cheklangan
    foydalanuvchi (T2.1) ruxsat etilmagan filialni so'rasa 403, parametrsiz esa faqat o'z filiallari
    qatorlarini oladi. Cheklanmagan foydalanuvchi parametrsiz butun korxonani ko'radi."""
    if branch_id:
        if ctx.allowed_branch_ids is not None and branch_id not in ctx.allowed_branch_ids:
            raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        return q.filter(branch_condition(Transaction.branch_id, user.company_id, branch_id))
    ids = ctx.scope_ids()
    if ids is None:
        return q
    return q.filter(Transaction.branch_id.in_(list(ids)))


def _filter_wallet_ptype(q, wallet_id: Optional[int], payment_type: Optional[str]):
    """To'lovlar ro'yxatiga kassa va to'lov turi filtri (T3.6). Kassa korxona doirasida (so'rovda
    `company_id` filtri bor — begona kassa bo'sh natija beradi). Turi 'cash' — NULL ham naqd hisoblanadi."""
    if wallet_id:
        q = q.filter(Transaction.wallet_id == wallet_id)
    if payment_type:
        pt = payment_type.strip().lower()
        if pt == "cash":
            q = q.filter(or_(Transaction.payment_type == "cash", Transaction.payment_type.is_(None)))
        elif pt:
            q = q.filter(Transaction.payment_type == pt)
    return q


# To'lovlar hisoboti: summary butun filtrlangan to'plam bo'yicha SQL agregatdan (limit/skip dan mustaqil)
SUPPLIER_PAY_REFS = ("supplier_payment", "kirim", "purchase_order")


def _norm_ptype(ptype) -> str:
    return (ptype or "cash").lower()


def _add_ptype(summary: dict, ptype, amount: float) -> None:
    """To'lov turi bo'yicha jamilar (naqd/plastik/bank/payme/click/uzum)."""
    if ptype == "cash":
        summary["naqd"] += amount
    elif ptype == "card":
        summary["plastik"] += amount
    elif ptype in ("bank", "bank_transfer"):
        summary["bank"] += amount
    elif ptype == "payme":
        summary["payme"] += amount
    elif ptype == "click":
        summary["click"] += amount
    elif ptype == "uzum":
        summary["uzum"] += amount


def _add_by_ptype(by_pt: dict, ptype: str, code: str, raw: float, uzs: float) -> None:
    """`summary_by_payment_type`: {to'lov_turi: {umumiy (UZS ekvivalent), by_currency: {kod: asl summa}}}.
    Barcha turlar (uzcard, humo, visa, keshbek ham) alohida kalitda — faqat 'umumiy'ga tushib ketmaydi."""
    e = by_pt.setdefault(ptype, {"umumiy": 0.0, "by_currency": {}})
    e["umumiy"] += uzs
    e["by_currency"][code] = e["by_currency"].get(code, 0.0) + raw


def _income_summary(db: Session, q, company_id):
    """Kirim to'lovlari jamilari — butun filtrlangan to'plam bo'yicha (bitta GROUP BY so'rovi).

    Qaytaradi: `(summary UZS ekvivalentida, summary_by_currency, summary_by_payment_type)`.
    Valyutalar aralashmaydi: `summary` — kurs bo'yicha UZS ekvivalent, `summary_by_currency` — asl valyutada.
    Sahifalash (skip/limit) ta'sir qilmaydi."""
    from app.services.currency_service import norm_code, rate_map, to_uzs
    rates = rate_map(db, company_id)
    rows = q.order_by(None).with_entities(
        Transaction.payment_type, Transaction.reference_type, Transaction.currency_code,
        func.coalesce(func.sum(Transaction.amount), 0),
    ).group_by(Transaction.payment_type, Transaction.reference_type, Transaction.currency_code).all()
    summary = {
        "naqd": 0.0, "plastik": 0.0, "bank": 0.0, "payme": 0.0, "click": 0.0, "uzum": 0.0, "umumiy": 0.0,
        "sotuv_summasi": 0.0, "mijoz_qarz_yopish": 0.0, "taminotchi_qaytaruv": 0.0,
    }
    by_cur: dict = {}
    by_pt: dict = {}
    for ptype, rtype, cur, total in rows:
        ptype = _norm_ptype(ptype)
        code = norm_code(cur)
        raw = float(total or 0)
        uzs = float(to_uzs(total, code, rates))
        _add_by_ptype(by_pt, ptype, code, raw, uzs)
        if rtype == "customer_payment":
            summary["mijoz_qarz_yopish"] += uzs
        elif rtype == "return_to_supplier":
            summary["taminotchi_qaytaruv"] += uzs
        elif rtype == "sale":
            summary["sotuv_summasi"] += uzs
        _add_ptype(summary, ptype, uzs)
        summary["umumiy"] += uzs
        # Valyuta kesimi (Kirim to'lovlar sahifasi jami kartochkalari)
        c = by_cur.setdefault(code, {
            "naqd": 0.0, "plastik": 0.0, "bank": 0.0, "umumiy": 0.0, "sotuv": 0.0, "qarz_yopish": 0.0, "qaytaruv": 0.0,
        })
        c["umumiy"] += raw
        if ptype in ("cash", "naqd"):
            c["naqd"] += raw
        elif ptype in ("card", "plastik", "uzcard", "humo"):
            c["plastik"] += raw
        elif ptype in ("bank", "bank_transfer"):
            c["bank"] += raw
        if rtype == "customer_payment":
            c["qarz_yopish"] += raw
        elif rtype == "sale":
            c["sotuv"] += raw
        elif rtype == "return_to_supplier":
            c["qaytaruv"] += raw
    return summary, by_cur, by_pt


def _expense_tx_currencies(db: Session, txs) -> tuple:
    """Chiqim tranzaksiyalari valyutasi: `({tx.id: kod}, {supplier.id: Supplier}, {tx.id: supplier_id})`.

    Faqat eski (meta siz) ta'minotchi to'lovlarida valyuta yozilmagan bo'lishi mumkin — ta'minotchi
    qarzi valyutasidan taxmin qilinadi (xarid to'lovida `reference_id` — xarid ID si)."""
    from app.models.purchase_order import PurchaseOrder
    po_ids = [tx.reference_id for tx in txs if tx.reference_type == "purchase_order" and tx.reference_id]
    po_supplier = dict(db.query(PurchaseOrder.id, PurchaseOrder.supplier_id).filter(PurchaseOrder.id.in_(po_ids)).all()) if po_ids else {}

    def supplier_of(tx):
        return po_supplier.get(tx.reference_id) if tx.reference_type == "purchase_order" else tx.reference_id

    supplier_ids = {supplier_of(tx) for tx in txs if tx.reference_type in SUPPLIER_PAY_REFS and tx.reference_id}
    supplier_ids.discard(None)
    suppliers_obj = {s.id: s for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()} if supplier_ids else {}

    codes = {}
    tx_supplier = {}
    for tx in txs:
        tx_currency = getattr(tx, "currency_code", None)
        sid = supplier_of(tx) if tx.reference_type in SUPPLIER_PAY_REFS else None
        tx_supplier[tx.id] = sid
        if (not tx_currency or tx_currency == "UZS") and tx.meta is None:
            if tx.reference_type in SUPPLIER_PAY_REFS and tx.reference_id:
                sup = suppliers_obj.get(sid)
                if sup:
                    # debt_balances da UZS dan boshqa valyuta bormi?
                    db_map = sup.debt_balances or {}
                    non_uzs = [c for c, v in db_map.items() if c != "UZS" and float(v or 0) >= 0]
                    if non_uzs:
                        tx_currency = non_uzs[0]
                    elif sup.debt_currency and sup.debt_currency != "UZS":
                        tx_currency = sup.debt_currency
        codes[tx.id] = tx_currency or "UZS"
    return codes, suppliers_obj, tx_supplier


def _expense_summary(db: Session, q, company_id) -> tuple:
    """Chiqim to'lovlari jamilari — butun filtrlangan to'plam bo'yicha.
    Qaytaradi: `(summary UZS ekvivalentida, summary_by_currency, summary_by_payment_type)`.

    Asosiy qism bitta GROUP BY so'rovi. Faqat UZS/valyutasiz ta'minotchi to'lovlari (eski yozuvlarda valyuta
    ta'minotchi qarzidan taxmin qilinadi) alohida, valyutasi aniqlanib qo'shiladi."""
    from app.services.currency_service import norm_code, rate_map, to_uzs
    rates = rate_map(db, company_id)
    summary = {
        "naqd": 0.0, "plastik": 0.0, "bank": 0.0, "payme": 0.0, "click": 0.0, "uzum": 0.0, "umumiy": 0.0,
        "taminotchi_qarz_yopish": 0.0, "xarajat": 0.0, "mijozga_qaytaruv": 0.0,
    }

    by_cur: dict = {}
    by_pt: dict = {}

    def add(rtype, ptype, uzs: float, raw: float, code: str):
        ptype = _norm_ptype(ptype)
        if rtype in SUPPLIER_PAY_REFS:
            summary["taminotchi_qarz_yopish"] += uzs
        elif rtype == "sale_refund":
            summary["mijozga_qaytaruv"] += uzs
        elif rtype == "expense":
            summary["xarajat"] += uzs
        _add_ptype(summary, ptype, uzs)
        summary["umumiy"] += uzs
        _add_by_ptype(by_pt, ptype, code, raw, uzs)
        # Valyuta kesimi (Chiqim to'lovlar sahifasi jami kartochkalari) — asl valyutada
        c = by_cur.setdefault(code, {
            "naqd": 0.0, "plastik": 0.0, "bank": 0.0, "umumiy": 0.0, "taminotchi": 0.0, "xarajat": 0.0, "qaytaruv": 0.0,
        })
        c["umumiy"] += raw
        if ptype in ("cash", "naqd"):
            c["naqd"] += raw
        elif ptype in ("card", "plastik", "uzcard", "humo"):
            c["plastik"] += raw
        elif ptype in ("bank", "bank_transfer"):
            c["bank"] += raw
        if rtype in SUPPLIER_PAY_REFS:
            c["taminotchi"] += raw
        elif rtype == "expense":
            c["xarajat"] += raw
        elif rtype == "sale_refund":
            c["qaytaruv"] += raw

    legacy_cond = and_(
        Transaction.reference_type.in_(SUPPLIER_PAY_REFS),
        or_(Transaction.currency_code.is_(None), Transaction.currency_code == "UZS"),
    )
    rows = q.order_by(None).filter(or_(Transaction.reference_type.is_(None), ~legacy_cond)).with_entities(
        Transaction.payment_type, Transaction.reference_type, Transaction.currency_code,
        func.coalesce(func.sum(Transaction.amount), 0),
    ).group_by(Transaction.payment_type, Transaction.reference_type, Transaction.currency_code).all()
    for ptype, rtype, cur, total in rows:
        code = norm_code(cur)
        add(rtype, ptype, float(to_uzs(total, code, rates)), float(total or 0), code)

    legacy = q.order_by(None).filter(legacy_cond).all()
    if legacy:
        codes, _sup, _tx_sup = _expense_tx_currencies(db, legacy)
        for tx in legacy:
            code = norm_code(codes[tx.id])
            add(tx.reference_type, tx.payment_type, float(to_uzs(tx.amount, code, rates)), float(tx.amount or 0), code)
    return summary, by_cur, by_pt


@router.get("/payments/income")
def get_income_payments(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = Query(None, description="Filial (-1 — filialsiz); bo'sh — filtrsiz"),
    wallet_id: Optional[int] = Query(None, description="Kassa"),
    payment_type: Optional[str] = Query(None, description="To'lov turi (cash, card, ...)"),
    customer_id: Optional[int] = Query(None, description="Faqat shu mijozning to'lovlari (mijoz to'lovi va uning sotuvlari)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000),
    response: Response = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Kirim to'lovlari. T2.8: `summary` (va `summary_by_currency`) limitdan mustaqil — butun filtrlangan
    davr bo'yicha SQL agregatdan; `items` — `skip/limit` sahifasi, jami soni `total` va `X-Total-Count`."""
    q = db.query(Transaction).filter(Transaction.type == "income", tx_cash_flow_filter(), Transaction.voided_at.is_(None))
    if user.role.value != "super_admin":
        q = q.filter(Transaction.company_id == user.company_id)
    if date_from:
        q = q.filter(Transaction.created_at >= _parse_dt_start(date_from))
    if date_to:
        q = q.filter(Transaction.created_at < _parse_dt_end(date_to))
    q = _scope_tx_branch(q, effective_ctx(user, ctx), user, branch_id)  # T2.1: reports.all_branches
    q = _filter_wallet_ptype(q, wallet_id, payment_type)
    if customer_id:
        # T3.8: mijoz kartasi uchun — butun korxona ro'yxatini klientda filtrlash o'rniga serverda
        sale_ids_sq = db.query(Sale.id).filter(Sale.customer_id == customer_id)
        if user.role.value != "super_admin":
            sale_ids_sq = sale_ids_sq.filter(Sale.company_id == user.company_id)
        q = q.filter(or_(
            and_(Transaction.reference_type == "customer_payment", Transaction.reference_id == customer_id),
            and_(Transaction.reference_type == "sale", Transaction.reference_id.in_(sale_ids_sq.subquery().select())),
        ))

    total = q.order_by(None).count()
    summary, summary_by_currency, summary_by_payment_type = _income_summary(db, q, user.company_id)
    txs = (
        q.options(joinedload(Transaction.wallet), joinedload(Transaction.branch))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc()).offset(skip).limit(limit).all()
    )
    if response is not None:
        response.headers["X-Total-Count"] = str(total)

    items = []
    customer_ids = [tx.reference_id for tx in txs if tx.reference_type == "customer_payment" and tx.reference_id]
    supplier_ids = [tx.reference_id for tx in txs if tx.reference_type == "return_to_supplier" and tx.reference_id]
    sale_ids = [tx.reference_id for tx in txs if tx.reference_type == "sale" and tx.reference_id]

    customers = {c.id: c.name for c in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()} if customer_ids else {}
    suppliers = {s.id: s.name for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()} if supplier_ids else {}
    sales = {s.id: s.customer_id for s in db.query(Sale).filter(Sale.id.in_(sale_ids)).all()} if sale_ids else {}

    sale_customer_ids = [cid for cid in sales.values() if cid]
    if sale_customer_ids:
        scustomers = {c.id: c.name for c in db.query(Customer).filter(Customer.id.in_(sale_customer_ids)).all()}
        customers.update(scustomers)

    for tx in txs:
        contragent = "Noma'lum"
        turi = "Boshqa"

        if tx.reference_type == "customer_payment":
            contragent = customers.get(tx.reference_id, "Noma'lum Mijoz")
            turi = "Mijoz"
        elif tx.reference_type == "return_to_supplier":
            contragent = suppliers.get(tx.reference_id, "Noma'lum Ta'minotchi")
            turi = "Ta'minotchi"
        elif tx.reference_type == "sale":
            cid = sales.get(tx.reference_id)
            if cid:
                contragent = customers.get(cid, "Noma'lum Mijoz")
            turi = "Mijoz"

        ptype = _norm_ptype(tx.payment_type)
        wallet_name = tx.wallet.name if tx.wallet else "Noma'lum Kassa"

        items.append({
            "id": tx.id,
            "contragent": contragent,
            "turi": turi,
            "amount": float(tx.amount),
            "currency_code": tx.currency_code or "UZS",
            "payment_type": ptype,
            "reference_type": tx.reference_type,
            "description": tx.description,
            "wallet": wallet_name,
            "wallet_id": tx.wallet_id,
            "reference_id": tx.reference_id,
            # T2.6: mijoz kartasi ism bo'yicha emas, id bo'yicha filtrlaydi
            "customer_id": (
                tx.reference_id if tx.reference_type == "customer_payment"
                else (sales.get(tx.reference_id) if tx.reference_type == "sale" else None)
            ),
            "branch_id": tx.branch_id,
            "branch_name": tx.branch.name if tx.branch else None,
            "created_at": tx.created_at.isoformat() if tx.created_at else None
        })

    return {
        "items": items, "summary": summary, "summary_by_currency": summary_by_currency,
        "summary_by_payment_type": summary_by_payment_type, "total": total,
    }


@router.get("/payments/expense")
def get_expense_payments(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = Query(None, description="Filial (-1 — filialsiz); bo'sh — filtrsiz"),
    wallet_id: Optional[int] = Query(None, description="Kassa"),
    payment_type: Optional[str] = Query(None, description="To'lov turi (cash, card, ...)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=5000),
    response: Response = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Chiqim to'lovlari. T2.8: `summary` limitdan mustaqil (butun filtrlangan davr, UZS ekvivalentida);
    `items` — `skip/limit` sahifasi, jami soni `total` va `X-Total-Count`."""
    q = db.query(Transaction).filter(Transaction.type == "expense", tx_cash_flow_filter(), Transaction.voided_at.is_(None))
    if user.role.value != "super_admin":
        q = q.filter(Transaction.company_id == user.company_id)
    if date_from:
        q = q.filter(Transaction.created_at >= _parse_dt_start(date_from))
    if date_to:
        q = q.filter(Transaction.created_at < _parse_dt_end(date_to))
    q = _scope_tx_branch(q, effective_ctx(user, ctx), user, branch_id)  # T2.1: reports.all_branches
    q = _filter_wallet_ptype(q, wallet_id, payment_type)

    total = q.order_by(None).count()
    summary, summary_by_currency, summary_by_payment_type = _expense_summary(db, q, user.company_id)
    txs = (
        q.options(joinedload(Transaction.wallet), joinedload(Transaction.branch))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc()).offset(skip).limit(limit).all()
    )
    if response is not None:
        response.headers["X-Total-Count"] = str(total)

    items = []
    currency_codes, suppliers_obj, tx_supplier = _expense_tx_currencies(db, txs)
    suppliers = {sid: s.name for sid, s in suppliers_obj.items()}
    customer_ids = [tx.reference_id for tx in txs if tx.reference_type == "sale_refund" and tx.reference_id]
    expense_ids = [tx.reference_id for tx in txs if tx.reference_type == "expense" and tx.reference_id]

    customers = {c.id: c.name for c in db.query(Customer).filter(Customer.id.in_(customer_ids)).all()} if customer_ids else {}
    expenses_db = {e.id: e.category.name for e in db.query(Expense).filter(Expense.id.in_(expense_ids)).all() if e.category} if expense_ids else {}

    for tx in txs:
        contragent = "Noma'lum"
        turi = "Boshqa"
        currency_code = currency_codes[tx.id]

        if tx.reference_type in SUPPLIER_PAY_REFS:
            contragent = suppliers.get(tx_supplier.get(tx.id), "Noma'lum Ta'minotchi")
            turi = "Ta'minotchi"
        elif tx.reference_type == "sale_refund":
            contragent = customers.get(tx.reference_id, "Noma'lum Mijoz")
            turi = "Mijoz"
        elif tx.reference_type == "expense":
            contragent = expenses_db.get(tx.reference_id, "Xarajat")
            turi = "Xarajat"

        ptype = _norm_ptype(tx.payment_type)
        wallet_name = tx.wallet.name if tx.wallet else "Noma'lum Kassa"

        items.append({
            "id": tx.id,
            "contragent": contragent,
            "turi": turi,
            "amount": float(tx.amount),
            "currency_code": currency_code,
            "payment_type": ptype,
            "reference_type": tx.reference_type,
            "description": tx.description,
            "wallet": wallet_name,
            "wallet_id": tx.wallet_id,
            "branch_id": tx.branch_id,
            "branch_name": tx.branch.name if tx.branch else None,
            "created_at": tx.created_at.isoformat() if tx.created_at else None
        })

    return {
        "items": items, "summary": summary, "summary_by_currency": summary_by_currency,
        "summary_by_payment_type": summary_by_payment_type, "total": total,
    }


@router.get("/transactions")
def list_transactions(
    branch_id: Optional[int] = None,
    tx_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    include_voided: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    response: Response = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    """T2.8: `skip/limit` (standart 500, eng ko'pi 2000); javob massivligicha qoladi, jami soni `X-Total-Count`."""
    q = db.query(Transaction)
    # T1.19: bekor qilingan (void) tranzaksiyalar ko'rsatilmaydi; include_voided=true — faqat admin/director
    if not (include_voided and _can_see_voided(user)):
        q = q.filter(Transaction.voided_at.is_(None))
    if user.role.value != "super_admin":
        q = q.filter(Transaction.company_id == user.company_id)
    branch_id = resolve_report_scope(db, user, branch_id).branch_id  # T2.1: cheklangan menejer — o'z filiali
    if branch_id:
        q = q.filter(branch_condition(Transaction.branch_id, user.company_id, branch_id))
    if tx_type:
        q = q.filter(Transaction.type == tx_type)
    if date_from:
        q = q.filter(Transaction.created_at >= _parse_dt_start(date_from))
    if date_to:
        q = q.filter(Transaction.created_at < _parse_dt_end(date_to))
    if response is not None:
        response.headers["X-Total-Count"] = str(q.order_by(None).count())
    return q.order_by(Transaction.created_at.desc(), Transaction.id.desc()).offset(skip).limit(limit).all()


@router.post("/transactions", status_code=status.HTTP_201_CREATED)
def create_transaction(
    data: TransactionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_module_roles("finance", *FINANCE_ROLES)),
):
    # Faqat qo'lda kiritiladigan havola turlari — sotuv/mijoz to'lovi kabi tizim yozuvini
    # bu yerdan soxtalashtirib bo'lmaydi (keyin DELETE bilan mijoz qarzini o'zgartirardi)
    if data.reference_type not in MANUAL_TX_REFERENCE_TYPES:
        raise HTTPException(status_code=400, detail="Havola turi noto'g'ri: faqat other_income yoki other_expense")
    # Kassa — o'z korxonasiniki bo'lishi shart (begona bo'lsa 404)
    wallet = get_company_wallet(db, data.wallet_id, user.company_id, for_update=True)
    branch_id = _resolve_tx_branch(db, user, explicit_branch_id=data.branch_id, wallet=wallet)
    currency = (data.currency_code or "UZS").strip().upper() or "UZS"
    payment_type = data.payment_type or "cash"

    # T2.8: yagona `cash_service.post_cash` — Transaction + KassaMovement + Wallet.balance (faqat UZS).
    # Havolasiz yozuv: tranzaksiya reference_id siz, kassa harakati esa tranzaksiyaning o'zi bilan bog'lanadi.
    tx = cash_service.post_cash(
        db, user=user, wallet=wallet, direction="in" if data.type == "income" else "out",
        amount=data.amount, currency=currency, payment_type=payment_type,
        reference_type=data.reference_type, reference_id=None, description=data.description,
        branch_id=branch_id, link_movement_to_tx=True,
    )

    log_action_for(db, user, "TRANSACTION_CREATE", "transaction", tx.id,
                   new_values=_tx_audit(tx), branch_id=branch_id)
    db.commit()
    db.refresh(tx)
    return tx


class TransactionUpdate(BaseModel):
    amount: float = Field(gt=0)
    payment_type: Optional[str] = None
    wallet_id: Optional[int] = None
    description: Optional[str] = None


@router.put("/transactions/{tx_id}")
def update_transaction(
    tx_id: int,
    data: TransactionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
):
    from app.models.customer import Customer
    from app.models.supplier import Supplier
    from app.models.moliya import Expense, KassaMovement

    tx = db.get(Transaction, tx_id)
    if not tx or tx.voided_at is not None or (user.role.value != "super_admin" and tx.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Tranzaksiya topilmadi")
    if tx.reference_type in SYSTEM_TX_TYPES:
        raise HTTPException(status_code=400, detail=SYSTEM_TX_LOCKED)
    is_uzs = (tx.currency_code or "UZS").upper() == "UZS"
    old_audit = _tx_audit(tx)

    if tx.reference_type == "customer_payment":
        # Mijoz to'lovi qarz taqsimoti (FIFO, valyuta chelaklari), jurnal va kassa harakati bilan bog'langan —
        # summa/kassani bu yerda o'zgartirish ularni buzardi (T2.6). Faqat izoh va to'lov turi.
        if abs(Decimal(str(data.amount)) - Decimal(str(tx.amount or 0))) >= Decimal("0.01") or data.wallet_id != tx.wallet_id:
            raise HTTPException(status_code=400, detail="Mijoz to'lovining summasini o'zgartirib bo'lmaydi — o'chirib, qaytadan kiriting")
        mv = cash_service.find_kassa_movement(db, tx)
        if data.payment_type:
            tx.payment_type = str(data.payment_type)
            if mv:
                mv.payment_type = str(data.payment_type)
        if data.description is not None:
            tx.description = str(data.description)
            if mv:
                mv.description = str(data.description)
        log_action_for(db, user, "TRANSACTION_UPDATE", "transaction", tx.id,
                       old_values=old_audit, new_values=_tx_audit(tx), branch_id=tx.branch_id)
        db.commit()
        db.refresh(tx)
        return tx

    if tx.reference_type in SUPPLIER_TX_TYPES:
        # Ta'minotchi to'lovlari qarz taqsimoti, xarid va kassa harakati bilan bog'langan —
        # summa/kassani bu yerda o'zgartirish ularni buzardi. Faqat izoh va to'lov turi.
        if abs(Decimal(str(data.amount)) - Decimal(str(tx.amount or 0))) >= Decimal("0.01") or data.wallet_id != tx.wallet_id:
            raise HTTPException(status_code=400, detail="Ta'minotchi to'lovining summasi yoki kassasini o'zgartirib bo'lmaydi — o'chirib, qaytadan kiriting")
        mv = cash_service.find_kassa_movement(db, tx)
        if data.payment_type:
            tx.payment_type = str(data.payment_type)
            if mv:
                mv.payment_type = str(data.payment_type)
        if data.description is not None:
            tx.description = str(data.description)
            if mv:
                mv.description = str(data.description)
        log_action_for(db, user, "TRANSACTION_UPDATE", "transaction", tx.id,
                       old_values=old_audit, new_values=_tx_audit(tx), branch_id=tx.branch_id)
        db.commit()
        db.refresh(tx)
        return tx

    old_amount = float(tx.amount)
    new_amount = float(data.amount)
    diff = new_amount - old_amount

    # Kassa harakati — summa/kassa o'zgarishidan OLDIN topiladi (mos kelish summa va hamyon bo'yicha).
    # Avval (reference_type, reference_id).first() edi — bir sotuvdagi boshqa to'lov harakati o'zgarib ketardi.
    mv = _find_tx_kassa_movement(db, tx)

    # Wallet updates (yangi kassa — korxona bo'yicha tekshiriladi, begona bo'lsa 404).
    # Hamyon balansi faqat UZS tranzaksiyalarda o'zgaradi.
    wallet_changed = tx.wallet_id != data.wallet_id
    if wallet_changed:
        new_w = get_company_wallet(db, data.wallet_id, user.company_id, for_update=True)
        if tx.wallet_id and is_uzs:
            old_w = find_company_wallet(db, tx.wallet_id, user.company_id)
            if old_w:
                if tx.type == "income": old_w.balance = float(old_w.balance) - old_amount
                else: old_w.balance = float(old_w.balance) + old_amount
        if new_w and is_uzs:
            if tx.type == "income": new_w.balance = float(new_w.balance) + new_amount
            else: new_w.balance = float(new_w.balance) - new_amount
    else:
        if tx.wallet_id and diff != 0 and is_uzs:
            w = find_company_wallet(db, tx.wallet_id, user.company_id)
            if w:
                if tx.type == "income": w.balance = (Decimal(str(w.balance or 0)) + Decimal(str(diff)))
                else: w.balance = (Decimal(str(w.balance or 0)) - Decimal(str(diff)))

    # References update
    if diff != 0:
        if tx.reference_type == "expense" and tx.reference_id:
            expense = db.query(Expense).filter(Expense.id == tx.reference_id, Expense.company_id == tx.company_id).first()
            if expense:
                expense.amount = Decimal(str(new_amount))
                # T2.7: UZS ekvivalent saqlangan kurs bilan qayta hisoblanadi
                expense.amount_uzs = (Decimal(str(new_amount)) * Decimal(str(expense.exchange_rate or 1))).quantize(Decimal("0.01"))
                if wallet_changed:
                    expense.wallet_id = data.wallet_id

    tx.amount = Decimal(str(new_amount))
    if data.payment_type:
        tx.payment_type = str(data.payment_type)  # type: ignore[assignment]
    tx.wallet_id = data.wallet_id  # type: ignore[assignment]
    if data.description is not None:
        tx.description = str(data.description) if data.description is not None else tx.description

    # Sync KassaMovement if exists
    if mv:
        mv.amount = Decimal(str(new_amount))
        if data.payment_type:
            mv.payment_type = str(data.payment_type)
        if wallet_changed:
            mv.wallet_id = data.wallet_id
            mv.session_id = _open_session_id(db, data.wallet_id)
        if data.description is not None:
            mv.description = str(data.description) if data.description is not None else mv.description

    log_action_for(db, user, "TRANSACTION_UPDATE", "transaction", tx.id,
                   old_values=old_audit, new_values=_tx_audit(tx), branch_id=tx.branch_id)
    db.commit()
    db.refresh(tx)
    return tx


@router.delete("/transactions/{tx_id}", status_code=204)
def delete_transaction(
    tx_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
):
    from app.models.customer import Customer
    from app.models.supplier import Supplier
    from app.models.moliya import Expense, KassaMovement

    tx = db.get(Transaction, tx_id)
    if not tx or (user.role.value != "super_admin" and tx.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Tranzaksiya topilmadi")
    if tx.voided_at is not None:
        raise HTTPException(status_code=400, detail="Tranzaksiya allaqachon bekor qilingan")
    if tx.reference_type in SYSTEM_TX_TYPES:
        raise HTTPException(status_code=400, detail=SYSTEM_TX_LOCKED)
    old_audit = _tx_audit(tx)
    audit_branch = tx.branch_id

    from app.services import supplier_ledger as ledger

    # ── Ta'minotchi bilan bog'liq to'lovlar: qarz aynan qaytariladi, hamyon faqat UZS da ──
    if tx.reference_type == "purchase_order":
        from app.services.purchase_order_service import remove_po_payment
        remove_po_payment(db, tx)
        log_action_for(db, user, "TRANSACTION_DELETE", "transaction", tx_id,
                       old_values=old_audit, branch_id=audit_branch)
        db.commit()
        return
    if tx.reference_type == "supplier_payment":
        supplier = db.query(Supplier).filter(Supplier.id == tx.reference_id, Supplier.company_id == tx.company_id).first()
        if supplier:
            allocation = (tx.meta or {}).get("allocation")
            if allocation is not None:
                ledger.reverse_allocation(db, supplier, allocation)
            else:  # eski yozuv — to'lov valyutasidagi qarzga qaytaramiz
                ledger.add(db, supplier, tx.currency_code or "UZS", tx.amount)
        cash_service.reverse_cash(db, tx)
        log_action_for(db, user, "TRANSACTION_DELETE", "transaction", tx_id,
                       old_values=old_audit, branch_id=audit_branch)
        db.commit()
        return
    if tx.reference_type == "return_to_supplier" and tx.type == "income":
        from app.services.supplier_return_service import on_refund_tx_deleted
        on_refund_tx_deleted(db, tx)
        cash_service.reverse_cash(db, tx)
        log_action_for(db, user, "TRANSACTION_DELETE", "transaction", tx_id,
                       old_values=old_audit, branch_id=audit_branch)
        db.commit()
        return

    now = datetime.utcnow()

    if tx.reference_type == "customer_payment" and tx.reference_id:
        # T2.6: qarz AYNAN qaytadi — valyuta chelaklari, filiallar va Sale.paid_amount (jurnal + meta.allocation bo'yicha)
        cust_ledger.reverse_payment(db, tx, user)
    elif tx.reference_type == "expense" and tx.reference_id:
        expense = db.query(Expense).filter(Expense.id == tx.reference_id, Expense.company_id == tx.company_id).first()
        if expense:
            # T1.19: xarajat o'chirilmaydi — bekor qilinadi (void)
            expense.voided_at = now
            expense.voided_by = user.id

    # T2.8: yagona `cash_service.reverse_cash(void=True)` — hamyon balansi (faqat UZS) qaytadi, shu tranzaksiyaning
    # kassa harakati (hamyon, summa va vaqt bo'yicha mosi) O'CHIRILMAYDI — teskari harakat yoziladi (T1.19),
    # tranzaksiya va uning teskari juftligi voided
    cash_service.reverse_cash(
        db, tx, user=user, void=True, now=now, reference_type="transaction_void", reference_id=tx.id,
        description=f"Tranzaksiya bekor qilindi (ID: {tx.id})",
    )
    log_action_for(db, user, "TRANSACTION_VOID", "transaction", tx.id,
                   old_values=old_audit, new_values={"voided": True}, branch_id=tx.branch_id,
                   company_id=tx.company_id)
    db.commit()


# ─── Debitor boshqaruvi (Mijozlar qarzi) ─────────────────────────────────────

@router.get("/customer-debts")
def get_customer_debts(
    branch_id: Optional[int] = Query(None, description="Filial (-1 — filialsiz); bo'sh — butun korxona"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Qarzdor mijozlar ro'yxati.

    T2.6: `branch_id` berilsa — shu filial jurnali (`customer_debt_log`) bo'yicha sof qarz (mijoz bir necha
    filialda qarzdor bo'lsa har filial alohida qator); berilmasa butun korxona va qo'shimcha `by_branch` +
    `unassigned` (filiallar yig'indisi `total_debt` ga teng). `overdue` — to'lanmagan qoldiq
    `total_amount - paid_amount * kurs` bo'yicha (`paid_amount` sotuv valyutasida)."""
    from app.utils.report_utils import sale_branch_filter, sale_rate

    cid = user.company_id
    scoped = None
    bid = None
    if cid is not None:
        bid, allowed = cust_ledger.check_branch_scope(db, user, effective_ctx(user, ctx), branch_id)
        if bid or allowed is not None:
            scoped = cust_ledger.debt_by_branch(db, cid, bid, allowed)

    if scoped is not None:
        rows = scoped["customers"]
        names = scoped["branch_names"]
        customer_ids = list({r["customer"].id for r in rows})
    else:
        cq = db.query(Customer).filter(Customer.debt_balance > 0)
        if user.role.value != "super_admin":
            cq = cq.filter(Customer.company_id == user.company_id)
        customers = cq.order_by(Customer.debt_balance.desc()).all()
        customer_ids = [c.id for c in customers]
        names = {}
        if cid is not None:
            from app.models.branch import Branch
            names = {b.id: b.name for b in db.query(Branch.id, Branch.name).filter(Branch.company_id == cid).all()}

    today = date.today()
    due_dates: dict[int, date | None] = {}
    if customer_ids:
        dq = (
            db.query(Sale.customer_id, func.min(Sale.debt_due_date))
            .filter(
                Sale.customer_id.in_(customer_ids),
                Sale.debt_due_date.isnot(None),
                Sale.total_amount - Sale.paid_amount * sale_rate() > 0.01,
            )
        )
        if bid and cid is not None:
            dq = dq.filter(sale_branch_filter(bid, db, cid))
        due_dates = {r[0]: r[1] for r in dq.group_by(Sale.customer_id).all()}

    total = 0.0
    total_debts = {}
    items = []
    if scoped is not None:
        for r in rows:
            c = r["customer"]
            due = due_dates.get(c.id)
            total += r["debt_uzs"]
            for curr, amt in r["debts"].items():
                total_debts[curr] = total_debts.get(curr, 0.0) + float(amt)
            items.append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "debt_balance": r["debt_uzs"],
                "debt_balances": r["debts"],
                "debt_limit": float(c.debt_limit),
                "earliest_due_date": str(due) if due else None,
                "overdue": bool(due and due < today),
                "branch_id": r["branch_id"],
                "branch_name": names.get(r["branch_id"]) if r["branch_id"] is not None else None,
            })
        count = len(customer_ids)
    else:
        total = sum(float(c.debt_balance) for c in customers)
        for c in customers:
            due = due_dates.get(c.id)

            c_balances = c.debt_balances or {}
            if not c_balances and c.debt_balance and c.debt_balance > 0:
                c_balances = {c.debt_currency or "UZS": float(c.debt_balance)}

            for curr, amt in c_balances.items():
                if float(amt) > 0:
                    total_debts[curr] = total_debts.get(curr, 0.0) + float(amt)

            items.append({
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "debt_balance": float(c.debt_balance),
                "debt_balances": c_balances,
                "debt_limit": float(c.debt_limit),
                "earliest_due_date": str(due) if due else None,
                "overdue": bool(due and due < today),
                "branch_id": c.branch_id,
                "branch_name": names.get(c.branch_id),
            })
        count = len(customers)

    overdue_count = len({i["id"] for i in items if i["overdue"]})
    out = {
        "total_debt": total,
        "total_debts": total_debts,
        "count": count,
        "overdue_count": overdue_count,
        "items": items,
    }
    if scoped is not None:
        out["scope"] = "branch"
        out["branch_id"] = bid
    elif cid is not None:
        full = cust_ledger.debt_by_branch(db, cid)
        out["scope"] = "company"
        out["by_branch"] = full["by_branch"]
        out["unassigned"] = full["unassigned"]
    return out


@router.post("/customer-debts/{customer_id}/pay", status_code=200)
def record_customer_debt_payment(
    customer_id: int,
    data: DebtPaymentIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*DEBT_PAY_ROLES)),
):
    """Mijoz qarzini to'lash — `POST /customers/{id}/pay-debt` bilan BIR XIL servis (`customer_ledger.pay_debt`):
    valyuta kaskadi, sotuvlarga FIFO, kassa yozuvi (to'lov valyutasida), jurnal. Kassa topilmasa 400 (T2.6)."""
    from app.services.customer_service import lock_customer

    customer = lock_customer(db, customer_id, user.company_id)   # boshqa korxona mijozi — 404

    currency = (data.currency or "UZS").strip().upper() or "UZS"
    pay = data.amount
    res = cust_ledger.pay_debt(
        db, customer, user=user,
        payments=[{"amount": pay, "currency": currency, "payment_type": data.payment_type or "cash"}],
        wallet_id=data.wallet_id,
        reason=data.description or f"Mijoz qarzi to'lovi: {customer.name}",
    )
    db.commit()

    # ── Telegram bildirishnoma ──
    try:
        # Kassa/filial: servis tanlagan kassa (to'lov tranzaksiyasi filiali, bo'lmasa kassa filiali)
        pay_wallet_id = res.get("wallet_id")
        pay_tx = db.get(Transaction, res["transaction_ids"][0]) if res.get("transaction_ids") else None
        pay_branch_id = pay_tx.branch_id if pay_tx is not None else None
        if pay_branch_id is None and pay_wallet_id:
            pay_branch_id = db.query(Wallet.branch_id).filter(Wallet.id == pay_wallet_id).scalar()
        location = describe_location(db, branch_id=pay_branch_id, wallet_id=pay_wallet_id)
        msg = "💵 <b>Qarz To'lovi</b>\n" + (f"{location}\n" if location else "")
        msg += f"🤝 Mijoz: {esc(customer.name)}\n💰 Summa: {float(pay):,.0f} {esc(currency)}\n📈 Qolgan qarz: {float(customer.debt_balance):,.0f} UZS"
        background_tasks.add_task(trigger_instant_notification, user.company_id, msg, "finance", pay_branch_id)
    except Exception as e:
        print(f"Telegram notification error: {e}")

    return {
        "customer_id": customer_id,
        "paid": float(pay),
        "currency": currency,
        "remaining_debt": float(customer.debt_balance),
        "debt_balances": res["debt_balances"],
        "transaction_ids": res["transaction_ids"],
        "allocation": res["allocation"],
    }


@router.get("/fix-old-tx-currency")
def fix_old_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.super_admin)),
):
    """Bir martalik ma'lumot tuzatish skripti — barcha kompaniyalarga ta'sir qiladi,
    shuning uchun faqat super_admin ishga tushira oladi (avval login talab qilmasdi)."""
    import re
    from decimal import Decimal
    # Fix all transactions that are UZS but have (amount CURRENCY) in description
    txs = db.query(Transaction).filter(
        Transaction.currency_code == "UZS",
        Transaction.description.like("%(%)%")
    ).all()
    
    count = 0
    pattern = re.compile(r'\(([\d\.,]+)\s+([A-Z]{3})\)\s*$')
    
    for tx in txs:
        if not tx.description: continue
        match = pattern.search(tx.description)
        if match:
            orig_amount_str = match.group(1).replace(',', '')
            orig_amount = float(orig_amount_str)
            orig_currency = match.group(2)
            
            # If the current amount is significantly larger, it means it was converted to UZS
            tx_amount = float(tx.amount) if tx.amount else 0.0  # type: ignore[arg-type]
            if tx_amount > orig_amount * 1000:
                tx.amount = Decimal(str(orig_amount))
                tx.currency_code = orig_currency  # type: ignore[assignment]
                count += 1
            # If amount is small but it was UZS, it might be an old bug where it just didn't set currency
            elif tx_amount == orig_amount:
                tx.currency_code = orig_currency  # type: ignore[assignment]
                count += 1

    # Check the old logic for sales just in case
    income_txs = db.query(Transaction).filter(
        Transaction.type == "income",
        Transaction.reference_type == "sale",
        Transaction.currency_code == "UZS",
        Transaction.description.ilike("% USD%"),
    ).all()
    income_count = 0
    for tx in income_txs:
        m = re.search(r'\((\d+\.?\d*)\s*USD\)', str(tx.description or ""))
        if m:
            tx.amount = Decimal(m.group(1))
            tx.currency_code = "USD"  # type: ignore[assignment]
            income_count += 1

    db.commit()
    return {"message": f"Fixed {count} generic and {income_count} sale transactions"}

# ─── Kreditor boshqaruvi (Supplier qarzi) ────────────────────────────────────

@router.get("/supplier-debts")
def get_supplier_debts(
    branch_id: Optional[int] = Query(None, description="Filial (-1 — filialsiz ombor); bo'sh — butun korxona"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Qarzimiz bor ta'minotchilar (biror valyutada musbat balans). Avans alohida ko'rsatiladi.

    T2.6: `branch_id` berilsa — shu filial omborlariga olingan xaridlar bo'yicha kreditorlik
    (`supplier_ledger.debt_by_branch`); `unallocated_payments` — xaridlarga bog'lanmagan umumiy to'lovlar."""
    from app.services import supplier_ledger as ledger

    cid = user.company_id
    bid, allowed, by_branch_data = None, None, None
    if cid is not None:
        bid, allowed = cust_ledger.check_branch_scope(db, user, effective_ctx(user, ctx), branch_id)
        by_branch_data = sup_ledger.debt_by_branch(db, cid, bid, allowed)

    # T2.8: kurslar korxona uchun BIR marta olinadi (sikl ichida har ta'minotchi/valyuta uchun so'rov yo'q)
    from app.services.currency_service import rate_map, to_uzs

    if by_branch_data is not None and (bid or allowed is not None):
        names = {b["branch_id"]: b["branch_name"] for b in by_branch_data["by_branch"]}
        from app.models.branch import Branch
        names.update({b.id: b.name for b in db.query(Branch.id, Branch.name).filter(Branch.company_id == cid).all()})
        items = []
        total = 0.0
        total_debts = {}
        for r in by_branch_data["suppliers"]:
            s = r["supplier"]
            total += r["debt_uzs"]
            for curr, amt in r["debts"].items():
                total_debts[curr] = total_debts.get(curr, 0.0) + float(amt)
            items.append({
                "id": s.id,
                "name": s.name,
                "phone": s.phone,
                "debt_balance": r["debt_uzs"],
                "debt_balances": r["debts"],
                "avans_balances": {},
                "payment_terms": s.payment_terms,
                "branch_id": r["branch_id"],
                "branch_name": names.get(r["branch_id"]) if r["branch_id"] is not None else None,
            })
        return {
            "total_debt": float(round(total, 2)),
            "total_debts": total_debts,
            "count": len({i["id"] for i in items}),
            "items": items,
            "scope": "branch",
            "branch_id": bid,
            "by_branch": by_branch_data["by_branch"],
            "unassigned": by_branch_data["unassigned"],
            "unallocated_payments": by_branch_data["unallocated_payments"],
            "unallocated_payments_uzs": by_branch_data["unallocated_payments_uzs"],
        }

    sq = db.query(Supplier).filter(Supplier.is_active == True)
    if user.role.value != "super_admin":
        sq = sq.filter(Supplier.company_id == user.company_id)

    total = Decimal("0")
    total_debts = {}
    items = []
    rates_by_company: dict = {}
    for s in sq.all():
        bal = ledger.balances(s)
        debts = {c: v for c, v in bal.items() if v > 0}
        if not debts:
            continue
        if s.company_id not in rates_by_company:
            rates_by_company[s.company_id] = rate_map(db, s.company_id)
        rates = rates_by_company[s.company_id]
        debt_uzs = sum((to_uzs(v, c, rates) for c, v in debts.items()), Decimal("0"))
        total += debt_uzs
        for curr, amt in debts.items():
            total_debts[curr] = total_debts.get(curr, 0.0) + float(amt)
        items.append({
            "id": s.id,
            "name": s.name,
            "phone": s.phone,
            "debt_balance": float(round(debt_uzs, 2)),
            "debt_balances": {c: float(v) for c, v in debts.items()},
            "avans_balances": {c: float(-v) for c, v in bal.items() if v < 0},
            "payment_terms": s.payment_terms,
        })
    items.sort(key=lambda x: x["debt_balance"], reverse=True)

    out = {
        "total_debt": float(round(total, 2)),
        "total_debts": total_debts,
        "count": len(items),
        "items": items,
    }
    if by_branch_data is not None:
        out["scope"] = "company"
        out["by_branch"] = by_branch_data["by_branch"]
        out["unassigned"] = by_branch_data["unassigned"]
        out["unallocated_payments"] = by_branch_data["unallocated_payments"]
        out["unallocated_payments_uzs"] = by_branch_data["unallocated_payments_uzs"]
    return out


@router.post("/supplier-debts/{supplier_id}/pay", status_code=200)
def record_supplier_debt_payment(
    supplier_id: int,
    data: DebtPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
):
    """Supplier qarzini to'lash — Xaridlar sahifasidagi to'lov bilan bir xil mantiq
    (avval har kim to'lay olardi, kassa harakati yozilmasdi, ortiqcha to'lov yo'qolardi)."""
    from app.services import supplier_ledger as ledger

    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id, Supplier.company_id == user.company_id, Supplier.is_active == True,
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier topilmadi")

    currency = (data.currency or "UZS").strip().upper() or "UZS"
    ledger.pay_supplier(
        db, supplier, user=user, amount=data.amount, currency=currency,
        payment_type=data.payment_type or "cash", wallet_id=data.wallet_id,
        reason=data.description or "Supplier to'lovi",
    )
    db.commit()
    db.refresh(supplier)
    return {
        "supplier_id": supplier_id,
        "paid": float(data.amount),
        "currency": currency,
        "remaining_debt": float(supplier.debt_balance or 0),
        "debt_balances": supplier.debt_balances,
    }


# ─── Foyda va Zarar (P&L) ─────────────────────────────────────────────────────

@router.get("/profit-loss")
def get_profit_loss(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    branch_id: Optional[int] = None,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
):
    """Foyda va Zarar hisoboti (UZS) — `/reports/profit-loss` va `/reports/pnl-compare` bilan bir xil servis
    (`pnl_service.compute_pnl`). `branch_id=-1` — filialsiz guruh. `company_id` faqat super_admin uchun."""
    from app.services.branch_helpers import BRANCH_NOT_FOUND
    from app.services.pnl_service import UNASSIGNED_BRANCH, compute_pnl
    from app.utils.report_utils import _date_range

    cid = user.company_id
    if user.role == UserRole.super_admin:
        cid = company_id or user.company_id
        if cid is None:
            raise HTTPException(status_code=400, detail="Korxonani tanlang (company_id)")
    try:
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Sana formati noto'g'ri (YYYY-MM-DD)")
    if branch_id and branch_id != UNASSIGNED_BRANCH:
        from app.models.branch import Branch
        if not db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first():
            raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
    if user.role != UserRole.super_admin:
        branch_id = resolve_report_scope(db, user, branch_id).branch_id  # T2.1: cheklangan menejer — o'z filiali

    start, end = _date_range(d_from, d_to)
    p = compute_pnl(db, cid, start, end, branch_id)
    return {
        "period": {
            "from": date_from or "boshidan",
            "to": date_to or "hozirga qadar",
        },
        "gross_revenue": p["gross_revenue"],
        "returns": p["returns"],
        "revenue": p["net_revenue"],
        "cogs": p["net_cogs"],
        "gross_profit": p["gross_profit"],
        "gross_margin_pct": p["gross_margin_pct"],
        "other_income": p["other_income"],
        "other_income_note": p["other_income_note"],
        "expenses": p["expenses"],
        "net_profit": p["net_profit"],
        "net_margin_pct": p["net_margin_pct"],
    }
