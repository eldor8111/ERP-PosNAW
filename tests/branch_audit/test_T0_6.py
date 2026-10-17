"""T0.6 — Xarajat va tranzaksiya yozuvlarini to'g'rilash.

POST /finance/expenses va /finance/transactions: company_id, reference_id, user_id,
filial tekshiruvi, summa > 0; xarajat o'chirilganda hamyon/kassa harakati/tranzaksiya
qaytadi; tizim yozuvlari (sale, sale_refund, shift) PUT/DELETE qilinmaydi; qarz
to'lovlarida manfiy summa yopiladi; migratsiya idempotent.
"""
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.customer import Customer
from app.models.moliya import Expense, ExpenseCategory, KassaMovement, KassaSession, Transaction, Wallet
from app.models.supplier import Supplier
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
WALLET_404 = "Kassa (hamyon) topilmadi"
BRANCH_400 = "Filial topilmadi"
NO_BRANCH_400 = "Korxonada filial yo'q"
LOCKED_400 = "Tizim yaratgan yozuvni o'zgartirib bo'lmaydi: tegishli bo'limdan bekor qiling"


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, balance=1000, name=None, is_active=True):
    w = Wallet(name=name or f"Kassa {company.id}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=is_active, is_open=True)
    db.add(w)
    db.flush()
    return w


def _category(db, company, name="Ijara"):
    c = ExpenseCategory(name=name, company_id=company.id if company else None)
    db.add(c)
    db.flush()
    return c


def _customer(db, company, debt=5000):
    c = Customer(name=f"Mijoz {company.id}", company_id=company.id,
                 debt_balance=Decimal(debt), debt_balances={"UZS": float(debt)})
    db.add(c)
    db.flush()
    return c


def _supplier(db, company, debt=5000):
    s = Supplier(name=f"Taminotchi {company.id}", company_id=company.id, is_active=True,
                 debt_balance=Decimal(debt), debt_balances={"UZS": float(debt)})
    db.add(s)
    db.flush()
    return s


def _bal(db, wallet):
    db.refresh(wallet)
    return Decimal(str(wallet.balance))


def _count(db, model, **flt):
    q = db.query(model)
    for k, v in flt.items():
        q = q.filter(getattr(model, k) == v)
    return q.count()


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch):
    """Telegram bildirishnomasi o'z SessionLocal() bilan jonli bazaga ulanmoqchi bo'ladi — o'chiramiz."""
    import app.routers.finance as fin
    monkeypatch.setattr(fin, "trigger_instant_notification", lambda *a, **k: None)


@pytest.fixture
def two(db, mk):
    """A va B korxonalar: har birida filial, admin, kassa (filialli) va kategoriya."""
    ca, ba, wha, ua = mk.tenant()
    cb, bb, whb, ub = mk.tenant()
    ba2 = mk.branch(ca, name="A ikkinchi filial")
    wa = _wallet(db, ca, ba)
    wb = _wallet(db, cb, bb)
    cat_a = _category(db, ca)
    cat_b = _category(db, cb)
    return dict(ca=ca, ba=ba, ba2=ba2, ua=ua, wa=wa, cat_a=cat_a,
                cb=cb, bb=bb, ub=ub, wb=wb, cat_b=cat_b)


# ─── POST /finance/expenses ──────────────────────────────────────────────────

def test_create_expense_links_company_reference_user(client, db, two):
    """Mezon 1, 4: filial o'z korxonasiniki, tranzaksiyada company_id/reference_id/user_id,
    hamyon kamayadi, kassa harakati yoziladi, cash-balance va payments/expense da ko'rinadi."""
    t = two
    before = _bal(db, t['wa'])
    r = client.login(t['ua']).post('/api/finance/expenses', json={
        "category_id": t['cat_a'].id, "amount": 300, "wallet_id": t['wa'].id, "description": "Ijara"})
    assert r.status_code == 201, r.text
    exp = db.get(Expense, r.json()['id'])
    assert exp.branch_id in (t['ba'].id, t['ba2'].id) and exp.company_id == t['ca'].id
    assert exp.wallet_id == t['wa'].id

    tx = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == exp.id).one()
    assert tx.company_id == t['ca'].id and tx.user_id == t['ua'].id and tx.branch_id == exp.branch_id
    assert tx.type == "expense" and tx.wallet_id == t['wa'].id and tx.payment_type == "cash"
    assert tx.currency_code == "UZS" and Decimal(str(tx.amount)) == Decimal(300)

    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense", KassaMovement.reference_id == exp.id).one()
    assert mv.direction == "out" and mv.company_id == t['ca'].id and mv.created_by == t['ua'].id
    assert mv.wallet_id == t['wa'].id and mv.session_id is None
    assert _bal(db, t['wa']) == before - Decimal(300)

    cb = client.login(t['ua']).get('/api/finance/cash-balance').json()
    assert cb['total_expense'] == 300.0 and cb['expense_by_currency'].get('UZS') == 300.0
    lst = client.login(t['ua']).get('/api/finance/payments/expense').json()
    assert any(i.get('id') == tx.id for i in lst['items'])
    # B korxona o'z balansida bu chiqimni ko'rmaydi
    assert client.login(t['ub']).get('/api/finance/cash-balance').json()['total_expense'] == 0.0


def test_create_expense_branch_resolution_order(client, db, two, mk):
    """Body dagi filial → kassa filiali → foydalanuvchi filiali → korxonaning birinchi filiali."""
    t = two
    c = client.login(t['ua'])
    # 1) aniq filial (ba2)
    r = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 10, "branch_id": t['ba2'].id})
    assert r.status_code == 201 and db.get(Expense, r.json()['id']).branch_id == t['ba2'].id
    # 2) kassa filiali (ua filiali ba, kassa ba2 da)
    w2 = _wallet(db, t['ca'], t['ba2'], name="Ikkinchi kassa")
    r = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 10, "wallet_id": w2.id})
    assert r.status_code == 201 and db.get(Expense, r.json()['id']).branch_id == t['ba2'].id
    # 3) foydalanuvchi filiali (kassa filialsiz)
    w3 = _wallet(db, t['ca'], None, name="Filialsiz kassa")
    r = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 10, "wallet_id": w3.id})
    assert r.status_code == 201 and db.get(Expense, r.json()['id']).branch_id == t['ba'].id
    # 4) filialsiz foydalanuvchi → korxonaning eng kichik id li faol filiali
    u2 = mk.user(t['ca'], role=UserRole.admin, branch=None)
    r = client.login(u2).post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 10})
    assert r.status_code == 201 and db.get(Expense, r.json()['id']).branch_id == t['ba'].id
    # 5) kassa Expense yoki tranzaksiya yozilmaydi (wallet_id siz) — faqat Expense + Transaction
    e = db.get(Expense, r.json()['id'])
    assert e.wallet_id is None
    assert _count(db, KassaMovement, reference_type="expense", reference_id=e.id) == 0


def test_create_expense_foreign_branch_or_wallet_nothing_written(client, db, two):
    """Mezon 2: begona filial → 400, begona kassa → 404; DB ga hech narsa yozilmaydi, balans o'zgarmaydi."""
    t = two
    before_a, before_b = _bal(db, t['wa']), _bal(db, t['wb'])
    n_exp, n_tx, n_mv = db.query(Expense).count(), db.query(Transaction).count(), db.query(KassaMovement).count()
    c = client.login(t['ua'])

    r = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 100, "branch_id": t['bb'].id, "wallet_id": t['wa'].id})
    assert r.status_code == 400 and r.json()['detail'] == BRANCH_400
    r = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 100, "wallet_id": t['wb'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    # begona kategoriya → 404 (T0.3 testi bilan bir xil: begona resurs ko'rinmaydi)
    r = c.post('/api/finance/expenses', json={"category_id": t['cat_b'].id, "amount": 100})
    assert r.status_code == 404 and r.json()['detail'] == "Kategoriya topilmadi"
    # nofaol kassa → 404
    inactive = _wallet(db, t['ca'], t['ba'], name="Nofaol", is_active=False)
    r = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 100, "wallet_id": inactive.id})
    assert r.status_code == 404

    assert (db.query(Expense).count(), db.query(Transaction).count(), db.query(KassaMovement).count()) == (n_exp, n_tx, n_mv)
    assert _bal(db, t['wa']) == before_a and _bal(db, t['wb']) == before_b

    # umumiy (company_id NULL) kategoriya ishlaydi
    shared = _category(db, None, name="Umumiy")
    r = c.post('/api/finance/expenses', json={"category_id": shared.id, "amount": 5})
    assert r.status_code == 201, r.text


def test_create_expense_company_without_branch_400(client, db, mk):
    """Mezon 3: filialsiz korxonada aniq 400, 500 emas."""
    c0 = mk.company()
    u0 = mk.user(c0, role=UserRole.admin, branch=None)
    cat = _category(db, c0)
    w = _wallet(db, c0, None)
    r = client.login(u0).post('/api/finance/expenses', json={"category_id": cat.id, "amount": 50, "wallet_id": w.id})
    assert r.status_code == 400 and r.json()['detail'] == NO_BRANCH_400
    assert _bal(db, w) == Decimal(1000) and _count(db, Expense, company_id=c0.id) == 0


def test_create_expense_amount_nonpositive_422(client, db, two):
    """Mezon 7: amount <= 0 → 422, hech narsa yozilmaydi."""
    t = two
    before = _bal(db, t['wa'])
    n = db.query(Expense).count()
    for amt in (0, -100):
        r = client.login(t['ua']).post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": amt, "wallet_id": t['wa'].id})
        assert r.status_code == 422, r.text
    assert _bal(db, t['wa']) == before and db.query(Expense).count() == n


# ─── DELETE /finance/expenses/{id} ───────────────────────────────────────────

def test_delete_expense_restores_wallet_removes_tx_and_movement(client, db, two):
    """Mezon 5: o'chirishdan keyin balans qaytadi, xarajat/tranzaksiya/kassa harakati qolmaydi.
    Begona korxona foydalanuvchisi uchun 404 va hech narsa o'zgarmaydi."""
    t = two
    before = _bal(db, t['wa'])
    r = client.login(t['ua']).post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 250, "wallet_id": t['wa'].id})
    exp_id = r.json()['id']
    assert _bal(db, t['wa']) == before - Decimal(250)

    # B korxona → 404, hech narsa o'chmaydi
    r = client.login(t['ub']).delete(f'/api/finance/expenses/{exp_id}')
    assert r.status_code == 404
    assert db.get(Expense, exp_id) is not None and _bal(db, t['wa']) == before - Decimal(250)

    r = client.login(t['ua']).delete(f'/api/finance/expenses/{exp_id}')
    assert r.status_code == 204, r.text
    db.expire_all()
    # T1.19: o'chirish o'rniga bekor qilish (void) — yozuvlar qoladi, teskari harakat yoziladi
    assert db.get(Expense, exp_id).voided_at is not None
    assert db.query(Transaction).filter(
        Transaction.reference_type == "expense", Transaction.reference_id == exp_id,
        Transaction.voided_at.is_(None)).count() == 0
    assert _count(db, KassaMovement, reference_type="expense_void", reference_id=exp_id) == 1
    assert _bal(db, t['wa']) == before


def test_delete_expense_legacy_tx_without_reference(client, db, two):
    """Eski yozuv: tranzaksiya reference_id siz — summa, kassa, filial va 10 s ichida bitta nomzod bo'lsa o'chadi;
    ikki nomzod bo'lsa (ikki ma'noli) tegilmaydi. Hamyon baribir qaytadi."""
    t = two
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 1:1 holat
    e1 = Expense(branch_id=t['ba'].id, category_id=t['cat_a'].id, amount=Decimal(70), company_id=t['ca'].id,
                 wallet_id=t['wa'].id, created_at=now)
    db.add(e1); db.flush()
    tx1 = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(70), wallet_id=t['wa'].id,
                      company_id=t['ca'].id, reference_type="expense", reference_id=None, created_at=now + timedelta(seconds=3))
    tx_far = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(70), wallet_id=t['wa'].id,
                         company_id=t['ca'].id, reference_type="expense", reference_id=None, created_at=now + timedelta(seconds=60))
    db.add_all([tx1, tx_far]); db.flush()
    before = _bal(db, t['wa'])
    r = client.login(t['ua']).delete(f'/api/finance/expenses/{e1.id}')
    assert r.status_code == 204
    db.expire_all()
    assert db.get(Transaction, tx1.id).voided_at is not None and db.get(Transaction, tx_far.id).voided_at is None
    assert _bal(db, t['wa']) == before + Decimal(70)

    # ikki ma'noli holat: ikkala nomzod ham qoladi
    e2 = Expense(branch_id=t['ba'].id, category_id=t['cat_a'].id, amount=Decimal(80), company_id=t['ca'].id,
                 wallet_id=t['wa'].id, created_at=now)
    db.add(e2); db.flush()
    txa = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(80), wallet_id=t['wa'].id,
                      company_id=t['ca'].id, reference_type="expense", reference_id=None, created_at=now + timedelta(seconds=1))
    txb = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(80), wallet_id=t['wa'].id,
                      company_id=t['ca'].id, reference_type="expense", reference_id=None, created_at=now + timedelta(seconds=2))
    db.add_all([txa, txb]); db.flush()
    r = client.login(t['ua']).delete(f'/api/finance/expenses/{e2.id}')
    assert r.status_code == 204
    db.expire_all()
    assert db.get(Expense, e2.id).voided_at is not None   # T1.19: void
    assert db.get(Transaction, txa.id).voided_at is None and db.get(Transaction, txb.id).voided_at is None


# ─── POST /finance/transactions ──────────────────────────────────────────────

def test_create_transaction_reference_whitelist_and_other_income(client, db, two):
    """Mezon 6: customer_payment → 400; "Boshqa kirim" branch_id siz 201, company/user/branch yoziladi."""
    t = two
    c = client.login(t['ua'])
    before = _bal(db, t['wa'])
    n_tx = db.query(Transaction).count()
    for rt in ("customer_payment", "sale", "supplier_payment", "expense"):
        r = c.post('/api/finance/transactions', json={"type": "income", "amount": 100, "wallet_id": t['wa'].id, "reference_type": rt, "reference_id": 1})
        assert r.status_code == 400, (rt, r.text)
    assert db.query(Transaction).count() == n_tx and _bal(db, t['wa']) == before

    # KirimTolovlar "Boshqa kirim" so'rovi (branch_id yo'q)
    r = c.post('/api/finance/transactions', json={
        "type": "income", "amount": 150, "currency_code": "UZS", "payment_type": "card",
        "description": "Boshqa kirim", "wallet_id": t['wa'].id, "reference_type": "other_income"})
    assert r.status_code == 201, r.text
    tx = db.get(Transaction, r.json()['id'])
    assert tx.company_id == t['ca'].id and tx.user_id == t['ua'].id and tx.branch_id == t['ba'].id
    assert tx.reference_type == "other_income" and tx.reference_id is None and tx.payment_type == "card"
    assert _bal(db, t['wa']) == before + Decimal(150)
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "other_income", KassaMovement.reference_id == tx.id).one()
    assert mv.direction == "in" and mv.payment_type == "card" and mv.company_id == t['ca'].id

    # Havolasiz (reference_type None) chiqim — ham ruxsat
    r = c.post('/api/finance/transactions', json={"type": "expense", "amount": 50, "wallet_id": t['wa'].id})
    assert r.status_code == 201 and _bal(db, t['wa']) == before + Decimal(100)

    # Valyutali kirim — hamyon balansi o'zgarmaydi, harakat yoziladi
    r = c.post('/api/finance/transactions', json={"type": "income", "amount": 10, "currency_code": "usd", "wallet_id": t['wa'].id, "reference_type": "other_income"})
    assert r.status_code == 201 and r.json()['currency_code'] == "USD"
    assert _bal(db, t['wa']) == before + Decimal(100)


def test_create_transaction_foreign_and_validation(client, db, two):
    """Begona kassa → 404, begona filial → 400, amount <= 0 va noto'g'ri type → 422; hech narsa yozilmaydi."""
    t = two
    c = client.login(t['ua'])
    n_tx = db.query(Transaction).count()
    before_b = _bal(db, t['wb'])
    r = c.post('/api/finance/transactions', json={"type": "income", "amount": 100, "wallet_id": t['wb'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    r = c.post('/api/finance/transactions', json={"type": "income", "amount": 100, "branch_id": t['bb'].id})
    assert r.status_code == 400 and r.json()['detail'] == BRANCH_400
    for body in ({"type": "income", "amount": 0}, {"type": "expense", "amount": -5}, {"type": "transfer", "amount": 5}):
        r = c.post('/api/finance/transactions', json=body)
        assert r.status_code == 422, (body, r.text)
    assert db.query(Transaction).count() == n_tx and _bal(db, t['wb']) == before_b


# ─── PUT/DELETE /finance/transactions/{id} ───────────────────────────────────

def test_system_transactions_locked(client, db, two):
    """Mezon 8: sale, sale_refund, shift tranzaksiyalarini PUT/DELETE qilish 400."""
    t = two
    before = _bal(db, t['wa'])
    ids = []
    for rt in ("sale", "sale_refund", "shift"):
        tx = Transaction(branch_id=t['ba'].id, type="income", amount=Decimal(100), wallet_id=t['wa'].id,
                         company_id=t['ca'].id, reference_type=rt, reference_id=1)
        db.add(tx); db.flush(); ids.append(tx.id)
    c = client.login(t['ua'])
    for tx_id in ids:
        r = c.put(f'/api/finance/transactions/{tx_id}', json={"amount": 50})
        assert r.status_code == 400 and r.json()['detail'] == LOCKED_400
        r = c.delete(f'/api/finance/transactions/{tx_id}')
        assert r.status_code == 400 and r.json()['detail'] == LOCKED_400
        assert db.get(Transaction, tx_id) is not None and Decimal(str(db.get(Transaction, tx_id).amount)) == Decimal(100)
    assert _bal(db, t['wa']) == before
    # begona korxona → 404
    assert client.login(t['ub']).delete(f'/api/finance/transactions/{ids[0]}').status_code == 404


def test_update_transaction_amount_nonpositive_422(client, db, two):
    t = two
    tx = Transaction(branch_id=t['ba'].id, type="income", amount=Decimal(100), wallet_id=t['wa'].id,
                     company_id=t['ca'].id, reference_type="other_income")
    db.add(tx); db.flush()
    for amt in (0, -1):
        r = client.login(t['ua']).put(f'/api/finance/transactions/{tx.id}', json={"amount": amt, "wallet_id": t['wa'].id})
        assert r.status_code == 422


def test_update_and_delete_customer_payment_uzs_only(client, db, two):
    """customer_payment: UZS bo'lsa debt_balance VA debt_balances['UZS'] birga o'zgaradi;
    valyutali bo'lsa PUT/DELETE 400."""
    t = two
    cust = _customer(db, t['ca'], debt=5000)
    tx = Transaction(branch_id=t['ba'].id, type="income", amount=Decimal(1000), wallet_id=t['wa'].id,
                     company_id=t['ca'].id, currency_code="UZS", reference_type="customer_payment", reference_id=cust.id)
    db.add(tx); db.flush()
    before = _bal(db, t['wa'])
    c = client.login(t['ua'])

    # T2.6: mijoz to'lovining summasini PUT bilan o'zgartirib bo'lmaydi (taqsimot/jurnal buziladi) — 400, hech narsa o'zgarmaydi
    r = c.put(f'/api/finance/transactions/{tx.id}', json={"amount": 1500, "wallet_id": t['wa'].id})
    assert r.status_code == 400, r.text
    db.refresh(cust)
    assert Decimal(str(cust.debt_balance)) == Decimal(5000) and cust.debt_balances["UZS"] == 5000.0
    assert _bal(db, t['wa']) == before

    r = c.delete(f'/api/finance/transactions/{tx.id}')
    assert r.status_code == 204
    db.expire_all()
    assert Decimal(str(cust.debt_balance)) == Decimal(6000) and cust.debt_balances["UZS"] == 6000.0
    assert _bal(db, t['wa']) == before - Decimal(1000)

    # Valyutali mijoz to'lovi: PUT (summa o'zgarishi) — 400; DELETE (T2.6) — 204 va qarz o'sha valyuta chelagiga qaytadi
    txu = Transaction(branch_id=t['ba'].id, type="income", amount=Decimal(10), wallet_id=t['wa'].id,
                      company_id=t['ca'].id, currency_code="USD", reference_type="customer_payment", reference_id=cust.id)
    db.add(txu); db.flush()
    b2 = _bal(db, t['wa'])
    assert c.put(f'/api/finance/transactions/{txu.id}', json={"amount": 20, "wallet_id": t['wa'].id}).status_code == 400
    assert c.delete(f'/api/finance/transactions/{txu.id}').status_code == 204
    db.expire_all()
    assert _bal(db, t['wa']) == b2                       # UZS kassa balansiga tegmaydi
    assert cust.debt_balances["UZS"] == 6000.0 and cust.debt_balances["USD"] == 10.0


def test_update_transaction_wallet_switch_syncs_movement_and_session(client, db, two):
    """PUT: kassa almashsa eski/yangi balans, kassa harakati (hamyon+summa bo'yicha mosi) va session_id yangilanadi."""
    t = two
    c = client.login(t['ua'])
    r = c.post('/api/finance/transactions', json={"type": "income", "amount": 100, "wallet_id": t['wa'].id, "reference_type": "other_income"})
    tx_id = r.json()['id']
    w2 = _wallet(db, t['ca'], t['ba2'], name="Ikkinchi")
    s2 = KassaSession(wallet_id=w2.id, company_id=t['ca'].id, status="open")
    db.add(s2); db.flush()
    b1, b2 = _bal(db, t['wa']), _bal(db, w2)

    # begona kassaga o'tkazish — 404
    assert c.put(f'/api/finance/transactions/{tx_id}', json={"amount": 100, "wallet_id": t['wb'].id}).status_code == 404

    r = c.put(f'/api/finance/transactions/{tx_id}', json={"amount": 120, "wallet_id": w2.id, "payment_type": "card"})
    assert r.status_code == 200, r.text
    assert _bal(db, t['wa']) == b1 - Decimal(100) and _bal(db, w2) == b2 + Decimal(120)
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "other_income", KassaMovement.reference_id == tx_id).one()
    assert mv.wallet_id == w2.id and mv.session_id == s2.id and Decimal(str(mv.amount)) == Decimal(120) and mv.payment_type == "card"

    # DELETE: balans va harakat qaytadi
    assert c.delete(f'/api/finance/transactions/{tx_id}').status_code == 204
    db.expire_all()
    assert _bal(db, w2) == b2
    # T1.19: asl harakat qoladi, teskari (void) harakat yoziladi
    assert _count(db, KassaMovement, reference_type="transaction_void", reference_id=tx_id) == 1


def test_update_expense_transaction_syncs_expense(client, db, two):
    """PUT expense tranzaksiyasi: Expense.amount yangilanadi, aynan shu xarajatning kassa harakati o'zgaradi."""
    t = two
    c = client.login(t['ua'])
    e1 = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 100, "wallet_id": t['wa'].id}).json()['id']
    e2 = c.post('/api/finance/expenses', json={"category_id": t['cat_a'].id, "amount": 100, "wallet_id": t['wa'].id}).json()['id']
    tx1 = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == e1).one()
    before = _bal(db, t['wa'])
    r = c.put(f'/api/finance/transactions/{tx1.id}', json={"amount": 130, "wallet_id": t['wa'].id})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert Decimal(str(db.get(Expense, e1).amount)) == Decimal(130)
    assert Decimal(str(db.get(Expense, e2).amount)) == Decimal(100)
    mv1 = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense", KassaMovement.reference_id == e1).one()
    mv2 = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense", KassaMovement.reference_id == e2).one()
    assert Decimal(str(mv1.amount)) == Decimal(130) and Decimal(str(mv2.amount)) == Decimal(100)
    assert _bal(db, t['wa']) == before - Decimal(30)


# ─── Qarz to'lovlari: summa > 0 ──────────────────────────────────────────────

def test_debt_payments_reject_nonpositive(client, db, two):
    """Mezon 7: customer-debts/pay, supplier-debts/pay → 422; customers/pay-debt → 400;
    debt_balance va wallet.balance o'zgarmaydi."""
    t = two
    cust = _customer(db, t['ca'], debt=5000)
    sup = _supplier(db, t['ca'], debt=5000)
    before = _bal(db, t['wa'])
    n_tx = db.query(Transaction).count()
    c = client.login(t['ua'])
    for amt in (0, -500):
        r = c.post(f'/api/finance/customer-debts/{cust.id}/pay', json={"amount": amt, "wallet_id": t['wa'].id})
        assert r.status_code == 422, r.text
        r = c.post(f'/api/finance/supplier-debts/{sup.id}/pay', json={"amount": amt, "wallet_id": t['wa'].id})
        assert r.status_code == 422, r.text
        r = c.post(f'/api/customers/{cust.id}/pay-debt', json={"reason": "x", "wallet_id": t['wa'].id,
                                                               "payments": [{"amount": 100}, {"amount": amt}]})
        assert r.status_code == 400 and r.json()['detail'] == "To'lov miqdori musbat bo'lishi kerak", r.text   # T2.6 xabari
    # eski mijoz: payments siz, amount berilmagan (standart 0) → 400
    r = c.post(f'/api/customers/{cust.id}/pay-debt', json={"reason": "x", "wallet_id": t['wa'].id})
    assert r.status_code == 400
    db.expire_all()
    assert Decimal(str(cust.debt_balance)) == Decimal(5000) and Decimal(str(sup.debt_balance)) == Decimal(5000)
    assert _bal(db, t['wa']) == before and db.query(Transaction).count() == n_tx

    # ijobiy yo'l: musbat summa ishlaydi, tranzaksiyada user_id bor
    r = c.post(f'/api/finance/customer-debts/{cust.id}/pay', json={"amount": 500, "wallet_id": t['wa'].id})
    assert r.status_code == 200, r.text
    tx = db.query(Transaction).filter(Transaction.reference_type == "customer_payment", Transaction.reference_id == cust.id).one()
    assert tx.user_id == t['ua'].id and tx.company_id == t['ca'].id
    assert _bal(db, t['wa']) == before + Decimal(500)
    r = c.post(f'/api/customers/{cust.id}/pay-debt', json={"reason": "x", "wallet_id": t['wa'].id, "payments": [{"amount": 100}]})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert Decimal(str(cust.debt_balance)) == Decimal(4400)


# ─── Migratsiya: t0_6 ────────────────────────────────────────────────────────

def _load_migration():
    path = os.path.join(ROOT, 'alembic', 'versions', 't0_6_fix_expense_tx_links.py')
    spec = importlib.util.spec_from_file_location('mig_t0_6', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_fixes_links_and_branches_idempotent(db, two):
    """Mezon 9: company_id kassadan, reference_id faqat 1:1 da, begona filial tuzatiladi (audit bilan);
    ikki marta ishga tushirilsa natija o'zgarmaydi; downgrade filialni qaytaradi."""
    t = two
    mod = _load_migration()
    assert mod.revision == 't0_6' and mod.down_revision == 't0_4'
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # A korxona xarajati B filialiga yozilgan (Finance.jsx branch_id=1 holati), kassa A da (filial ba)
    e_bad = Expense(branch_id=t['bb'].id, category_id=t['cat_a'].id, amount=Decimal(100), company_id=t['ca'].id,
                    wallet_id=t['wa'].id, created_at=now)
    # 1:1 nomzod: company_id va reference_id yo'q
    db.add(e_bad); db.flush()
    tx_bad = Transaction(branch_id=t['bb'].id, type="expense", amount=Decimal(100), wallet_id=t['wa'].id,
                         company_id=None, reference_type="expense", reference_id=None, created_at=now + timedelta(seconds=2))
    # Ikki ma'noli: bitta xarajatga ikkita tranzaksiya
    e_amb = Expense(branch_id=t['ba'].id, category_id=t['cat_a'].id, amount=Decimal(55), company_id=t['ca'].id,
                    wallet_id=None, created_at=now)
    db.add(e_amb); db.flush()
    tx_a1 = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(55), wallet_id=None,
                        company_id=None, reference_type="expense", reference_id=None, created_at=now + timedelta(seconds=1))
    tx_a2 = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(55), wallet_id=None,
                        company_id=None, reference_type="expense", reference_id=None, created_at=now + timedelta(seconds=3))
    # Kassasiz, uzoq vaqtli: tegilmaydi
    tx_far = Transaction(branch_id=t['ba'].id, type="expense", amount=Decimal(100), wallet_id=None,
                         company_id=None, reference_type="expense", reference_id=None, created_at=now + timedelta(minutes=5))
    # Kassasi bo'lmagan va filiali ham begona xarajat → korxonaning eng kichik id li filiali
    e_nowallet = Expense(branch_id=t['bb'].id, category_id=t['cat_a'].id, amount=Decimal(7), company_id=t['ca'].id,
                         wallet_id=None, created_at=now)
    db.add_all([tx_bad, tx_a1, tx_a2, tx_far, e_nowallet]); db.flush()

    conn = db.connection()

    class FakeOp:
        @staticmethod
        def get_bind():
            return conn

    mod.op = FakeOp
    mod.upgrade()
    db.expire_all()

    assert tx_bad.company_id == t['ca'].id and tx_bad.reference_id == e_bad.id
    assert e_bad.branch_id == t['ba'].id            # kassa filiali
    assert tx_bad.branch_id == t['ba'].id           # bog'langan tranzaksiya ham
    assert e_nowallet.branch_id == t['ba'].id       # eng kichik id li faol filial
    assert tx_a1.reference_id is None and tx_a2.reference_id is None and tx_a1.company_id is None
    assert tx_far.reference_id is None and tx_far.company_id is None
    audit = conn.execute(text("SELECT expense_id, old_branch_id, new_branch_id FROM expense_fix_audit ORDER BY expense_id")).fetchall()
    assert [(r[0], r[1], r[2]) for r in audit] == [(e_bad.id, t['bb'].id, t['ba'].id), (e_nowallet.id, t['bb'].id, t['ba'].id)]

    # idempotent
    mod.upgrade()
    db.expire_all()
    assert conn.execute(text("SELECT count(*) FROM expense_fix_audit")).scalar() == 2
    assert tx_bad.reference_id == e_bad.id and e_bad.branch_id == t['ba'].id
    assert tx_a1.reference_id is None and tx_a2.reference_id is None

    # downgrade: filial eski qiymatga qaytadi, company_id/reference_id qoladi
    mod.downgrade()
    db.expire_all()
    assert e_bad.branch_id == t['bb'].id and e_nowallet.branch_id == t['bb'].id
    assert tx_bad.reference_id == e_bad.id and tx_bad.company_id == t['ca'].id
    assert conn.execute(text("SELECT count(*) FROM expense_fix_audit")).scalar() == 0


# ─── Frontend: branch_id=1 qolmagan, tizim yozuvlari uchun tugmalar yo'q ──────

def test_frontend_no_hardcoded_branch_and_locked_rows():
    fin = open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'Finance.jsx'), encoding='utf-8').read()
    assert "branch_id: 1" not in fin
    # T2.5: forma filiali defaultBranchId() bilan to'ldiriladi (finance.branchAuto matni endi ishlatilmaydi)
    assert "api.get('/branches')" in fin and "defaultBranchId" in fin
    chiqim = open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'ChiqimTolovlar.jsx'), encoding='utf-8').read()
    assert "['purchase_order', 'sale_refund', 'shift'].includes(g.reference_type)" in chiqim
    kirim = open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'KirimTolovlar.jsx'), encoding='utf-8').read()
    assert "['sale', 'shift'].includes(g.reference_type)" in kirim
    for lang in ('uz', 'ru', 'en'):
        src = open(os.path.join(ROOT, 'frontend', 'src', 'i18n', f'{lang}.js'), encoding='utf-8').read()
        for key in ("'finance.branch'", "'finance.branchAuto'", "'chiqimTolov.fromRelatedSection'", "'kirimTolov.fromRelatedSection'"):
            assert key in src, (lang, key)
