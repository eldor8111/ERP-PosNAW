"""T0.7 — branch_id 0/1 fallbacklar va filialsiz korxona.

find_tx_branch/resolve_tx_branch tartibi, sotuv/smena/xarajat/qarz to'lovi/AI to'lovi
filialsiz foydalanuvchi va filialsiz korxonada, POST /companies asosiy filiali,
marketplace/order_to_sale filialsiz korxonada, migratsiya (idempotent) va 0/1 fallback yo'qligi.
"""
import importlib.util
import os
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.models.branch import Branch
from app.models.customer import Customer
from app.models.moliya import Expense, ExpenseCategory, Transaction, Wallet
from app.models.product import Product
from app.models.shift import Shift
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
NO_BRANCH = "Korxonada filial yo'q"


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, balance=0, name=None):
    w = Wallet(name=name or f"Kassa {company.id}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=True, is_open=True)
    db.add(w)
    db.flush()
    return w


def _customer(db, company, debt=5000, name=None):
    c = Customer(name=name or f"Mijoz {company.id}", company_id=company.id,
                 debt_balance=Decimal(debt), debt_balances={"UZS": float(debt)})
    db.add(c)
    db.flush()
    return c


def _product(db, company, n=1):
    p = Product(name=f"Tovar {n}", sku=f"T07-{n}-{company.id}", barcode=f"B07-{n}-{company.id}",
                company_id=company.id, sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _category(db, company):
    cat = ExpenseCategory(name="Ijara", company_id=company.id)
    db.add(cat)
    db.flush()
    return cat


@pytest.fixture
def world(db, mk):
    """A korxona: 2 filial, filialsiz admin, ombor (2-filialda); B korxona alohida."""
    ca = mk.company()
    ba1 = mk.branch(ca, name="A-1")
    ba2 = mk.branch(ca, name="A-2")
    wha = mk.warehouse(ca, ba2)
    admin_nb = mk.user(ca, role=UserRole.admin)            # filialsiz admin
    cb = mk.company()
    bb = mk.branch(cb, name="B-1")
    whb = mk.warehouse(cb, bb)
    ub = mk.user(cb, role=UserRole.admin, branch=bb)
    return dict(ca=ca, ba1=ba1, ba2=ba2, wha=wha, admin_nb=admin_nb, cb=cb, bb=bb, whb=whb, ub=ub)


# ─── 1. find_tx_branch / resolve_tx_branch tartibi ──────────────────────────

def test_find_tx_branch_order(db, mk, world):
    from app.services.tenant_guards import find_tx_branch
    w = world
    u = w['admin_nb']
    wallet = _wallet(db, w['ca'], w['ba2'])
    # 5. hech narsa yo'q: eng kichik id li faol filial
    assert find_tx_branch(db, u) == w['ba1'].id
    # 4. ombor filiali
    assert find_tx_branch(db, u, warehouse_id=w['wha'].id) == w['ba2'].id
    # 3. kassa filiali ombordan ustun
    wallet.branch_id = w['ba1'].id
    assert find_tx_branch(db, u, wallet=wallet, warehouse_id=w['wha'].id) == w['ba1'].id
    # 2. user filiali kassa/ombordan ustun
    u.branch_id = w['ba2'].id
    wallet.branch_id = w['ba1'].id
    assert find_tx_branch(db, u, wallet=wallet) == w['ba2'].id
    # 1. aniq berilgan filial hammadan ustun
    assert find_tx_branch(db, u, explicit_branch_id=w['ba1'].id, wallet=wallet) == w['ba1'].id


def test_find_tx_branch_ignores_foreign_company_resources(db, mk, world):
    from app.services.tenant_guards import find_tx_branch
    w = world
    u = w['admin_nb']
    # begona korxona ombori va filiali (user.branch_id begona) e'tiborsiz
    assert find_tx_branch(db, u, warehouse_id=w['whb'].id) == w['ba1'].id
    u.branch_id = w['bb'].id
    assert find_tx_branch(db, u) == w['ba1'].id
    foreign_wallet = _wallet(db, w['cb'], w['bb'])
    assert find_tx_branch(db, u, wallet=foreign_wallet) == w['ba1'].id
    # aniq berilgan begona filial — 400
    with pytest.raises(HTTPException) as ei:
        find_tx_branch(db, u, explicit_branch_id=w['bb'].id)
    assert ei.value.status_code == 400


def test_find_tx_branch_prefers_active_then_any_then_none(db, mk):
    from app.services.tenant_guards import find_tx_branch, resolve_tx_branch
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    assert find_tx_branch(db, u) is None
    with pytest.raises(HTTPException) as ei:
        resolve_tx_branch(db, u)
    assert ei.value.status_code == 400 and ei.value.detail.startswith(NO_BRANCH)
    b_off = mk.branch(c, is_active=False)
    assert find_tx_branch(db, u) == b_off.id                 # faol yo'q: har qanday birinchi
    b_on = mk.branch(c, is_active=True)
    assert find_tx_branch(db, u) == b_on.id                  # faol ustuvor (id kattaroq bo'lsa ham)
    assert resolve_tx_branch(db, u) == b_on.id


def test_resolve_branch_id_ignores_foreign_warehouse(db, world):
    """Mezon 6: begona korxona ombori id si berilsa uning filiali qaytmaydi."""
    from app.services.sale_helpers import resolve_branch_id
    w = world
    assert resolve_branch_id(db, w['admin_nb'], w['whb'].id) == w['ba1'].id
    assert resolve_branch_id(db, w['admin_nb'], w['wha'].id) == w['ba2'].id
    assert resolve_branch_id(db, w['admin_nb'], w['whb'].id, prefer_warehouse=True) == w['ba1'].id


# ─── 2. Sotuv: filialsiz korxonada 400 ──────────────────────────────────────

def _sale_data(product, warehouse):
    from app.schemas.sale import SaleCreate
    return SaleCreate(items=[{"product_id": product.id, "quantity": 1, "unit_price": 1000}],
                      payment_type="cash", paid_amount=Decimal("1000"), paid_cash=Decimal("1000"),
                      warehouse_id=warehouse.id)


def test_sale_writes_income_transaction_with_branch(db, mk):
    from app.services.sale_create import create_sale
    c, b, wh, u = mk.tenant()
    _wallet(db, c, b)
    p = _product(db, c)
    sale = create_sale(db, _sale_data(p, wh), u)
    txs = db.query(Transaction).filter(Transaction.reference_type == "sale", Transaction.reference_id == sale.id).all()
    assert len(txs) == 1 and txs[0].branch_id == b.id and txs[0].company_id == c.id


def test_sale_branchless_company_returns_400_and_no_silent_loss(db, mk):
    from app.services.sale_create import create_sale
    c = mk.company()
    wh = mk.warehouse(c)                      # filialsiz ombor
    u = mk.user(c, role=UserRole.admin)
    _wallet(db, c)
    p = _product(db, c)
    with pytest.raises(HTTPException) as ei:
        create_sale(db, _sale_data(p, wh), u)
    assert ei.value.status_code == 400 and ei.value.detail.startswith(NO_BRANCH)
    # Eski xatti-harakat (jim o'tkazib yuborish) yo'q: sale_create da `if tx_branch_id:` qolmagan
    src = open(os.path.join(ROOT, 'app', 'services', 'sale_create.py'), encoding='utf-8').read()
    assert 'if tx_branch_id:' not in src


# ─── 3. Smena: filialsiz xodim ──────────────────────────────────────────────

def test_shift_api_open_and_close_branchless_user(client, db, world):
    """Mezon 3: smena filiali NULL emas, yopish 500 bermaydi."""
    w = world
    u = w['admin_nb']
    wallet = _wallet(db, w['ca'], w['ba1'], name="Asosiy")
    # T1.11: 2+ faol filialli korxonada filialsiz admin filialni aniq ko'rsatishi shart (jim birinchisiga tushmaydi)
    r = client.login(u).post('/api/shifts/open', json={"opening_cash": 100})
    assert r.status_code == 400 and r.json()["detail"] == "Filial tanlang", r.text
    r = client.login(u).post('/api/shifts/open', json={"opening_cash": 100, "branch_id": w['ba1'].id})
    assert r.status_code == 201, r.text
    assert r.json()["branch_id"] == w['ba1'].id
    sid = r.json()["id"]
    r = client.login(u).post(f'/api/shifts/{sid}/close', json={"closing_cash": 100, "wallet_id": wallet.id})
    assert r.status_code == 200, r.text
    db.expire_all()
    s = db.get(Shift, sid)
    assert s.status == "closed" and s.branch_id == w['ba1'].id


def test_shift_open_explicit_foreign_branch_400_and_no_branch_company_400(client, db, mk, world):
    w = world
    r = client.login(w['admin_nb']).post('/api/shifts/open', json={"branch_id": w['bb'].id})
    assert r.status_code == 400
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    r = client.login(u).post('/api/shifts/open', json={})
    assert r.status_code == 400 and NO_BRANCH in r.json()["detail"]
    assert db.query(Shift).filter(Shift.cashier_id == u.id).count() == 0


# ─── 4. Kassa xarajati ──────────────────────────────────────────────────────

def test_kassa_do_expense_branchless_user_uses_company_branch(client, db, world):
    w = world
    wallet = _wallet(db, w['ca'], None, balance=1000)
    cat = _category(db, w['ca'])
    r = client.login(w['admin_nb']).post('/api/kassa/do-expense', json={
        "wallet_id": wallet.id, "category_id": cat.id, "amount": 100})
    assert r.status_code == 200, r.text
    exp = db.get(Expense, r.json()["expense_id"])
    tx = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == exp.id).one()
    assert exp.branch_id == w['ba1'].id and tx.branch_id == w['ba1'].id   # >= 1, o'z korxonasi filiali
    assert db.get(Branch, tx.branch_id).company_id == w['ca'].id


def test_kassa_do_expense_wallet_branch_used_and_foreign_wallet_404(client, db, world):
    w = world
    wallet = _wallet(db, w['ca'], w['ba2'], balance=1000)
    cat = _category(db, w['ca'])
    r = client.login(w['admin_nb']).post('/api/kassa/do-expense', json={
        "wallet_id": wallet.id, "category_id": cat.id, "amount": 50})
    assert r.status_code == 200, r.text
    assert db.get(Expense, r.json()["expense_id"]).branch_id == w['ba2'].id   # kassa filiali
    # begona korxona kassasi — 404 (izolyatsiya)
    fw = _wallet(db, w['cb'], w['bb'], balance=1000)
    r = client.login(w['admin_nb']).post('/api/kassa/do-expense', json={
        "wallet_id": fw.id, "category_id": cat.id, "amount": 50})
    assert r.status_code == 404


def test_kassa_do_expense_branchless_company_400(client, db, mk):
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    wallet = _wallet(db, c, None, balance=1000)
    cat = _category(db, c)
    r = client.login(u).post('/api/kassa/do-expense', json={"wallet_id": wallet.id, "category_id": cat.id, "amount": 10})
    assert r.status_code == 400 and NO_BRANCH in r.json()["detail"]
    assert db.query(Expense).filter(Expense.company_id == c.id).count() == 0


# ─── 5. Mijoz qarzi to'lovi ─────────────────────────────────────────────────

def test_finance_debt_payment_branchless_user(client, db, world):
    w = world
    wallet = _wallet(db, w['ca'], w['ba2'], balance=0)
    cust = _customer(db, w['ca'], debt=5000)
    r = client.login(w['admin_nb']).post(f'/api/finance/customer-debts/{cust.id}/pay', json={
        "amount": 1000, "wallet_id": wallet.id})
    assert r.status_code == 200, r.text
    tx = db.query(Transaction).filter(Transaction.reference_type == "customer_payment",
                                      Transaction.reference_id == cust.id).one()
    assert tx.branch_id == w['ba2'].id and tx.branch_id >= 1


def test_finance_debt_payment_foreign_customer_404_and_branchless_company_400(client, db, mk, world):
    w = world
    foreign = _customer(db, w['cb'])
    r = client.login(w['admin_nb']).post(f'/api/finance/customer-debts/{foreign.id}/pay', json={"amount": 10})
    assert r.status_code == 404
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    wallet = _wallet(db, c)
    cust = _customer(db, c)
    r = client.login(u).post(f'/api/finance/customer-debts/{cust.id}/pay', json={"amount": 10, "wallet_id": wallet.id})
    assert r.status_code == 400 and NO_BRANCH in r.json()["detail"]
    assert db.query(Transaction).filter(Transaction.company_id == c.id).count() == 0


# ─── 6. AI qarz to'lovi ─────────────────────────────────────────────────────

def test_ai_record_debt_payment_branchless_admin(db, world):
    """Mezon 2: users.branch_id NULL admin — to'lov yoziladi, Transaction.branch_id o'z korxonasiniki."""
    from app.services.ai_tools_registry import AIToolRegistry
    w = world
    wallet = _wallet(db, w['ca'], w['ba2'], balance=0)
    cust = _customer(db, w['ca'], debt=5000, name="Aliyev Ali")
    tool = AIToolRegistry.get_tool("record_debt_payment")()
    res = tool.execute(db, w['ca'].id, w['admin_nb'], customer_name="Aliyev Ali", amount=500)
    db.flush()
    assert "Muvaffaqiyatli" in res["reply"]
    tx = db.query(Transaction).filter(Transaction.reference_type == "customer_payment",
                                      Transaction.reference_id == cust.id).one()
    assert tx.branch_id >= 1 and db.get(Branch, tx.branch_id).company_id == w['ca'].id
    assert tx.branch_id == w['ba2'].id and tx.wallet_id == wallet.id


def test_ai_confirm_branchless_company_returns_error_reply_not_500(client, db, mk):
    from app.models.ai_audit import AIAuditLog
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    cust = _customer(db, c, debt=5000, name="Valiyev Vali")
    log = AIAuditLog(company_id=c.id, user_id=u.id, tool_name="record_debt_payment",
                     tool_arguments={"customer_name": "Valiyev Vali", "amount": 500},
                     status="PENDING_CONFIRMATION", confirmation_required=True, confirmation_id="conf-t07")
    db.add(log)
    db.commit()          # /ai/confirm rollback qiladi: PENDING log avval saqlangan bo'lishi kerak (haqiqiy oqimdagidek)
    r = client.login(u).post('/api/ai/confirm', json={"confirmation_id": "conf-t07"})
    assert r.status_code == 200, r.text
    # T2.6: kassasi/filiali yo'q korxonada qarz to'lovi "Ochiq kassa topilmadi" bilan rad etiladi (qarz o'zgarmaydi)
    assert NO_BRANCH in r.json()["reply"] or "Ochiq kassa topilmadi" in r.json()["reply"]
    db.expire_all()
    # T2.6: AI vositasi rad etishni "❌ ..." javobi sifatida qaytaradi (istisno emas) — log SUCCESS bo'lishi mumkin
    assert db.get(AIAuditLog, log.id).status in ("ERROR", "SUCCESS")
    assert Decimal(str(db.get(Customer, cust.id).debt_balance)) == Decimal(5000)   # qarz o'zgarmadi
    assert db.query(Transaction).filter(Transaction.company_id == c.id).count() == 0


def test_ai_confirm_commit_failure_is_caught(client, db, world, monkeypatch):
    """Commit (IntegrityError) try ichida: 500 emas, log ERROR bo'ladi."""
    from app.models.ai_audit import AIAuditLog
    w = world
    _wallet(db, w['ca'], w['ba1'])
    _customer(db, w['ca'], debt=5000, name="Karimov Karim")
    log = AIAuditLog(company_id=w['ca'].id, user_id=w['admin_nb'].id, tool_name="record_debt_payment",
                     tool_arguments={"customer_name": "Karimov Karim", "amount": 100},
                     status="PENDING_CONFIRMATION", confirmation_required=True, confirmation_id="conf-t07b")
    db.add(log)
    db.commit()
    real_commit = db.commit
    calls = {"n": 0}

    def flaky_commit():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("FK violation")
        return real_commit()

    monkeypatch.setattr(db, "commit", flaky_commit)
    r = client.login(w['admin_nb']).post('/api/ai/confirm', json={"confirmation_id": "conf-t07b"})
    assert r.status_code == 200, r.text
    assert "FK violation" in r.json()["reply"]
    assert calls["n"] == 2          # log alohida commit qilindi
    assert db.get(AIAuditLog, log.id).status == "ERROR"


# ─── 7. POST /companies — asosiy filial ─────────────────────────────────────

def test_create_company_creates_default_branch(client, db, mk):
    su = mk.user(None, role=UserRole.super_admin)
    r = client.login(su).post('/api/companies', json={"name": "Yangi Do'kon"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["branches_count"] == 1
    branches = db.query(Branch).filter(Branch.company_id == body["id"]).all()
    assert len(branches) == 1 and branches[0].is_active is True
    assert branches[0].name == "Yangi Do'kon (Asosiy)"


# ─── 8. Marketplace va order_to_sale filialsiz korxonada ────────────────────

def test_marketplace_import_branchless_company_skips_without_exception(db, mk):
    from app.models.order import Order
    from app.services.marketplace_service import _import_mirmaza_group
    c = mk.company()
    mo = {"marketOrderId": "MO-1", "customer": {"name": "X", "phone": "998901112233"}}
    ok = _import_mirmaza_group(db, mo, c.id, [{"externalId": "PROD-1", "quantity": 1, "total": 10}], "grp-t07")
    assert ok is False
    assert db.query(Order).filter(Order.company_id == c.id).count() == 0


def test_order_to_sale_branchless_company_skipped_with_log(db, mk, caplog, monkeypatch):
    import logging
    import app.services.sale_create as sc
    from app.services.order_to_sale import maybe_create_sale_for_delivered_group
    c = mk.company(orders_auto_create_sale=True)
    mk.user(c, role=UserRole.admin)

    def _boom(*a, **k):
        raise AssertionError("chaqirilmasligi kerak")

    monkeypatch.setattr(sc, "create_sale", _boom)
    order = SimpleNamespace(sale_id=None, company_id=c.id, id=77, order_group_id="g77")
    with caplog.at_level(logging.WARNING):
        maybe_create_sale_for_delivered_group(db, [order])      # exception ko'tarmaydi
    assert order.sale_id is None
    assert any("filial yo'q" in rec.getMessage() for rec in caplog.records)


# ─── 9. supplier_ledger ─────────────────────────────────────────────────────

def test_supplier_ledger_branch_resolution(db, world, mk):
    from app.services.supplier_ledger import resolve_branch, record_cash
    w = world
    assert resolve_branch(db, w['admin_nb'], w['wha'].id) == w['ba2'].id
    assert resolve_branch(db, w['admin_nb'], w['whb'].id) == w['ba1'].id      # begona ombor e'tiborsiz
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    with pytest.raises(HTTPException) as ei:
        record_cash(db, user=u, direction="out", amount=10, currency="UZS", payment_type="cash",
                    wallet_id=None, reference_type="supplier_payment", reference_id=1, description="t")
    assert ei.value.status_code == 400


# ─── 10. Migratsiya ─────────────────────────────────────────────────────────

def _load_migration():
    path = os.path.join(ROOT, 'alembic', 'versions', 't0_7_branchless_companies_and_tx_branch_nullable.py')
    spec = importlib.util.spec_from_file_location('mig_t0_7', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_backfill_idempotent(db, mk):
    """Mezon 8: filialsiz korxonaga filial, NULL tranzaksiya/ochiq smena to'ldiriladi, yopiq smena tegilmaydi; ikki marta bir xil."""
    mod = _load_migration()
    assert mod.revision == 't0_7' and mod.down_revision == 't0_6'
    c_none = mk.company(name="Bo'sh")
    c_two = mk.company()
    mk.branch(c_two, is_active=False)
    b_on1 = mk.branch(c_two, is_active=True)
    b_on2 = mk.branch(c_two, is_active=True)
    u = mk.user(c_two, role=UserRole.admin)
    tx = Transaction(branch_id=None, company_id=c_two.id, type="income", amount=Decimal(5))
    tx_other = Transaction(branch_id=b_on2.id, company_id=c_two.id, type="income", amount=Decimal(6))
    s_open = Shift(cashier_id=u.id, branch_id=None, company_id=c_two.id, status="open")
    s_closed = Shift(cashier_id=u.id, branch_id=None, company_id=c_two.id, status="closed")
    db.add_all([tx, tx_other, s_open, s_closed])
    db.flush()

    conn = db.connection()
    executed = []

    class FakeOp:
        @staticmethod
        def get_bind():
            return conn

        @staticmethod
        def execute(stmt):
            executed.append(stmt)
            conn.execute(text(stmt))

    mod.op = FakeOp
    mod.upgrade()
    db.expire_all()
    new_b = db.query(Branch).filter(Branch.company_id == c_none.id).all()
    assert len(new_b) == 1 and new_b[0].is_active and new_b[0].name == "Bo'sh (Asosiy)"
    assert db.query(Branch).filter(Branch.company_id == c_two.id).count() == 3        # o'zgarmadi
    assert tx.branch_id == b_on1.id and tx_other.branch_id == b_on2.id
    assert s_open.branch_id == b_on1.id and s_closed.branch_id is None

    mod.upgrade()          # ikkinchi marta
    db.expire_all()
    assert db.query(Branch).filter(Branch.company_id == c_none.id).count() == 1
    assert tx.branch_id == b_on1.id and s_open.branch_id == b_on1.id and s_closed.branch_id is None
    assert mod.downgrade() is None
    assert not any("DROP NOT NULL" in s for s in executed)      # SQLite: ALTER faqat PostgreSQLda


def test_migration_drops_not_null_on_postgresql():
    mod = _load_migration()
    executed = []

    class FakeOp:
        @staticmethod
        def get_bind():
            return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        @staticmethod
        def execute(stmt):
            executed.append(stmt)

    mod.op = FakeOp
    mod.upgrade()
    assert executed[-1] == "ALTER TABLE transactions ALTER COLUMN branch_id DROP NOT NULL"
    assert len(executed) == 4


def test_main_auto_migration_drops_not_null():
    src = open(os.path.join(ROOT, 'app', 'main.py'), encoding='utf-8').read()
    assert "ALTER TABLE transactions ALTER COLUMN branch_id DROP NOT NULL;" in src


# ─── 11. 0/1 fallback qolmagan ──────────────────────────────────────────────

def test_no_zero_one_branch_fallbacks_left():
    pat = re.compile(r"branch_id\s*=.*(or 0|else 0|else 1)\b")
    bad = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, 'app')):
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(base, f)
                for i, line in enumerate(open(p, encoding='utf-8', errors='ignore'), 1):
                    if pat.search(line):
                        bad.append(f"{p}:{i}: {line.strip()}")
    assert not bad, bad
