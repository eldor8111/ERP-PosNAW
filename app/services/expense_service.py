"""T4.6 — xarajat yaratish va tasdiqlash (kassa va moliya routerlari uchun yagona mantiq).

Limit ichidagi xarajat darhol `approved` bo'ladi: `Expense` + `cash_service.post_cash` (KassaMovement,
Transaction, Wallet.balance). Limitdan katta xarajat (`require_approval`) `status="pending"` bilan yoziladi:
kassa harakati, tranzaksiya va hamyon balansi O'ZGARMAYDI; menejer tasdiqlaganda (`approve_pending_expense`)
shu uchta yozuv bir marta yoziladi, rad etilsa (`reject_pending_expense`) hech narsa o'zgarmaydi.
`Expense.created_by` — yaratuvchi, `approved_by` — tasdiqlovchi (limit ichida NULL = avto-tasdiq).
"""
from datetime import timedelta
from decimal import Decimal
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.approval import ApprovalRequest
from app.models.moliya import Expense, Wallet
from app.models.user import User
from app.services import approval_service, cash_service


def _description(expense: Expense, category_name: Optional[str]) -> str:
    return expense.description or category_name or "Xarajat"


def post_expense_cash(db: Session, expense: Expense, poster, *, payment_type: Optional[str], wallet=None,
                      category_name: Optional[str] = None) -> None:
    """Tasdiqlangan xarajat uchun KassaMovement + Transaction + Wallet.balance (kassa.py dagi eski mantiq)."""
    if wallet is None and expense.wallet_id:
        wallet = db.query(Wallet).filter(
            Wallet.id == expense.wallet_id, Wallet.company_id == expense.company_id,
        ).with_for_update().first()
    if category_name is None and expense.category is not None:
        category_name = expense.category.name
    cash_service.post_cash(
        db, user=poster, wallet=wallet, direction="out", amount=expense.amount, currency=expense.currency,
        payment_type=payment_type or "cash", reference_type="expense", reference_id=expense.id,
        description=_description(expense, category_name), branch_id=expense.branch_id,
    )


def create_expense(
    db: Session, *, user, wallet, branch_id: int, category_id: int, category_name: Optional[str], amount,
    currency: str, rate, description: Optional[str], payment_type: str = "cash",
) -> Tuple[Expense, Optional[ApprovalRequest]]:
    """Xarajat yaratadi. Qaytaradi `(expense, approval_request)`: so'rov `None` bo'lsa xarajat `approved` va pul
    yozilgan; aks holda `pending` (pul yozilmagan). `block` qoidasi buzilsa 403 `limit_exceeded`. Commit chaqiruvchida."""
    amount = Decimal(str(amount))
    amount_uzs = (amount * Decimal(str(rate))).quantize(Decimal("0.01"))
    violation = approval_service.evaluate_expense(db, user, branch_id, amount_uzs)
    if violation is not None and violation.mode == "block":
        raise HTTPException(status_code=403, detail=violation.detail("limit_exceeded"))
    pending = violation is not None   # require_approval

    expense = Expense(
        branch_id=branch_id, category_id=category_id, amount=amount, currency=currency, exchange_rate=rate,
        amount_uzs=amount_uzs, company_id=user.company_id, wallet_id=wallet.id if wallet is not None else None,
        description=description, created_by=user.id, approved_by=None,
        status="pending" if pending else "approved",
    )
    db.add(expense)
    db.flush()

    if not pending:
        post_expense_cash(db, expense, user, payment_type=payment_type, wallet=wallet, category_name=category_name)
        return expense, None

    req = approval_service.create_request(
        db, user, action_type="expense", branch_id=branch_id, amount=amount_uzs,
        payload={
            "expense_id": expense.id, "wallet_id": expense.wallet_id, "category_id": category_id,
            "amount": amount, "currency": currency, "payment_type": payment_type, "description": description,
        },
        reason=description or category_name, ttl=timedelta(hours=approval_service.EXPENSE_TTL_HOURS),
        reference_type="expense", reference_id=expense.id,
    )
    expense.approval_request_id = req.id
    return expense, req


def _payment_type_of(db: Session, expense: Expense) -> str:
    if expense.approval_request_id:
        req = db.get(ApprovalRequest, expense.approval_request_id)
        if req is not None and isinstance(req.payload, dict) and req.payload.get("payment_type"):
            return req.payload["payment_type"]
    return "cash"


def approve_pending_expense(db: Session, expense: Expense, approver) -> None:
    """`pending` xarajatni tasdiqlaydi: pul BIR marta yoziladi (hamyon balansi kamayadi). Commit chaqiruvchida."""
    if expense.status != "pending" or expense.voided_at is not None:
        raise HTTPException(status_code=409, detail="Xarajat tasdiqlash holatida emas")
    poster = db.get(User, expense.created_by) if expense.created_by else None
    if poster is None or poster.company_id != expense.company_id:
        poster = approver
    post_expense_cash(db, expense, poster, payment_type=_payment_type_of(db, expense))
    expense.status = "approved"
    expense.approved_by = approver.id
    log_action(
        db, "EXPENSE_APPROVE", "expense", expense.id, user_id=approver.id, company_id=expense.company_id,
        branch_id=expense.branch_id,
        new_values={"amount": float(expense.amount or 0), "currency": expense.currency, "created_by": expense.created_by},
    )


def reject_pending_expense(db: Session, expense: Expense) -> None:
    """Rad etilgan xarajat: hech qanday pul yozuvi qilinmaydi (balans o'zgarmaydi)."""
    if expense.status == "pending":
        expense.status = "rejected"


def cancel_pending_expense(db: Session, expense: Expense, user) -> None:
    """Tasdiq kutayotgan (yoki rad etilgan) xarajatni bekor qilishda: pul yozuvi yo'q, shuning uchun teskari
    harakat kerak emas. Bog'liq `pending` so'rov `rejected` bo'ladi."""
    if expense.status == "pending":
        expense.status = "rejected"
    if expense.approval_request_id:
        req = db.get(ApprovalRequest, expense.approval_request_id)
        if req is not None and req.status == "pending":
            req.status = "rejected"
            req.decided_by = user.id
            req.decision_note = "Xarajat bekor qilindi"
