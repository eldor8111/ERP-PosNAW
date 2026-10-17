"""T1.11 — Smena: filial, kassa, kunlik yopish va hisobotlar.

Qamrov: POST /shifts/open (filial/kassa tekshiruvi, "Filial tanlang", parallel ochish -> 400), yopishda
expected_cash/difference/closed_by saqlanishi va sanalgan summa bilan inkassatsiya, kamomad Transaction'i,
yopilgan smenaga smenasiz sotuv tushmasligi, ikki marta yopish, begona/nofaol/boshqa filial kassasi,
GET /shifts (rol qoidalari, limit/skip, X-Total-Count, N+1 yo'q), Z-hisobot, summary, handover-wallets,
pos_require_shift (backend), kassa yopilishi (difference, expected/difference_summary, kamomad Transaction,
yopiq sessiya xarajatini o'zgartirish 409), GET /kassa/sessions, migratsiya fayli va frontend yordamchilari.
Har joyda ikki korxona izolyatsiyasi va ijobiy yo'l.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_11.py -q -p no:cacheprovider
"""
import itertools
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.inventory import StockLevel
from app.models.moliya import ExpenseCategory, KassaMovement, KassaSession, Transaction, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SalePayment, SaleStatus
from app.models.shift import Shift
from app.models.user import UserRole, UserWallet

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, *, active=True, is_open=True, personal=False, balance=0, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=active, is_open=is_open, is_personal=personal)
    db.add(w)
    db.flush()
    return w


def _attach(db, user, wallet, default=True):
    db.add(UserWallet(user_id=user.id, wallet_id=wallet.id, is_default=default, company_id=wallet.company_id))
    db.flush()


def _open_shift_row(db, user, company, branch, opening=0, opened_at=None, status="open"):
    s = Shift(cashier_id=user.id, branch_id=branch.id if branch else None, company_id=company.id, status=status,
              opened_at=opened_at or datetime.utcnow() - timedelta(hours=1), opening_cash=Decimal(opening))
    db.add(s)
    db.flush()
    return s


def _sell(db, user, company, shift, wallet, payments, *, created_at=None, number=None):
    """Sotuv: SalePayment + KassaMovement(in) + Wallet.balance. payments: [(tur, summa)]."""
    n = next(_seq)
    total = sum(Decimal(a) for _, a in payments)
    s = Sale(number=number or f"S111-{n}", cashier_id=user.id, total_amount=total, paid_amount=total,
             discount_amount=Decimal(0),
             paid_cash=sum(Decimal(a) for t, a in payments if t == "cash"),
             payment_type=PaymentType.cash if len(payments) == 1 and payments[0][0] == "cash" else PaymentType.mixed,
             company_id=company.id, shift_id=shift.id if shift else None)
    if created_at is not None:
        s.created_at = created_at
    db.add(s)
    db.flush()
    for ptype, amt in payments:
        amt = Decimal(amt)
        db.add(SalePayment(sale_id=s.id, payment_type=ptype, amount=amt))
        db.add(KassaMovement(wallet_id=wallet.id, company_id=company.id, direction="in", payment_type=ptype,
                             amount=amt, currency="UZS", reference_type="sale", reference_id=s.id,
                             created_by=user.id))
        wallet.balance = Decimal(str(wallet.balance or 0)) + amt
    db.flush()
    return s


def _product(db, company, wh, qty=100):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T111-{n}", barcode=f"B111-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


def _sale_body(p, wh, qty=1):
    amt = 1000 * qty
    return {"items": [{"product_id": p.id, "quantity": qty, "unit_price": 1000}], "payment_type": "cash",
            "paid_amount": amt, "paid_cash": amt, "payments": [{"type": "cash", "amount": amt}],
            "warehouse_id": wh.id}


def _fresh(db, obj):
    db.expire_all()
    return db.get(type(obj), obj.id)


@pytest.fixture
def w(db, mk):
    """Korxona A: 2 faol filial (a1, a2) + nofaol filial; admin, manager (a1), 2 kassir; kassalar. Korxona B."""
    ca = mk.company()
    a1 = mk.branch(ca, name="Yunusobod")
    a2 = mk.branch(ca, name="Chilonzor")
    a_off = mk.branch(ca, name="Yopiq", is_active=False)
    wh1 = mk.warehouse(ca, a1)
    admin = mk.user(ca, role=UserRole.admin)                       # filialsiz admin
    manager = mk.user(ca, role=UserRole.manager, branch=a1)
    cash1 = mk.user(ca, role=UserRole.cashier, branch=a1)
    cash1b = mk.user(ca, role=UserRole.cashier, branch=a1)
    cash2 = mk.user(ca, role=UserRole.cashier, branch=a2)
    src = _wallet(db, ca, a1, name="Kassir kassasi")
    main = _wallet(db, ca, a1, name="Asosiy kassa")
    chil = _wallet(db, ca, a2, name="Chilonzor kassa")
    hand = _wallet(db, ca, a1, personal=True, name="Kuryer qo'l kassasi")
    dead = _wallet(db, ca, a1, active=False, name="Nofaol kassa")
    _attach(db, cash1, src)
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    cash_b = mk.user(cb, role=UserRole.cashier, branch=bb)
    wallet_b = _wallet(db, cb, bb, name="B kassa")
    prod = _product(db, ca, wh1)
    return SimpleNamespace(ca=ca, a1=a1, a2=a2, a_off=a_off, wh1=wh1, admin=admin, manager=manager, cash1=cash1,
                           cash1b=cash1b, cash2=cash2, src=src, main=main, chil=chil, hand=hand, dead=dead,
                           cb=cb, bb=bb, admin_b=admin_b, cash_b=cash_b, wallet_b=wallet_b, prod=prod)


# ── 1. POST /shifts/open ─────────────────────────────────────────────────────

def test_open_foreign_inactive_and_other_branch(client, db, w):
    cl = client.login(w.cash1)
    # begona korxona filiali — rad (404/400), smena yaratilmaydi
    assert cl.post('/api/shifts/open', json={'branch_id': w.bb.id}).status_code in (400, 404)
    # nofaol filial — rad
    assert cl.post('/api/shifts/open', json={'branch_id': w.a_off.id}).status_code in (400, 404)
    # kassir o'zining filialidan boshqa faol filial — 403
    assert cl.post('/api/shifts/open', json={'branch_id': w.a2.id}).status_code == 403
    assert db.query(Shift).filter(Shift.cashier_id == w.cash1.id).count() == 0
    # ijobiy yo'l: o'z filiali
    r = cl.post('/api/shifts/open', json={'branch_id': w.a1.id, 'opening_cash': 100, 'note': 'Ertalab'})
    assert r.status_code == 201, r.text
    j = r.json()
    assert j['branch_id'] == w.a1.id and j['branch_name'] == "Yunusobod" and j['status'] == 'open'
    s = _fresh(db, db.get(Shift, j['id']))
    assert s.note_open == 'Ertalab' and s.company_id == w.ca.id


def test_open_requires_branch_choice_when_multiple_active(client, db, w, mk):
    # filialsiz admin, 2 faol filial -> "Filial tanlang"
    r = client.login(w.admin).post('/api/shifts/open', json={'opening_cash': 0})
    assert r.status_code == 400 and r.json()['detail'] == "Filial tanlang"
    assert db.query(Shift).filter(Shift.cashier_id == w.admin.id).count() == 0
    # aniq filial bilan — ochiladi
    r = client.login(w.admin).post('/api/shifts/open', json={'opening_cash': 0, 'branch_id': w.a2.id})
    assert r.status_code == 201 and r.json()['branch_id'] == w.a2.id
    # bitta faol filialli korxonada avto-tanlanadi
    c, b, _wh, adm = mk.tenant(UserRole.admin)
    adm.branch_id = None
    db.flush()
    r = client.login(adm).post('/api/shifts/open', json={})
    assert r.status_code == 201 and r.json()['branch_id'] == b.id


def test_open_negative_cash_rejected(client, w):
    assert client.login(w.cash1).post('/api/shifts/open', json={'opening_cash': -1}).status_code == 422


def test_open_wallet_validation(client, db, w):
    cl = client.login(w.admin)
    body = {'branch_id': w.a1.id, 'opening_cash': 0}
    assert cl.post('/api/shifts/open', json={**body, 'wallet_id': w.wallet_b.id}).status_code == 404   # begona korxona
    assert cl.post('/api/shifts/open', json={**body, 'wallet_id': 987654}).status_code == 404
    r = cl.post('/api/shifts/open', json={**body, 'wallet_id': w.dead.id})
    assert r.status_code == 400 and r.json()['detail'] == "Kassa nofaol"
    r = cl.post('/api/shifts/open', json={**body, 'wallet_id': w.chil.id})
    assert r.status_code == 400 and r.json()['detail'] == "Kassa boshqa filialga tegishli"
    assert db.query(Shift).filter(Shift.cashier_id == w.admin.id).count() == 0
    r = cl.post('/api/shifts/open', json={**body, 'wallet_id': w.main.id})
    assert r.status_code == 201 and r.json()['wallet_id'] == w.main.id


def test_second_open_is_400_and_db_index_blocks_parallel(client, db, w, monkeypatch):
    cl = client.login(w.cash1)
    assert cl.post('/api/shifts/open', json={}).status_code == 201
    r = cl.post('/api/shifts/open', json={})
    assert r.status_code == 400 and r.json()['detail'] == "Kassir uchun faol smena allaqachon mavjud"
    # bazadagi indeks ikkinchi ochiq smenani rad etadi
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _open_shift_row(db, w.cash1, w.ca, w.a1)
    # parallel holat: tekshiruvdan o'tib ketgan so'rovda flush IntegrityError beradi -> 500 emas, 400
    db.commit()
    orig = Session.flush

    def boom(self, *a, **kw):
        if any(isinstance(o, Shift) for o in self.new):
            raise IntegrityError("INSERT INTO shifts", {}, Exception("unique"))
        return orig(self, *a, **kw)

    monkeypatch.setattr(Session, 'flush', boom)
    r = client.login(w.cash1b).post('/api/shifts/open', json={})
    assert r.status_code == 400 and r.json()['detail'] == "Kassir uchun faol smena allaqachon mavjud"


# ── 2. Yopish: expected/difference/handover/kamomad ──────────────────────────

@pytest.fixture
def day(db, w):
    """cash1: ochilish 100 000, naqd sotuv 1 900 000 (kassir kassasi `src`ga tushgan)."""
    shift = _open_shift_row(db, w.cash1, w.ca, w.a1, opening=100000)
    sale = _sell(db, w.cash1, w.ca, shift, w.src, [("cash", 1900000)])
    return SimpleNamespace(shift=shift, sale=sale)


def test_close_saves_expected_difference_and_handover(client, db, w, day):
    bal_src = Decimal(str(w.src.balance))
    r = client.login(w.cash1).post(f'/api/shifts/{day.shift.id}/close',
                                   json={'closing_cash': 1950000, 'wallet_id': w.main.id, 'note': 'Sanadim'})
    assert r.status_code == 200, r.text
    j = r.json()
    assert float(j['expected_cash']) == 2000000.0 and float(j['difference']) == -50000.0
    assert float(j['closing_cash']) == 1950000.0 and float(j['handed_over_cash']) == 1850000.0
    s = _fresh(db, day.shift)
    assert s.status == 'closed' and s.closed_by == w.cash1.id and s.note_close == 'Sanadim'
    assert Decimal(str(s.expected_cash)) == 2000000 and Decimal(str(s.cash_difference)) == -50000
    assert Decimal(str(s.difference)) == -50000
    assert s.wallet_id == w.src.id
    # hamyonga aniq 1 850 000 tushadi (opening kassada qoladi)
    assert Decimal(str(_fresh(db, w.main).balance)) == 1850000
    assert Decimal(str(_fresh(db, w.src).balance)) == bal_src - 1850000
    # kamomad xarajat bo'lib filial bo'yicha yoziladi
    tx = db.query(Transaction).filter(Transaction.reference_type == 'shift_shortage',
                                      Transaction.reference_id == day.shift.id).all()
    assert len(tx) == 1 and tx[0].type == 'expense' and Decimal(str(tx[0].amount)) == 50000
    assert tx[0].branch_id == w.a1.id and tx[0].company_id == w.ca.id
    # smena ro'yxatida ham ko'rinadi
    row = client.login(w.cash1).get('/api/shifts').json()[0]
    assert float(row['expected_cash']) == 2000000.0 and float(row['difference']) == -50000.0


def test_close_surplus_writes_income(client, db, w, day):
    r = client.login(w.cash1).post('/api/shifts/close', json={'closing_cash': 2010000})
    assert r.status_code == 200, r.text
    assert float(r.json()['difference']) == 10000.0
    tx = db.query(Transaction).filter(Transaction.reference_type == 'shift_surplus').one()
    assert tx.type == 'income' and Decimal(str(tx.amount)) == 10000


def test_close_without_count_no_difference_transaction(client, db, w, day):
    r = client.login(w.cash1).post('/api/shifts/close', json={})
    assert r.status_code == 200, r.text
    assert float(r.json()['expected_cash']) == 2000000.0 and float(r.json()['difference']) == 0.0
    assert db.query(Transaction).filter(Transaction.reference_type.in_(('shift_shortage', 'shift_surplus'))).count() == 0


def test_close_negative_closing_cash_422(client, w, day):
    assert client.login(w.cash1).post('/api/shifts/close', json={'closing_cash': -5}).status_code == 422


def test_second_close_does_not_repeat_handover(client, db, w, day):
    cl = client.login(w.cash1)
    assert cl.post(f'/api/shifts/{day.shift.id}/close', json={'closing_cash': 2000000, 'wallet_id': w.main.id}).status_code == 200
    main_bal = Decimal(str(_fresh(db, w.main).balance))
    r = cl.post(f'/api/shifts/{day.shift.id}/close', json={'closing_cash': 2000000, 'wallet_id': w.main.id})
    assert r.status_code == 400 and r.json()['detail'] == "Smena allaqachon yopilgan"
    assert Decimal(str(_fresh(db, w.main).balance)) == main_bal == 1900000
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == 'transfer_in',
                                          KassaMovement.wallet_id == w.main.id).count() == 1


def test_close_rejects_foreign_inactive_other_branch_wallet(client, db, w, day):
    cl = client.login(w.cash1)
    for wid, codes in ((w.wallet_b.id, (404,)), (w.dead.id, (404, 400)), (w.chil.id, (400, 403, 404))):
        r = cl.post(f'/api/shifts/{day.shift.id}/close', json={'closing_cash': 2000000, 'wallet_id': wid})
        assert r.status_code in codes, (wid, r.status_code, r.text)
        s = _fresh(db, day.shift)
        assert s.status == 'open' and s.closed_at is None and s.closed_by is None
    assert db.query(Transaction).filter(Transaction.reference_type.in_(('shift_shortage', 'shift_surplus'))).count() == 0


def test_close_by_manager_branch_rule(client, db, w, day):
    # boshqa filial menejeri yopa olmaydi, o'z filiali menejeri yopadi, boshqa kassir yopa olmaydi
    other_mgr = db.query(type(w.manager)).get(w.manager.id)
    assert client.login(w.cash1b).post(f'/api/shifts/{day.shift.id}/close', json={}).status_code == 403
    mgr_b = type(w.manager)(name='M2', phone='998900000099', hashed_password='x', role=UserRole.manager,
                            company_id=w.ca.id, branch_id=w.a2.id)
    db.add(mgr_b)
    db.flush()
    assert client.login(mgr_b).post(f'/api/shifts/{day.shift.id}/close', json={}).status_code == 403
    assert client.login(w.admin_b).post(f'/api/shifts/{day.shift.id}/close', json={}).status_code == 404
    assert _fresh(db, day.shift).status == 'open'
    r = client.login(other_mgr).post(f'/api/shifts/{day.shift.id}/close', json={'closing_cash': 2000000})
    assert r.status_code == 200, r.text
    assert _fresh(db, day.shift).closed_by == w.manager.id


# ── 3. Smenasiz sotuv yopilgan smena hisobotiga tushmaydi ────────────────────

def test_unlinked_sale_after_close_not_in_z_report(client, db, w, day):
    # smena davomidagi smenasiz sotuv hisobga kiradi
    _sell(db, w.cash1, w.ca, None, w.src, [("cash", 5000)], created_at=datetime.utcnow() - timedelta(minutes=10))
    cl = client.login(w.cash1)
    assert cl.post('/api/shifts/close', json={}).status_code == 200
    closed_at = _fresh(db, day.shift).closed_at
    # yopilgandan keyin qilingan smenasiz sotuv — kirmaydi
    _sell(db, w.cash1, w.ca, None, w.src, [("cash", 777000)], created_at=closed_at + timedelta(minutes=5))
    z = cl.get(f'/api/shifts/{day.shift.id}/z-report').json()
    assert z['sales']['count'] == 2
    assert z['sales']['by_payment']['cash']['UZS'] == 1905000.0
    assert z['cash']['cash_sales'] == 1905000.0


# ── 4. GET /shifts: rollar, limit/skip, N+1 ──────────────────────────────────

def test_list_roles_pagination_and_no_n_plus_one(client, db, w):
    mine = [_open_shift_row(db, w.cash1, w.ca, w.a1, opened_at=datetime.utcnow() - timedelta(days=i + 1),
                            status='closed') for i in range(3)]
    other = _open_shift_row(db, w.cash1b, w.ca, w.a1)
    chil = _open_shift_row(db, w.cash2, w.ca, w.a2)
    foreign = _open_shift_row(db, w.cash_b, w.cb, w.bb)

    ids = lambda r: {x['id'] for x in r.json()}
    # kassir faqat o'z smenalari
    r = client.login(w.cash1).get('/api/shifts')
    assert ids(r) == {s.id for s in mine}
    # manager faqat o'z filiali (a1): Chilonzor va begona korxona yo'q
    r = client.login(w.manager).get('/api/shifts')
    assert ids(r) == {s.id for s in mine} | {other.id}
    # admin: butun korxona, begona korxona yo'q; filial filtri ishlaydi
    r = client.login(w.admin).get('/api/shifts')
    assert ids(r) == {s.id for s in mine} | {other.id, chil.id}
    assert ids(client.login(w.admin).get('/api/shifts', params={'branch_id': w.a2.id})) == {chil.id}
    assert ids(client.login(w.admin).get('/api/shifts', params={'cashier_id': w.cash1b.id})) == {other.id}
    # begona korxona admini faqat o'zinikini
    assert ids(client.login(w.admin_b).get('/api/shifts')) == {foreign.id}
    # limit/skip/X-Total-Count
    r = client.login(w.admin).get('/api/shifts', params={'limit': 2, 'skip': 0})
    assert len(r.json()) == 2 and r.headers['X-Total-Count'] == '5'
    r2 = client.login(w.admin).get('/api/shifts', params={'limit': 2, 'skip': 4})
    assert len(r2.json()) == 1
    assert client.login(w.admin).get('/api/shifts', params={'limit': 500}).status_code == 422
    # sana filtri
    today = datetime.utcnow().date().isoformat()
    r = client.login(w.admin).get('/api/shifts', params={'date_from': today, 'date_to': today})
    assert ids(r) == {other.id, chil.id}

    # N+1 yo'q: kassir nomi uchun alohida `users` so'rovi yo'q
    stmts = []

    def _on(conn, cursor, statement, params, context, executemany):
        stmts.append(statement)

    bind = db.get_bind()
    event.listen(bind, 'before_cursor_execute', _on)
    try:
        r = client.login(w.admin).get('/api/shifts')
    finally:
        event.remove(bind, 'before_cursor_execute', _on)
    assert r.status_code == 200 and all(x['cashier_name'] for x in r.json())
    per_row = [s for s in stmts if re.search(r'FROM users\s+WHERE users\.id\s*=', s)]
    assert per_row == []


# ── 5. GET /shifts/{id}, Z-hisobot ───────────────────────────────────────────

def test_get_shift_permissions_and_schema(client, db, w, day):
    sid = day.shift.id
    j = client.login(w.cash1).get(f'/api/shifts/{sid}').json()
    assert j['cashier_name'] == w.cash1.name and j['branch_name'] == "Yunusobod" and j['status'] == 'open'
    assert client.login(w.manager).get(f'/api/shifts/{sid}').status_code == 200
    assert client.login(w.admin).get(f'/api/shifts/{sid}').status_code == 200
    assert client.login(w.cash1b).get(f'/api/shifts/{sid}').status_code == 403
    assert client.login(w.cash2).get(f'/api/shifts/{sid}/z-report').status_code == 403
    assert client.login(w.admin_b).get(f'/api/shifts/{sid}').status_code == 404
    assert client.login(w.admin_b).get(f'/api/shifts/{sid}/z-report').status_code == 404
    assert client.login(w.admin).get('/api/shifts/999999').status_code == 404


def test_z_report_sums(client, db, w):
    shift = _open_shift_row(db, w.cash1, w.ca, w.a1, opening=100000)
    _sell(db, w.cash1, w.ca, shift, w.src, [("cash", 100000), ("card", 50000)])
    _sell(db, w.cash1, w.ca, shift, w.src, [("cash", 40000)])
    # qaytarish hujjati (R...): naqd 20 000
    ret = Sale(number="R-T111-1", cashier_id=w.cash1.id, total_amount=Decimal(20000), paid_amount=Decimal(20000),
               paid_cash=Decimal(20000), discount_amount=Decimal(0), payment_type=PaymentType.cash,
               status=SaleStatus.refunded, company_id=w.ca.id, shift_id=shift.id)
    db.add(ret)
    # bekor qilingan sotuv hisobga kirmaydi
    canc = _sell(db, w.cash1, w.ca, shift, w.src, [("cash", 999000)])
    canc.status = SaleStatus.cancelled
    # mijoz qarz to'lovi: naqd 30 000
    db.add(KassaMovement(wallet_id=w.src.id, company_id=w.ca.id, direction="in", payment_type="cash", amount=30000,
                         currency="UZS", reference_type="customer_payment", created_by=w.cash1.id))
    db.flush()
    z = client.login(w.cash1).get(f'/api/shifts/{shift.id}/z-report').json()
    assert z['sales']['count'] == 2 and z['sales']['total_amount'] == 190000.0
    assert z['sales']['by_payment'] == {'cash': {'UZS': 140000.0}, 'card': {'UZS': 50000.0}}
    assert z['returns']['count'] == 1 and z['returns']['by_payment'] == {'cash': {'UZS': 20000.0}}
    assert z['debt_payments']['by_payment'] == {'cash': {'UZS': 30000.0}}
    c = z['cash']
    assert c['opening'] == 100000.0 and c['cash_sales'] == 140000.0 and c['returns_cash'] == 20000.0
    assert c['debt_cash'] == 30000.0 and c['expected'] == 250000.0   # 100 000 + 140 000 - 20 000 + 30 000
    assert c['counted'] is None and c['difference'] is None
    assert z['shift']['id'] == shift.id and z['generated_at']
    # /current bilan bir xil kutilgan summa
    cur = client.login(w.cash1).get('/api/shifts/current').json()
    assert Decimal(cur['expected_cash']) == 250000
    assert cur['branch_name'] == "Yunusobod" and 'wallet_id' in cur


# ── 6. summary / handover-wallets ────────────────────────────────────────────

def test_summary_and_handover_wallets(client, db, w, day):
    r = client.login(w.admin).get('/api/shifts/summary')
    assert r.status_code == 200
    by_branch = {x['branch_id']: x for x in r.json()}
    assert set(by_branch) == {w.a1.id, w.a2.id}                          # nofaol filial yo'q
    assert [s['id'] for s in by_branch[w.a1.id]['open_shifts']] == [day.shift.id]
    wnames = {x['name'] for x in by_branch[w.a1.id]['wallets']}
    assert "Kassir kassasi" in wnames and "Kuryer qo'l kassasi" not in wnames and "Nofaol kassa" not in wnames
    assert client.login(w.cash1).get('/api/shifts/summary').status_code == 403
    assert w.bb.id not in {x['branch_id'] for x in r.json()}
    # manager faqat o'z filiali
    mine = client.login(w.manager).get('/api/shifts/summary').json()
    assert [x['branch_id'] for x in mine] == [w.a1.id]

    # inkassatsiya kassalari: nofaol, shaxsiy, boshqa filial, begona korxona va kassir kassasi yo'q
    r = client.login(w.cash1).get('/api/shifts/handover-wallets')
    assert r.status_code == 200
    got = {x['id'] for x in r.json()}
    assert w.main.id in got
    assert not ({w.dead.id, w.hand.id, w.chil.id, w.wallet_b.id, w.src.id} & got)


# ── 7. pos_require_shift (backend) ───────────────────────────────────────────

def test_pos_require_shift_blocks_sale_without_open_shift(client, db, w):
    body = _sale_body(w.prod, w.wh1)
    cl = client.login(w.cash1)
    # standart (false): smenasiz sotuv avvalgidek o'tadi
    assert w.ca.pos_require_shift in (False, None)
    r = cl.post('/api/sales/', json=body)
    assert r.status_code == 200, r.text
    # yoqilgan: ochiq smena yo'q -> 400
    w.ca.pos_require_shift = True
    db.flush()
    r = cl.post('/api/sales/', json=body)
    assert r.status_code == 400 and r.json()['detail'] == "Smena ochilmagan. Avval smena oching."
    # smena ochilgach o'tadi
    assert cl.post('/api/shifts/open', json={}).status_code == 201
    r = cl.post('/api/sales/', json=body)
    assert r.status_code == 200, r.text
    # boshqa korxonaga ta'sir qilmaydi
    assert db.get(type(w.ca), w.cb.id).pos_require_shift in (False, None)


def test_company_setting_roundtrip_and_isolation(client, db, w):
    r = client.login(w.admin).put(f'/api/companies/{w.ca.id}', json={'pos_require_shift': True})
    assert r.status_code == 200, r.text
    assert r.json()['pos_require_shift'] is True
    assert client.login(w.admin).get('/api/companies/me/features').json()['require_shift'] is True
    assert client.login(w.admin_b).get('/api/companies/me/features').json()['require_shift'] is False
    # begona korxona admini A korxonaning sozlamasini o'zgartira olmaydi
    r = client.login(w.admin_b).put(f'/api/companies/{w.ca.id}', json={'pos_require_shift': False})
    assert r.status_code == 404
    assert _fresh(db, w.ca).pos_require_shift is True
    # null yuborilsa e'tiborsiz (NOT NULL ustun)
    assert client.login(w.admin).put(f'/api/companies/{w.ca.id}', json={'pos_require_shift': None}).status_code == 200
    assert _fresh(db, w.ca).pos_require_shift is True


# ── 8. Kassa yopilishi: difference, saqlash, kamomad Transaction, 409 ────────

@pytest.fixture
def kassa_day(db, w):
    k = _wallet(db, w.ca, w.a1, is_open=False, name="Kunlik kassa")
    cat = ExpenseCategory(name="Kommunal", company_id=w.ca.id)
    db.add(cat)
    db.flush()
    return SimpleNamespace(k=k, cat=cat)


def _open_and_expense(client, w, kd, opening=100000, expense=10000):
    cl = client.login(w.admin)
    r = cl.post(f'/api/kassa/{kd.k.id}/open', json={'opening_balance': opening})
    assert r.status_code == 200, r.text
    r = cl.post('/api/kassa/do-expense', json={'wallet_id': kd.k.id, 'category_id': kd.cat.id, 'amount': expense,
                                                 'payment_type': 'cash'})
    assert r.status_code == 200, r.text
    return r.json()['expense_id']


def test_kassa_close_returns_and_stores_difference(client, db, w, kassa_day):
    _open_and_expense(client, w, kassa_day)
    sess = db.query(KassaSession).filter(KassaSession.wallet_id == kassa_day.k.id).one()
    assert sess.branch_id == w.a1.id                                   # ochilganda filial yoziladi
    r = client.login(w.admin).post(f'/api/kassa/{kassa_day.k.id}/close',
                                   json={'actual_amounts': {'cash': {'UZS': 80000}}, 'note': 'sanadim'})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['difference'] == {'cash': {'UZS': 10000.0}}                # kamomad > 0
    s = _fresh(db, sess)
    assert s.status == 'closed' and s.branch_id == w.a1.id
    assert s.difference_summary == {'cash': {'UZS': 10000.0}}
    assert s.expected_summary['cash'] == [{'currency': 'UZS', 'value': 90000.0}]
    tx = db.query(Transaction).filter(Transaction.reference_type == 'closing_shortage').one()
    assert tx.type == 'expense' and Decimal(str(tx.amount)) == 10000
    assert tx.branch_id == w.a1.id and tx.wallet_id == kassa_day.k.id and tx.payment_type == 'cash'
    assert tx.currency_code == 'UZS'


def test_kassa_close_surplus_is_income(client, db, w, kassa_day):
    _open_and_expense(client, w, kassa_day)
    r = client.login(w.admin).post(f'/api/kassa/{kassa_day.k.id}/close', json={'actual_amounts': {'cash': {'UZS': 95000}}})
    assert r.status_code == 200 and r.json()['difference'] == {'cash': {'UZS': -5000.0}}
    tx = db.query(Transaction).filter(Transaction.reference_type == 'closing_surplus').one()
    assert tx.type == 'income' and Decimal(str(tx.amount)) == 5000


def test_kassa_close_no_difference_is_empty(client, db, w, kassa_day):
    _open_and_expense(client, w, kassa_day)
    r = client.login(w.admin).post(f'/api/kassa/{kassa_day.k.id}/close', json={'actual_amounts': {'cash': {'UZS': 90000}}})
    assert r.status_code == 200 and r.json()['difference'] == {}
    assert db.query(Transaction).filter(Transaction.reference_type.in_(('closing_shortage', 'closing_surplus'))).count() == 0


def test_closed_session_expense_cannot_be_changed(client, db, w, kassa_day):
    exp_id = _open_and_expense(client, w, kassa_day)
    cl = client.login(w.admin)
    # sessiya ochiq paytda o'zgartirish mumkin
    assert cl.put(f'/api/kassa/expense/{exp_id}', json={'description': 'yangi'}).status_code == 200
    assert cl.post(f'/api/kassa/{kassa_day.k.id}/close', json={'actual_amounts': {'cash': {'UZS': 90000}}}).status_code == 200
    r = cl.put(f'/api/kassa/expense/{exp_id}', json={'description': "o'zgartirish"})
    assert r.status_code == 409 and "Yopilgan kassa sessiyasidagi" in r.json()['detail']
    assert cl.delete(f'/api/kassa/expense/{exp_id}').status_code == 409
    assert w.ca.id and db.query(KassaMovement).filter(KassaMovement.reference_type == 'expense',
                                                      KassaMovement.reference_id == exp_id).count() == 1


def test_kassa_sessions_by_branch_with_totals(client, db, w, kassa_day):
    _open_and_expense(client, w, kassa_day)
    client.login(w.admin).post(f'/api/kassa/{kassa_day.k.id}/close', json={'actual_amounts': {'cash': {'UZS': 80000}}})
    # Chilonzor filialida ikkinchi kassa, farqsiz yopilgan
    k2 = _wallet(db, w.ca, w.a2, is_open=False, name="Chilonzor 2")
    cl = client.login(w.admin)
    assert cl.post(f'/api/kassa/{k2.id}/open', json={'opening_balance': 1000}).status_code == 200
    assert cl.post(f'/api/kassa/{k2.id}/close', json={'actual_amounts': {'cash': {'UZS': 1000}}}).status_code == 200
    # begona korxona kassasi (A admini ko'rmaydi)
    kb = _wallet(db, w.cb, w.bb, is_open=False, name="B 2")
    assert client.login(w.admin_b).post(f'/api/kassa/{kb.id}/open', json={'opening_balance': 7}).status_code == 200
    cl = client.login(w.admin)

    today = datetime.utcnow().date().isoformat()
    r = cl.get('/api/kassa/sessions', params={'branch_id': w.a1.id, 'date_from': today, 'date_to': today})
    assert r.status_code == 200, r.text
    j = r.json()
    assert [x['wallet_id'] for x in j['items']] == [kassa_day.k.id] and j['total'] == 1
    row = j['items'][0]
    assert row['branch_id'] == w.a1.id and row['status'] == 'closed' and row['wallet_name'] == "Kunlik kassa"
    assert row['difference_summary'] == {'cash': {'UZS': 10000.0}}
    assert j['totals']['difference'] == {'cash': {'UZS': 10000.0}}
    # butun korxona: ikkala filial, begona korxona yo'q
    r = cl.get('/api/kassa/sessions')
    assert {x['wallet_id'] for x in r.json()['items']} == {kassa_day.k.id, k2.id}
    assert r.json()['totals']['difference'] == {'cash': {'UZS': 10000.0}}
    # begona korxona filialini so'rash -> rad
    assert cl.get('/api/kassa/sessions', params={'branch_id': w.bb.id}).status_code == 400
    # begona korxona admini faqat o'zinikini ko'radi
    assert [x['wallet_id'] for x in client.login(w.admin_b).get('/api/kassa/sessions').json()['items']] == [kb.id]
    cl = client.login(w.admin)
    # kassir uchun ruxsat yo'q
    assert client.login(w.cash1).get('/api/kassa/sessions').status_code == 403
    # eski yo'l /{wallet_id}/sessions ishlayveradi va yangi maydonlarni beradi
    old = client.login(w.admin).get(f'/api/kassa/{kassa_day.k.id}/sessions').json()
    assert old[0]['difference_summary'] == {'cash': {'UZS': 10000.0}} and old[0]['branch_id'] == w.a1.id


# ── 9. Migratsiya va frontend ────────────────────────────────────────────────

def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


def test_migration_file_is_additive():
    src = _read('alembic', 'versions', 't1_11_shift_close_fields.py')
    assert "revision = 't1_11'" in src and "down_revision = 't1_10'" in src
    for frag in ("shifts ADD COLUMN IF NOT EXISTS wallet_id", "shifts ADD COLUMN IF NOT EXISTS closed_by",
                 "note_open", "note_close", "kassa_sessions ADD COLUMN IF NOT EXISTS branch_id",
                 "ix_kassa_sessions_company_branch_opened",
                 "companies ADD COLUMN IF NOT EXISTS pos_require_shift BOOLEAN NOT NULL DEFAULT FALSE"):
        assert frag in src, frag
    assert 'SET NOT NULL' not in src and 'DROP COLUMN' not in src.split('def downgrade')[0]


def test_models_match_migration_columns():
    cols = set(Shift.__table__.columns.keys())
    assert {'wallet_id', 'closed_by', 'note_open', 'note_close', 'expected_cash', 'cash_difference'} <= cols
    assert 'branch_id' in KassaSession.__table__.columns
    from app.models.company import Company
    assert Company.__table__.columns['pos_require_shift'].nullable is False


def test_frontend_shift_helpers_and_page():
    helper = _read('frontend', 'src', 'utils', 'shiftBalances.js')
    for fn in ('export function uzs', 'export function terminalUzs', 'export function foreignEntries'):
        assert fn in helper
    page = _read('frontend', 'src', 'pages', 'admin', 'Shifts.jsx')
    assert "Number(v)" not in page and "fmt(val)" not in page
    assert "/shifts/current" in page and "/shifts/${shiftId}/z-report" in page
    assert "setSelectedWallet(String(r.data[0].id))" not in page
    settings = _read('frontend', 'src', 'pages', 'admin', 'Settings.jsx')
    assert "pos_require_shift" in settings and "<ShiftsTab" in settings
    assert "require_shift" in _read('frontend', 'src', 'hooks', 'useCompanyFeatures.js')
