"""
Finance API — 3-bosqich: Moliya moduli, P&L, Debitor/Kreditor boshqaruvi
"""
# pyright: reportMissingImports=false
# pyright: reportMissingModuleSource=false
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException  # type: ignore
from sqlalchemy.orm import Session  # type: ignore
from sqlalchemy import func  # type: ignore
from pydantic import BaseModel  # type: ignore
from decimal import Decimal

from app.database import get_db  # type: ignore
from app.models.moliya import ExpenseCategory, Expense, Transaction, Wallet  # type: ignore
from app.models.customer import Customer  # type: ignore
from app.models.sale import Sale  # type: ignore
from app.models.supplier import Supplier  # type: ignore
from app.core.dependencies import get_current_user  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.core.dependencies import require_roles  # type: ignore

router = APIRouter(prefix="/finance", tags=["Finance"])

FINANCE_ROLES = (UserRole.admin, UserRole.director, UserRole.accountant, UserRole.manager)


# ─── Yordamchi: satrdan datetime ─────────────────────────────────────────────

def _parse_dt_start(date_str: Optional[str]) -> datetime:
    """'YYYY-MM-DD' → kun boshi datetime"""
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d")
    return datetime(2000, 1, 1)


def _parse_dt_end(date_str: Optional[str]) -> datetime:
    """'YYYY-MM-DD' → kun oxiri datetime (keyingi kun 00:00)"""
    if date_str:
        return datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    return datetime(2100, 1, 1)


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
    branch_id: int
    category_id: int
    amount: Decimal
    wallet_id: Optional[int] = None
    description: Optional[str] = None


class TransactionIn(BaseModel):
    branch_id: int
    type: str  # 'income' or 'expense'
    amount: Decimal
    wallet_id: Optional[int] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    description: Optional[str] = None


class DebtPaymentIn(BaseModel):
    amount: Decimal
    description: Optional[str] = None


# ─── Wallets ──────────────────────────────────────────────────────────────────

@router.get("/wallets")
def list_wallets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Wallet)
    if user.role.value != "super_admin":
        q = q.filter(Wallet.company_id == user.company_id)
    return [
        {
            "id": w.id,
            "name": w.name,
            "type": w.type,
            "balance": float(w.balance),
            "is_active": w.is_active,
            "branch_id": w.branch_id,
            "detailed_balances": {wb.payment_type: float(wb.balance) for wb in w.detailed_balances} if hasattr(w, "detailed_balances") else {}
        }
        for w in q.all()
    ]

@router.post("/wallets", status_code=201)
def create_wallet(
    data: WalletIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    w = Wallet(**data.model_dump())
    w.company_id = user.company_id
    db.add(w)
    db.commit()
    db.refresh(w)
    return w

@router.delete("/wallets/{wallet_id}", status_code=204)
def delete_wallet(
    wallet_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    w = db.get(Wallet, wallet_id)
    if not w:
        raise HTTPException(status_code=404, detail="Not found")
    # Mark as inactive instead of deleting if it has balance
    if w.balance != 0:
        w.is_active = False
    else:
        db.delete(w)
    db.commit()


# ─── Expense Categories ───────────────────────────────────────────────────────

@router.get("/expense-categories")
def list_expense_categories(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ExpenseCategory)
    if user.role.value != "super_admin":
        q = q.filter(ExpenseCategory.company_id == user.company_id)
    return q.all()


@router.post("/expense-categories", status_code=201)
def create_expense_category(
    data: ExpenseCategoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cat = ExpenseCategory(**data.model_dump())
    cat.company_id = user.company_id
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/expense-categories/{cat_id}", status_code=204)
def delete_expense_category(
    cat_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cat = db.get(ExpenseCategory, cat_id)  # SQLAlchemy 2.0 usuli
    if not cat or (user.role.value != "super_admin" and cat.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(cat)
    db.commit()


# ─── Expenses ─────────────────────────────────────────────────────────────────

@router.get("/expenses")
def list_expenses(
    branch_id: Optional[int] = None,
    category_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Expense)
    if user.role.value != "super_admin":
        q = q.filter(Expense.company_id == user.company_id)
    if branch_id:
        q = q.filter(Expense.branch_id == branch_id)
    if category_id:
        q = q.filter(Expense.category_id == category_id)
    if date_from:
        q = q.filter(Expense.created_at >= _parse_dt_start(date_from))
    if date_to:
        q = q.filter(Expense.created_at < _parse_dt_end(date_to))
    results = q.order_by(Expense.created_at.desc()).all()
    return [
        {
            "id": e.id,
            "branch_id": e.branch_id,
            "category_id": e.category_id,
            "category_name": e.category.name if e.category else None,
            "amount": float(e.amount),
            "description": e.description,
            "approved_by": e.approved_by,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in results
    ]


@router.post("/expenses", status_code=201)
def create_expense(
    data: ExpenseIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    expense = Expense(**data.model_dump(), approved_by=user.id, company_id=user.company_id)
    db.add(expense)
    tx = Transaction(
        branch_id=data.branch_id,
        type="expense",
        amount=data.amount,
        wallet_id=data.wallet_id,
        reference_type="expense",
        description=data.description,
    )
    db.add(tx)
    
    if data.wallet_id:
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            wallet.balance = float(wallet.balance) - float(data.amount)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/expenses/{exp_id}", status_code=204)
def delete_expense(
    exp_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exp = db.get(Expense, exp_id)  # SQLAlchemy 2.0 usuli
    if not exp or (user.role.value != "super_admin" and exp.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Not found")

    # Moliya tranzaksiyasini ham o'chirish
    tx = db.query(Transaction).filter(
        Transaction.reference_type == "expense",
        Transaction.reference_id == exp_id,
        Transaction.type == "expense"
    ).first()
    if tx:
        db.delete(tx)

    db.delete(exp)
    db.commit()


# ─── Cash Balance ──────────────────────────────────────────────────────────────

@router.get("/cash-balance")
def get_cash_balance(
    branch_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    def _base(tx_type: str):
        q = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.type == tx_type
        )
        if user.role.value != "super_admin":
            q = q.filter(Transaction.company_id == user.company_id)
        if branch_id:
            q = q.filter(Transaction.branch_id == branch_id)
        if date_from:
            q = q.filter(Transaction.created_at >= _parse_dt_start(date_from))
        if date_to:
            q = q.filter(Transaction.created_at < _parse_dt_end(date_to))
        return float(q.scalar() or 0)

    income = _base("income")
    expense = _base("expense")

    
    from app.models.company import Company
    comp = db.query(Company).filter(Company.id == user.company_id).first() if user.company_id else None
    
    return {
        "company_name": comp.name if comp else "Tizim",
        "org_code": comp.org_code if comp else "-",
        "total_income": income,
        "total_expense": expense,
        "balance": float(comp.balance) if comp else 0,
    }


# ─── Transactions ──────────────────────────────────────────────────────────────

@router.get("/transactions")
def list_transactions(
    branch_id: Optional[int] = None,
    tx_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Transaction)
    if user.role.value != "super_admin":
        q = q.filter(Transaction.company_id == user.company_id)
    if branch_id:
        q = q.filter(Transaction.branch_id == branch_id)
    if tx_type:
        q = q.filter(Transaction.type == tx_type)
    if date_from:
        q = q.filter(Transaction.created_at >= _parse_dt_start(date_from))
    if date_to:
        q = q.filter(Transaction.created_at < _parse_dt_end(date_to))
    return q.order_by(Transaction.created_at.desc()).limit(500).all()


@router.post("/transactions", status_code=201)
def create_transaction(
    data: TransactionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tx = Transaction(**data.model_dump())
    tx.company_id = user.company_id
    db.add(tx)
    
    if data.wallet_id:
        wallet = db.get(Wallet, data.wallet_id)
        if wallet:
            if data.type == "income":
                wallet.balance = float(wallet.balance) + float(data.amount)
            elif data.type == "expense":
                wallet.balance = float(wallet.balance) - float(data.amount)
                
    db.commit()
    db.refresh(tx)
    return tx


# ─── Debitor boshqaruvi (Mijozlar qarzi) ─────────────────────────────────────

@router.get("/customer-debts")
def get_customer_debts(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
):
    """Qarzdor mijozlar ro'yxati"""
    cq = db.query(Customer).filter(Customer.debt_balance > 0)
    if user.role.value != "super_admin":
        cq = cq.filter(Customer.company_id == user.company_id)
    customers = cq.order_by(Customer.debt_balance.desc()).all()
    total = sum(float(c.debt_balance) for c in customers)

    today = date.today()
    customer_ids = [c.id for c in customers]
    due_dates: dict[int, date | None] = {}
    if customer_ids:
        rows = (
            db.query(Sale.customer_id, func.min(Sale.debt_due_date))
            .filter(
                Sale.customer_id.in_(customer_ids),
                Sale.debt_due_date.isnot(None),
                Sale.paid_amount < Sale.total_amount,
            )
            .group_by(Sale.customer_id)
            .all()
        )
        due_dates = {r[0]: r[1] for r in rows}

    items = []
    for c in customers:
        due = due_dates.get(c.id)
        items.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "debt_balance": float(c.debt_balance),
            "debt_limit": float(c.debt_limit),
            "earliest_due_date": str(due) if due else None,
            "overdue": bool(due and due < today),
        })

    overdue_count = sum(1 for i in items if i["overdue"])
    return {
        "total_debt": total,
        "count": len(customers),
        "overdue_count": overdue_count,
        "items": items,
    }


@router.post("/customer-debts/{customer_id}/pay", status_code=200)
def record_customer_debt_payment(
    customer_id: int,
    data: DebtPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mijoz qarzini to'lash"""
    customer = db.get(Customer, customer_id)  # SQLAlchemy 2.0 usuli
    if not customer or (user.role.value != "super_admin" and customer.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Mijoz topilmadi")

    pay = float(data.amount)
    balance = float(customer.debt_balance)
    if pay > balance:
        raise HTTPException(status_code=400, detail="To'lov summasi qarz balansidan katta")

    customer.debt_balance = balance - pay
    # Find user's branch or fallback to company's first branch
    from app.models.branch import Branch as _Branch
    tx_branch_id = user.branch_id
    if not tx_branch_id and user.company_id:
        br = db.query(_Branch).filter(_Branch.company_id == user.company_id).first()
        tx_branch_id = br.id if br else None
    tx = Transaction(
        branch_id=tx_branch_id or 0,
        type="income",
        amount=data.amount,
        company_id=user.company_id,
        reference_type="customer_payment",
        reference_id=customer_id,
        description=data.description or f"Mijoz qarzi to'lovi: {customer.name}",
    )
    db.add(tx)
    db.commit()
    return {
        "customer_id": customer_id,
        "paid": pay,
        "remaining_debt": float(customer.debt_balance),
    }


# ─── Kreditor boshqaruvi (Supplier qarzi) ────────────────────────────────────

@router.get("/supplier-debts")
def get_supplier_debts(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
):
    """Qarzdor supplierlar ro'yxati"""
    sq = db.query(Supplier).filter(Supplier.debt_balance > 0)
    if user.role.value != "super_admin":
        sq = sq.filter(Supplier.company_id == user.company_id)
    suppliers = sq.order_by(Supplier.debt_balance.desc()).all()
    total = sum(float(s.debt_balance) for s in suppliers)
    return {
        "total_debt": total,
        "count": len(suppliers),
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "phone": s.phone,
                "debt_balance": float(s.debt_balance),
                "payment_terms": s.payment_terms,
            }
            for s in suppliers
        ],
    }


@router.post("/supplier-debts/{supplier_id}/pay", status_code=200)
def record_supplier_debt_payment(
    supplier_id: int,
    data: DebtPaymentIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Supplier qarzini to'lash"""
    supplier = db.get(Supplier, supplier_id)  # SQLAlchemy 2.0 usuli
    if not supplier or (user.role.value != "super_admin" and supplier.company_id != user.company_id):
        raise HTTPException(status_code=404, detail="Supplier topilmadi")

    from app.models.branch import Branch as _Branch
    tx_branch_id = user.branch_id
    if not tx_branch_id and supplier.company_id:
        br = db.query(_Branch).filter(_Branch.company_id == supplier.company_id).first()
        tx_branch_id = br.id if br else None
    supplier.debt_balance = float(supplier.debt_balance) - paid
    tx = Transaction(
        branch_id=tx_branch_id or 0,
        type="expense",
        amount=paid,
        company_id=user.company_id,
        reference_type="supplier_payment",
        reference_id=supplier_id,
        description=data.description or f"Supplier to'lovi: {supplier.name}",
    )
    db.add(tx)
    db.commit()
    return {
        "supplier_id": supplier_id,
        "paid": paid,
        "remaining_debt": float(supplier.debt_balance),
    }


# ─── Foyda va Zarar (P&L) ─────────────────────────────────────────────────────

@router.get("/profit-loss")
def get_profit_loss(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*FINANCE_ROLES)),
):
    """Foyda va Zarar hisoboti"""
    from app.models.sale import Sale, SaleItem, SaleStatus  # type: ignore

    start = _parse_dt_start(date_from)
    end = _parse_dt_end(date_to)

    # Daromad (sotuvlardan)
    revenue_q = (
        db.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    if user.role.value != "super_admin":
        revenue_q = revenue_q.filter(Sale.company_id == user.company_id)
    revenue = float(revenue_q.scalar() or 0)

    # Tannarx (COGS)
    cogs_q = (
        db.query(func.coalesce(func.sum(SaleItem.cost_price * SaleItem.quantity), 0))
        .join(Sale)
        .filter(Sale.created_at >= start, Sale.created_at < end, Sale.status == SaleStatus.completed)
    )
    if user.role.value != "super_admin":
        cogs_q = cogs_q.filter(Sale.company_id == user.company_id)
    cogs = float(cogs_q.scalar() or 0)

    gross_profit = revenue - cogs

    # Xarajatlar
    expense_q = (
        db.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(Expense.created_at >= start, Expense.created_at < end)
    )
    if user.role.value != "super_admin":
        expense_q = expense_q.filter(Expense.company_id == user.company_id)
    total_expenses = float(expense_q.scalar() or 0)

    net_profit = gross_profit - total_expenses

    # Xarajatlar kategoriya bo'yicha
    expense_by_cat = (
        db.query(ExpenseCategory.name, func.coalesce(func.sum(Expense.amount), 0).label("total"))
        .join(Expense, Expense.category_id == ExpenseCategory.id)
        .filter(Expense.created_at >= start, Expense.created_at < end)
        .group_by(ExpenseCategory.name)
        .all()
    )

    return {
        "period": {
            "from": date_from or "boshidan",
            "to": date_to or "hozirga qadar",
        },
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": (int(gross_profit / revenue * 10000) / 100) if revenue else 0.0,
        "expenses": {
            "total": total_expenses,
            "by_category": [{"name": r.name, "total": float(r.total)} for r in expense_by_cat],
        },
        "net_profit": net_profit,
        "net_margin_pct": (int(net_profit / revenue * 10000) / 100) if revenue else 0.0,
    }
