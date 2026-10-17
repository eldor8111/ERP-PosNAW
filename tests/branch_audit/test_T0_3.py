"""T0.3 — Wallet IDOR: smena, moliya va tranzaksiyalarda hamyonni korxonaga tekshirish.

Ikki korxona (A, B), har birida o'z kassasi. B foydalanuvchisi A kassasini
`wallet_id` sifatida yuborganda 404 va A kassasi balansi o'zgarmasligi,
o'z kassasi bilan esa amal muvaffaqiyatli bo'lishi tekshiriladi.
"""
import importlib.util
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.customer import Customer
from app.models.moliya import ExpenseCategory, Transaction, Wallet, WalletBalance
from app.models.product import Product
from app.models.sale import Sale, SalePayment, PaymentType
from app.models.shift import Shift
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
WALLET_404 = "Kassa (hamyon) topilmadi"


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, balance=1000, is_active=True, name=None):
    w = Wallet(name=name or f"Kassa {company.id}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=is_active, is_open=True)
    db.add(w)
    db.flush()
    return w


def _category(db, company):
    c = ExpenseCategory(name="Ijara", company_id=company.id)
    db.add(c)
    db.flush()
    return c


def _customer(db, company, debt=5000):
    c = Customer(name=f"Mijoz {company.id}", company_id=company.id,
                 debt_balance=Decimal(debt), debt_balances={"UZS": float(debt)})
    db.add(c)
    db.flush()
    return c


def _shift(db, user, company, branch):
    s = Shift(cashier_id=user.id, branch_id=branch.id, company_id=company.id,
              status="open", opened_at=datetime.now(timezone.utc) )
    db.add(s)
    db.flush()
    return s


def _cash_sale(db, user, company, shift, amount=700):
    s = Sale(number=f"S{shift.id}-{user.id}", cashier_id=user.id, total_amount=Decimal(amount),
             paid_amount=Decimal(amount), paid_cash=Decimal(amount), payment_type=PaymentType.cash,
             company_id=company.id, shift_id=shift.id)
    db.add(s)
    db.flush()
    db.add(SalePayment(sale_id=s.id, payment_type="cash", amount=Decimal(amount)))
    db.flush()
    return s


def _product(db, company):
    p = Product(sku=f"SKU{company.id}", barcode=f"BC{company.id}", name="Tovar", company_id=company.id)
    db.add(p)
    db.flush()
    return p


def _bal(db, wallet):
    db.refresh(wallet)
    return Decimal(str(wallet.balance))


@pytest.fixture
def two(db, mk):
    """A va B korxonalar: har birida filial, ombor, admin va kassa."""
    ca, ba, wha, ua = mk.tenant()
    cb, bb, whb, ub = mk.tenant()
    wa = _wallet(db, ca, ba)
    wb = _wallet(db, cb, bb)
    return dict(ca=ca, ba=ba, wha=wha, ua=ua, wa=wa, cb=cb, bb=bb, whb=whb, ub=ub, wb=wb)


# ─── wallet_access yordamchisi ───────────────────────────────────────────────

def test_helper_get_company_wallet(db, two):
    from fastapi import HTTPException
    from app.services.wallet_access import get_company_wallet, find_company_wallet, get_company_branch
    t = two
    assert get_company_wallet(db, None, t['ca'].id) is None
    assert get_company_wallet(db, t['wa'].id, t['ca'].id).id == t['wa'].id
    with pytest.raises(HTTPException) as e:
        get_company_wallet(db, t['wa'].id, t['cb'].id)
    assert e.value.status_code == 404 and e.value.detail == WALLET_404
    # nofaol kassa
    inactive = _wallet(db, t['ca'], is_active=False, name="Nofaol")
    with pytest.raises(HTTPException):
        get_company_wallet(db, inactive.id, t['ca'].id)
    assert get_company_wallet(db, inactive.id, t['ca'].id, require_active=False).id == inactive.id
    # find — xato bermaydi
    assert find_company_wallet(db, t['wa'].id, t['cb'].id) is None
    assert find_company_wallet(db, t['wa'].id, t['ca'].id).id == t['wa'].id
    # filial
    assert get_company_branch(db, t['ba'].id, t['ca'].id).id == t['ba'].id
    with pytest.raises(HTTPException) as e:
        get_company_branch(db, t['ba'].id, t['cb'].id)
    assert e.value.status_code == 400 and e.value.detail == "Filial topilmadi"


# ─── POST /finance/expenses ──────────────────────────────────────────────────

def test_expense_foreign_wallet_404(client, db, two):
    t = two
    cat_b = _category(db, t['cb'])
    r = client.login(t['ub']).post('/api/finance/expenses', json={
        "branch_id": t['bb'].id, "category_id": cat_b.id, "amount": 300, "wallet_id": t['wa'].id})
    assert r.status_code == 404, r.text
    assert r.json()['detail'] == WALLET_404
    assert _bal(db, t['wa']) == Decimal(1000)
    assert db.query(Transaction).count() == 0


def test_expense_foreign_branch_and_category(client, db, two):
    t = two
    cat_a = _category(db, t['ca'])
    cat_b = _category(db, t['cb'])
    r = client.login(t['ub']).post('/api/finance/expenses', json={
        "branch_id": t['ba'].id, "category_id": cat_b.id, "amount": 300, "wallet_id": t['wb'].id})
    assert r.status_code == 400 and r.json()['detail'] == "Filial topilmadi"
    r = client.login(t['ub']).post('/api/finance/expenses', json={
        "branch_id": t['bb'].id, "category_id": cat_a.id, "amount": 300, "wallet_id": t['wb'].id})
    assert r.status_code == 404
    assert _bal(db, t['wb']) == Decimal(1000)


def test_expense_own_wallet_ok_tx_has_company_and_cash_balance(client, db, two):
    t = two
    cat_a = _category(db, t['ca'])
    r = client.login(t['ua']).post('/api/finance/expenses', json={
        "branch_id": t['ba'].id, "category_id": cat_a.id, "amount": 300, "wallet_id": t['wa'].id})
    assert r.status_code == 201, r.text
    assert _bal(db, t['wa']) == Decimal(700)
    tx = db.query(Transaction).filter(Transaction.reference_type == "expense").one()
    assert tx.company_id == t['ca'].id and tx.wallet_id == t['wa'].id
    # /finance/cash-balance natijasida ko'rinadi
    r = client.login(t['ua']).get('/api/finance/cash-balance')
    assert r.status_code == 200, r.text
    assert float(r.json()['total_expense']) == 300.0
    # B korxona uchun ko'rinmaydi
    r = client.login(t['ub']).get('/api/finance/cash-balance')
    assert float(r.json()['total_expense']) == 0.0


# ─── POST /finance/transactions ──────────────────────────────────────────────

def test_transaction_foreign_wallet_404(client, db, two):
    t = two
    r = client.login(t['ub']).post('/api/finance/transactions', json={
        "branch_id": t['bb'].id, "type": "income", "amount": 500, "wallet_id": t['wa'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    assert _bal(db, t['wa']) == Decimal(1000)
    assert db.query(Transaction).count() == 0


def test_transaction_foreign_branch_400(client, db, two):
    t = two
    r = client.login(t['ub']).post('/api/finance/transactions', json={
        "branch_id": t['ba'].id, "type": "income", "amount": 500, "wallet_id": t['wb'].id})
    assert r.status_code == 400 and r.json()['detail'] == "Filial topilmadi"
    assert _bal(db, t['wb']) == Decimal(1000)


def test_transaction_own_wallet_ok(client, db, two):
    t = two
    r = client.login(t['ub']).post('/api/finance/transactions', json={
        "branch_id": t['bb'].id, "type": "income", "amount": 500, "wallet_id": t['wb'].id})
    assert r.status_code == 201, r.text
    assert _bal(db, t['wb']) == Decimal(1500)
    assert r.json()['company_id'] == t['cb'].id


# ─── PUT /finance/transactions/{id} ──────────────────────────────────────────

def _own_tx(db, t):
    tx = Transaction(branch_id=t['ba'].id, type="income", amount=Decimal(200), wallet_id=t['wa'].id,
                     company_id=t['ca'].id, reference_type="manual")
    db.add(tx)
    db.flush()
    return tx


def test_update_transaction_foreign_wallet_404(client, db, two):
    t = two
    tx = _own_tx(db, t)
    r = client.login(t['ua']).put(f'/api/finance/transactions/{tx.id}', json={
        "amount": 200, "wallet_id": t['wb'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    assert _bal(db, t['wa']) == Decimal(1000)
    assert _bal(db, t['wb']) == Decimal(1000)
    db.refresh(tx)
    assert tx.wallet_id == t['wa'].id


def test_update_transaction_own_wallet_ok(client, db, two):
    t = two
    wa2 = _wallet(db, t['ca'], name="Kassa A2")
    tx = _own_tx(db, t)
    r = client.login(t['ua']).put(f'/api/finance/transactions/{tx.id}', json={
        "amount": 250, "wallet_id": wa2.id})
    assert r.status_code == 200, r.text
    assert _bal(db, t['wa']) == Decimal(800)    # eski kassadan 200 qaytdi
    assert _bal(db, wa2) == Decimal(1250)       # yangi kassaga 250 qo'shildi


# ─── POST /finance/customer-debts/{id}/pay ───────────────────────────────────

def test_finance_debt_pay_foreign_wallet_404(client, db, two):
    t = two
    cust = _customer(db, t['cb'])
    r = client.login(t['ub']).post(f'/api/finance/customer-debts/{cust.id}/pay', json={
        "amount": 100, "wallet_id": t['wa'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    assert _bal(db, t['wa']) == Decimal(1000)


def test_finance_debt_pay_own_wallet_ok(client, db, two):
    t = two
    cust = _customer(db, t['cb'])
    r = client.login(t['ub']).post(f'/api/finance/customer-debts/{cust.id}/pay', json={
        "amount": 100, "wallet_id": t['wb'].id})
    assert r.status_code == 200, r.text
    assert _bal(db, t['wb']) == Decimal(1100)


# ─── POST /customers/{id}/pay-debt ───────────────────────────────────────────

def test_customers_pay_debt_foreign_wallet_404(client, db, two):
    t = two
    cust = _customer(db, t['cb'])
    r = client.login(t['ub']).post(f'/api/customers/{cust.id}/pay-debt', json={
        "amount": 100, "reason": "test", "wallet_id": t['wa'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    assert _bal(db, t['wa']) == Decimal(1000)
    db.refresh(cust)
    assert Decimal(str(cust.debt_balance)) == Decimal(5000)


def test_customers_pay_debt_own_wallet_ok(client, db, two):
    t = two
    cust = _customer(db, t['cb'])
    r = client.login(t['ub']).post(f'/api/customers/{cust.id}/pay-debt', json={
        "amount": 100, "reason": "test", "wallet_id": t['wb'].id})
    assert r.status_code == 200, r.text
    assert _bal(db, t['wb']) == Decimal(1100)


# ─── POST /shifts/close va /shifts/{id}/close ────────────────────────────────

def test_shift_close_foreign_wallet_404_shift_stays_open(client, db, two):
    t = two
    cashier = db.get(type(t['ub']), t['ub'].id)
    shift = _shift(db, cashier, t['cb'], t['bb'])
    _cash_sale(db, cashier, t['cb'], shift, 700)
    r = client.login(cashier).post('/api/shifts/close', json={"wallet_id": t['wa'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    db.refresh(shift)
    assert shift.status == "open" and shift.closed_at is None
    assert _bal(db, t['wa']) == Decimal(1000)
    assert db.query(WalletBalance).count() == 0
    assert db.query(Transaction).count() == 0


def test_shift_close_foreign_card_wallet_404(client, db, two):
    t = two
    shift = _shift(db, t['ub'], t['cb'], t['bb'])
    r = client.login(t['ub']).post(f'/api/shifts/{shift.id}/close',
                                   json={"wallet_id": t['wb'].id, "wallet_card_id": t['wa'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    db.refresh(shift)
    assert shift.status == "open"
    assert _bal(db, t['wa']) == Decimal(1000)


def test_shift_close_inactive_wallet_404(client, db, two):
    t = two
    inactive = _wallet(db, t['cb'], is_active=False, name="Nofaol B")
    shift = _shift(db, t['ub'], t['cb'], t['bb'])
    r = client.login(t['ub']).post('/api/shifts/close', json={"wallet_id": inactive.id})
    assert r.status_code == 404
    db.refresh(shift)
    assert shift.status == "open"


def test_shift_close_own_wallet_ok(client, db, two):
    t = two
    shift = _shift(db, t['ub'], t['cb'], t['bb'])
    _cash_sale(db, t['ub'], t['cb'], shift, 700)
    r = client.login(t['ub']).post('/api/shifts/close', json={"wallet_id": t['wb'].id})
    assert r.status_code == 200, r.text
    assert r.json()['status'] == "closed"
    # T0.28: inkassatsiya daromad emas — kassir kassasi (wb) bilan bir xil kassaga
    # topshirilganda pul harakati ham, `shift` Transaction ham yozilmaydi
    assert _bal(db, t['wb']) == Decimal(1000)
    assert db.query(WalletBalance).filter(WalletBalance.wallet_id == t['wb'].id).count() == 0
    assert db.query(Transaction).filter(Transaction.reference_type == "shift").count() == 0
    db.refresh(shift)
    assert shift.status == "closed" and shift.company_id == t['cb'].id


# ─── POST /inventory/return-from-customer ────────────────────────────────────

def _return_payload(t, wallet_id, product):
    return {"warehouse_id": t['whb'].id, "payment_type": "cash", "paid_cash": 100,
            "wallet_id": wallet_id,
            "items": [{"product_id": product.id, "quantity": 1, "unit_price": 100}]}


def test_return_from_customer_foreign_wallet_404(client, db, two):
    t = two
    p = _product(db, t['cb'])
    r = client.login(t['ub']).post('/api/inventory/return-from-customer', json=_return_payload(t, t['wa'].id, p))
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    assert _bal(db, t['wa']) == Decimal(1000)


def test_return_from_customer_own_wallet_ok(client, db, two):
    t = two
    p = _product(db, t['cb'])
    r = client.login(t['ub']).post('/api/inventory/return-from-customer', json=_return_payload(t, t['wb'].id, p))
    assert r.status_code == 200, r.text
    assert _bal(db, t['wb']) == Decimal(900)


# ─── DELETE /finance/wallets/{id} va POST /finance/wallets ───────────────────

def test_delete_wallet_foreign_404(client, db, two):
    t = two
    r = client.login(t['ub']).delete(f'/api/finance/wallets/{t["wa"].id}')
    assert r.status_code == 404
    db.refresh(t['wa'])
    assert t['wa'].is_active is True


def test_delete_wallet_cashier_403(client, db, mk, two):
    t = two
    cashier = mk.user(t['ca'], role=UserRole.cashier, branch=t['ba'])
    r = client.login(cashier).delete(f'/api/finance/wallets/{t["wa"].id}')
    assert r.status_code == 403
    db.refresh(t['wa'])
    assert t['wa'].is_active is True


def test_delete_wallet_admin_soft_delete_only(client, db, two):
    t = two
    zero = _wallet(db, t['ca'], balance=0, name="Bo'sh kassa")
    r = client.login(t['ua']).delete(f'/api/finance/wallets/{zero.id}')
    assert r.status_code == 204, r.text
    row = db.get(Wallet, zero.id)
    assert row is not None and row.is_active is False   # qator o'chirilmaydi
    # Nofaol kassani qayta chaqirish ham 204 (require_active=False)
    r = client.login(t['ua']).delete(f'/api/finance/wallets/{zero.id}')
    assert r.status_code == 204


def test_create_wallet_foreign_branch_400(client, db, two):
    t = two
    r = client.login(t['ub']).post('/api/finance/wallets', json={"name": "X", "branch_id": t['ba'].id})
    assert r.status_code == 400 and r.json()['detail'] == "Filial topilmadi"
    r = client.login(t['ub']).post('/api/finance/wallets', json={"name": "X", "branch_id": t['bb'].id})
    assert r.status_code == 201, r.text


# ─── Migratsiya: transactions.company_id backfill ───────────────────────────

def test_migration_backfill_sql(db, two):
    t = two
    spec = importlib.util.spec_from_file_location(
        "s0_03_tx_company_backfill", os.path.join(ROOT, 'alembic', 'versions', 's0_03_tx_company_backfill.py'))
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.revision == 't0_3' and mig.down_revision == 't0_1'

    tx_w = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(10), wallet_id=t['wa'].id, company_id=None)
    tx_b = Transaction(branch_id=t['bb'].id, type="expense", amount=Decimal(10), wallet_id=None, company_id=None)
    tx_none = Transaction(branch_id=None, type="expense", amount=Decimal(10), wallet_id=None, company_id=None)
    db.add_all([tx_w, tx_b, tx_none])
    db.flush()

    db.execute(text(mig.SQL_BACKFILL_BY_WALLET))
    db.execute(text(mig.SQL_BACKFILL_BY_BRANCH))
    db.expire_all()
    assert tx_w.company_id == t['ca'].id
    assert tx_b.company_id == t['cb'].id
    assert tx_none.company_id is None
    assert db.execute(text("SELECT count(*) FROM transactions WHERE company_id IS NULL AND wallet_id IS NOT NULL")).scalar() == 0
    # idempotent
    db.execute(text(mig.SQL_BACKFILL_BY_WALLET))
    db.execute(text(mig.SQL_BACKFILL_BY_BRANCH))
    assert db.execute(text(mig.SQL_COUNT_REMAINING)).scalar() == 1


# ─── Qabul mezoni 6: routerlarda db.get(Wallet qolmagan ──────────────────────

def test_no_db_get_wallet_in_routers():
    for name in ("finance.py", "shifts.py", "inventory.py", "customers.py"):
        src = open(os.path.join(ROOT, 'app', 'routers', name), encoding='utf-8').read()
        assert "db.get(Wallet" not in src, name
