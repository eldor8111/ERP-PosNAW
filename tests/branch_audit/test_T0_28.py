"""T0.28 — smena yopilishidagi ikkilangan daromad yozuvi.

Inkassatsiya `income` Transaction emas, kassalararo ichki harakat:
manba kassa kamayadi, qabul qiluvchi oshadi, `transactions` ga yozuv qo'shilmaydi.
Hisobotlar (cash-balance, payments/income, dashboard, pnl-compare) eski
`reference_type='shift'` yozuvlarini sanamaydi.
"""
import importlib.util
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.audit_log import AuditLog
from app.models.moliya import CashTransfer, KassaMovement, Transaction, Wallet
from app.models.sale import PaymentType, Sale, SalePayment
from app.models.shift import Shift
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
WALLET_404 = "Kassa (hamyon) topilmadi"


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, balance=0, is_active=True, name=None):
    w = Wallet(name=name or f"Kassa {company.id}-{db.query(Wallet).count()}", type="cash",
               balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=is_active, is_open=True)
    db.add(w)
    db.flush()
    return w


def _bind(db, user, wallet):
    """Kassirning default kassasi (user_wallets)."""
    db.execute(text("INSERT INTO user_wallets(user_id, wallet_id, is_default, company_id) "
                    "VALUES (:u, :w, 1, :c)"), {"u": user.id, "w": wallet.id, "c": wallet.company_id})


def _shift(db, user, company, branch, opening=0):
    s = Shift(cashier_id=user.id, branch_id=branch.id, company_id=company.id, status="open",
              opened_at=datetime.now(timezone.utc), opening_cash=Decimal(opening))
    db.add(s)
    db.flush()
    return s


_n = [0]


def _sell(db, user, company, shift, wallet, payments, branch=None):
    """Sotuv: SalePayment + KassaMovement(in) + Wallet.balance + Transaction(income, sale).

    payments: [(tur, summa)]. `debt`/`cashback` uchun KassaMovement yozilmaydi (sale_create kabi).
    """
    _n[0] += 1
    total = sum(Decimal(a) for _, a in payments)
    s = Sale(number=f"S28-{_n[0]}", cashier_id=user.id, total_amount=total, paid_amount=total,
             paid_cash=sum(Decimal(a) for t, a in payments if t == "cash"),
             payment_type=PaymentType.cash if len(payments) == 1 and payments[0][0] == "cash" else PaymentType.mixed,
             company_id=company.id, shift_id=shift.id)
    db.add(s)
    db.flush()
    for ptype, amt in payments:
        amt = Decimal(amt)
        db.add(SalePayment(sale_id=s.id, payment_type=ptype, amount=amt))
        if ptype in ("debt", "cashback"):
            continue
        db.add(KassaMovement(wallet_id=wallet.id, company_id=company.id, direction="in",
                             payment_type=ptype, amount=amt, currency="UZS",
                             reference_type="sale", reference_id=s.id, created_by=user.id))
        wallet.balance = Decimal(str(wallet.balance or 0)) + amt
        db.add(Transaction(company_id=company.id, branch_id=branch.id if branch else None,
                           type="income", amount=amt, payment_type=ptype, wallet_id=wallet.id,
                           reference_type="sale", reference_id=s.id, description="Sotuv"))
    db.flush()
    return s


def _bal(db, w):
    db.refresh(w)
    return Decimal(str(w.balance))


def _net(db, wallet_id, ptype="cash"):
    ins = db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet_id,
                                         KassaMovement.payment_type == ptype).all()
    return sum((Decimal(str(m.amount)) if m.direction == "in" else -Decimal(str(m.amount))) for m in ins)


@pytest.fixture
def world(db, mk):
    """Bitta korxona: filial, kassir, kassir kassasi (src), asosiy kassa (main); ikkinchi korxona kassasi."""
    c, b, wh, admin = mk.tenant(role=UserRole.admin)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    src = _wallet(db, c, b, name="Kassir kassasi")
    main = _wallet(db, c, b, name="Asosiy kassa")
    _bind(db, cashier, src)
    shift = _shift(db, cashier, c, b, opening=50000)
    c2, b2, _, u2 = mk.tenant()
    foreign = _wallet(db, c2, b2, name="Begona")
    return dict(c=c, b=b, admin=admin, cashier=cashier, src=src, main=main, shift=shift,
                c2=c2, foreign=foreign, u2=u2)


def _close(client, w, **body):
    return client.login(w['cashier']).post(f"/api/shifts/{w['shift'].id}/close", json=body)


# ─── 1. Kassir kassasi bilan bir xil kassa ───────────────────────────────────

def test_same_wallet_no_money_movement_and_warning(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 3000000)], w['b'])
    tx_before = db.query(Transaction).count()
    bal = _bal(db, w['src'])
    r = _close(client, w, wallet_id=w['src'].id)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['status'] == "closed" and j['warnings'] and j['handover'] == []
    assert _bal(db, w['src']) == bal
    assert db.query(Transaction).count() == tx_before
    assert db.query(Transaction).filter(Transaction.reference_type == "shift").count() == 0
    assert db.query(CashTransfer).count() == 0


# ─── 2. Boshqa kassa: manba −X, qabul qiluvchi +X ────────────────────────────

def test_other_wallet_internal_transfer(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 3000000)], w['b'])
    tx_before = db.query(Transaction).count()
    total_before = _bal(db, w['src']) + _bal(db, w['main'])
    r = _close(client, w, wallet_id=w['main'].id)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['handover'] == [{"wallet_id": w['main'].id, "payment_type": "cash",
                              "currency": "UZS", "amount": 3000000.0}] or \
        (len(j['handover']) == 1 and float(j['handover'][0]['amount']) == 3000000.0)
    assert _bal(db, w['src']) == Decimal(0)
    assert _bal(db, w['main']) == Decimal(3000000)
    assert _bal(db, w['src']) + _bal(db, w['main']) == total_before
    mvs = {m.reference_type: m for m in db.query(KassaMovement).filter(
        KassaMovement.reference_type.in_(["transfer_out", "transfer_in"])).all()}
    assert mvs['transfer_out'].wallet_id == w['src'].id and mvs['transfer_out'].direction == "out"
    assert mvs['transfer_in'].wallet_id == w['main'].id and mvs['transfer_in'].direction == "in"
    ct = db.query(CashTransfer).one()
    assert ct.status == "completed" and ct.note == f"Smena #{w['shift'].id} inkassatsiyasi"
    assert mvs['transfer_out'].reference_id == ct.id == mvs['transfer_in'].reference_id
    assert db.query(Transaction).count() == tx_before          # income yozilmadi
    s = db.get(Shift, w['shift'].id)
    assert s.handover_wallet_id == w['main'].id and Decimal(str(s.handover_cash_amount)) == Decimal(3000000)


# ─── 3. Karta kassasi: debt/cashback ko'chirilmaydi ──────────────────────────

def test_card_handover_skips_debt_and_cashback(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'],
          [("cash", 100000), ("click", 200000), ("debt", 300000), ("cashback", 50000)], w['b'])
    r = _close(client, w, wallet_card_id=w['main'].id)
    assert r.status_code == 200, r.text
    j = r.json()
    assert [h['payment_type'] for h in j['handover']] == ["click"]
    assert j['warnings'] == []
    assert _bal(db, w['main']) == Decimal(200000)
    assert _bal(db, w['src']) == Decimal(100000)               # naqd joyida qoldi
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == "transfer_in",
                                          KassaMovement.payment_type.in_(["debt", "cashback"])).count() == 0
    assert db.query(Transaction).filter(Transaction.reference_type == "shift").count() == 0


# ─── 4-5. Hisobotlar 'shift' income ni sanamaydi ─────────────────────────────

def _legacy_shift_income(db, w, amount=3000000):
    db.add(Transaction(company_id=w['c'].id, branch_id=w['b'].id, type="income", amount=Decimal(amount),
                       payment_type="cash", wallet_id=w['main'].id, reference_type="shift",
                       reference_id=w['shift'].id, description="eski inkassatsiya"))
    db.flush()


def test_reports_exclude_legacy_shift_income(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 3000000)], w['b'])
    _legacy_shift_income(db, w)
    cl = client.login(w['admin'])

    r = cl.get('/api/finance/cash-balance')
    assert r.status_code == 200, r.text
    assert r.json()['total_income'] == 3000000.0

    r = cl.get('/api/finance/payments/income')
    assert r.status_code == 200, r.text
    assert r.json()['summary']['umumiy'] == 3000000.0
    assert all(i['reference_type'] != "shift" for i in r.json()['items'])

    r = cl.get('/api/dashboard/summary')
    assert r.status_code == 200, r.text
    assert r.json()['cash_balance'] == 3000000.0
    # T2.2: "boshqa daromad" faqat reference_type other_income/delivery_fee (qo'lda kirim)
    # pnl-compare: 'shift' boshqa daromadga kirmaydi, haqiqiy qo'lda kirim esa kiradi
    db.add(Transaction(company_id=w['c'].id, branch_id=w['b'].id, type="income", amount=Decimal(1000),
                       payment_type="cash", reference_type="other_income"))
    db.flush()
    r = cl.get('/api/reports/pnl-compare', params={'p1_from': '2020-01-01', 'p1_to': '2099-12-31',
                                                    'p2_from': '2020-01-01', 'p2_to': '2099-12-31'})
    assert r.status_code == 200, r.text
    assert r.json()['rows']['other_income']['p1'] == 1000.0


def test_other_income_still_counts_real_income(client, db, world):
    """Qora ro'yxat: 'shift' dan boshqa kirimlar (masalan manual) yo'qolmaydi."""
    w = world
    db.add(Transaction(company_id=w['c'].id, branch_id=w['b'].id, type="income", amount=Decimal(1000),
                       payment_type="cash", reference_type="manual"))
    db.add(Transaction(company_id=w['c'].id, branch_id=w['b'].id, type="income", amount=Decimal(2000),
                       payment_type="cash"))
    _legacy_shift_income(db, w, 500)
    db.flush()
    r = client.login(w['admin']).get('/api/finance/cash-balance')
    assert r.json()['total_income'] == 3000.0


def test_tx_not_internal_constants():
    from app.utils.report_utils import INTERNAL_TX_REFS, OTHER_INCOME_EXCLUDED_REFS
    assert INTERNAL_TX_REFS == ("shift",)
    assert set(OTHER_INCOME_EXCLUDED_REFS) == {"sale", "sale_payment", "customer_debt_payment",
                                               "customer_payment", "shift"}


# ─── 6. Begona / nofaol kassa → 404, smena ochiq ─────────────────────────────

def test_foreign_wallet_404_shift_stays_open(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 1000)], w['b'])
    r = _close(client, w, wallet_id=w['foreign'].id)
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    assert db.get(Shift, w['shift'].id).status == "open"
    assert _bal(db, w['foreign']) == Decimal(0)
    inactive = _wallet(db, w['c'], w['b'], is_active=False, name="Nofaol")
    r = _close(client, w, wallet_id=inactive.id)
    assert r.status_code == 404
    assert db.get(Shift, w['shift'].id).status == "open"


def test_branch_mismatch_400(client, db, world, mk):
    w = world
    other_branch = mk.branch(w['c'])
    far = _wallet(db, w['c'], other_branch, name="Boshqa filial kassasi")
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 1000)], w['b'])
    r = _close(client, w, wallet_id=far.id)
    assert r.status_code == 400, r.text
    assert db.get(Shift, w['shift'].id).status == "open"
    assert _bal(db, w['src']) == Decimal(1000)
    # filialsiz markaziy kassa ruxsat etiladi
    central = _wallet(db, w['c'], None, name="Markaziy")
    r = _close(client, w, wallet_id=central.id)
    assert r.status_code == 200, r.text
    assert _bal(db, central) == Decimal(1000)


# ─── 7. Ikki yopish: bittasi 200, ikkinchisi 400 ─────────────────────────────

def test_double_close_second_400_money_moves_once(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 5000)], w['b'])
    r1 = _close(client, w, wallet_id=w['main'].id)
    r2 = _close(client, w, wallet_id=w['main'].id)
    assert r1.status_code == 200 and r2.status_code == 400, (r1.text, r2.text)
    assert _bal(db, w['main']) == Decimal(5000)
    assert db.query(CashTransfer).count() == 1
    # /shifts/close (id siz) — faol smena yo'q
    r3 = client.login(w['cashier']).post('/api/shifts/close', json={"wallet_id": w['main'].id})
    assert r3.status_code in (400, 404)
    assert _bal(db, w['main']) == Decimal(5000)


# ─── 8. Qoldiq yetmasa miqdor cheklanadi ─────────────────────────────────────

def test_amount_capped_by_actual_net_no_negative(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 1000)], w['b'])
    # close_kassa kabi alohida inkasso 700 ni allaqachon olib ketgan
    db.add(KassaMovement(wallet_id=w['src'].id, company_id=w['c'].id, direction="out",
                         payment_type="cash", amount=Decimal(700), currency="UZS",
                         reference_type="withdraw", created_by=w['cashier'].id))
    w['src'].balance = Decimal(300)
    db.flush()
    r = _close(client, w, wallet_id=w['main'].id)
    assert r.status_code == 200, r.text
    j = r.json()
    assert float(j['handover'][0]['amount']) == 300.0 and j['warnings']
    assert _bal(db, w['src']) == Decimal(0) and _bal(db, w['main']) == Decimal(300)
    assert _net(db, w['src'].id) == Decimal(0)


def test_nothing_left_no_transfer(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 1000)], w['b'])
    db.add(KassaMovement(wallet_id=w['src'].id, company_id=w['c'].id, direction="out",
                         payment_type="cash", amount=Decimal(1000), currency="UZS",
                         reference_type="withdraw", created_by=w['cashier'].id))
    w['src'].balance = Decimal(0)
    db.flush()
    r = _close(client, w, wallet_id=w['main'].id)
    assert r.status_code == 200 and r.json()['handover'] == [] and r.json()['warnings']
    assert db.query(CashTransfer).count() == 0 and _bal(db, w['src']) == Decimal(0)


# ─── 9. Kassa farqi ──────────────────────────────────────────────────────────

def test_cash_difference_saved_and_audited(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 200000)], w['b'])
    expected = 50000 + 200000
    r = _close(client, w, closing_cash=expected - 10000)
    assert r.status_code == 200, r.text
    j = r.json()
    assert float(j['expected_cash']) == expected and float(j['cash_difference']) == -10000.0
    s = db.get(Shift, w['shift'].id)
    assert Decimal(str(s.expected_cash)) == Decimal(expected)
    assert Decimal(str(s.closing_cash)) == Decimal(expected - 10000)
    assert Decimal(str(s.cash_difference)) == Decimal(-10000)
    log = db.query(AuditLog).filter(AuditLog.action == "SHIFT_CASH_DIFF").one()
    assert log.entity_id == s.id


def test_closing_cash_defaults_to_expected_no_audit(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 200000)], w['b'])
    r = _close(client, w)
    assert r.status_code == 200, r.text
    s = db.get(Shift, w['shift'].id)
    assert Decimal(str(s.closing_cash)) == Decimal(250000) == Decimal(str(s.expected_cash))
    assert Decimal(str(s.cash_difference)) == 0
    assert db.query(AuditLog).filter(AuditLog.action == "SHIFT_CASH_DIFF").count() == 0
    assert s.handover_wallet_id is None


# ─── GET /shifts/current va /shifts ──────────────────────────────────────────

def test_current_shift_handover_wallets(client, db, world, mk):
    w = world
    other_branch = mk.branch(w['c'])
    _wallet(db, w['c'], w['b'], is_active=False, name="Nofaol")
    far = _wallet(db, w['c'], other_branch, name="Uzoq")
    central = _wallet(db, w['c'], None, name="Markaziy")
    r = client.login(w['cashier']).get('/api/shifts/current')
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['cashier_wallet_id'] == w['src'].id
    ids = {x['id'] for x in j['handover_wallets']}
    assert ids == {w['main'].id, central.id}
    assert w['src'].id not in ids and w['foreign'].id not in ids and far.id not in ids


def test_list_shifts_has_expected_and_difference(client, db, world):
    w = world
    _sell(db, w['cashier'], w['c'], w['shift'], w['src'], [("cash", 1000)], w['b'])
    assert _close(client, w, closing_cash=50000).status_code == 200
    r = client.login(w['admin']).get('/api/shifts')
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x['id'] == w['shift'].id)
    assert float(row['expected_cash']) == 51000.0 and float(row['cash_difference']) == -1000.0


# ─── Yordamchilar: resolve_cashier_wallet_id, kassa_net ──────────────────────

def test_resolve_cashier_wallet_id(db, mk):
    from app.services.sale_helpers import resolve_cashier_wallet_id
    c, b, _, _ = mk.tenant()
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    assert resolve_cashier_wallet_id(db, cashier) is None
    w1 = _wallet(db, c, b)
    w2 = _wallet(db, c, b)
    assert resolve_cashier_wallet_id(db, cashier) == w1.id          # zaxira: birinchi ochiq faol
    _bind(db, cashier, w2)
    assert resolve_cashier_wallet_id(db, cashier) == w2.id          # user_wallets default
    w2.is_active = False
    db.flush()
    assert resolve_cashier_wallet_id(db, cashier) == w1.id          # nofaol e'tiborga olinmaydi


def test_transfer_helper_and_kassa_net(db, mk):
    from app.services.cash_handover import kassa_net, transfer_between_wallets
    c, b, _, admin = mk.tenant()
    a = _wallet(db, c, b, balance=1000)
    z = _wallet(db, c, b, balance=0)
    db.add(KassaMovement(wallet_id=a.id, company_id=c.id, direction="in", payment_type="cash",
                         amount=Decimal(1000), currency="UZS", reference_type="sale"))
    db.flush()
    assert kassa_net(db, a.id, "cash", "UZS") == Decimal(1000)
    ct = transfer_between_wallets(db, company_id=c.id, source=a, target=z, amount=400, currency="UZS",
                                  payment_type="cash", user=admin, note="test", ref="x")
    assert ct.status == "completed"
    assert kassa_net(db, a.id, "cash", "UZS") == Decimal(600)
    assert kassa_net(db, z.id, "cash", "UZS") == Decimal(400)
    assert Decimal(str(a.balance)) == Decimal(600) and Decimal(str(z.balance)) == Decimal(400)
    assert db.query(Transaction).count() == 0
    # USD: balans o'zgarmaydi, harakatlar yoziladi
    transfer_between_wallets(db, company_id=c.id, source=a, target=z, amount=5, currency="USD",
                             payment_type="cash", user=admin)
    assert Decimal(str(a.balance)) == Decimal(600)
    assert kassa_net(db, z.id, "cash", "USD") == Decimal(5)
    assert transfer_between_wallets(db, company_id=c.id, source=a, target=z, amount=0, user=admin) is None


# ─── Migratsiya, model, frontend ─────────────────────────────────────────────

def test_migration_and_model_columns():
    path = os.path.join(ROOT, 'alembic', 'versions', 't028_shift_handover_columns.py')
    spec = importlib.util.spec_from_file_location('t028', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == 't028' and mod.down_revision == 't0_26'
    src = open(path, encoding='utf-8').read()
    for col in ("expected_cash", "cash_difference", "handover_cash_amount",
                "handover_wallet_id", "handover_card_wallet_id"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in src
        assert hasattr(Shift, col)


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding='utf-8').read()


def test_frontend_shifts_no_autoselect_no_nan_and_i18n():
    # smena yopish oynasi alohida komponentga ajratilgan — ikkala faylni birga tekshiramiz
    jsx = (_read('frontend', 'src', 'pages', 'admin', 'Shifts.jsx')
           + _read('frontend', 'src', 'components', 'ShiftCloseModal.jsx'))
    assert "setSelectedWallet(String(r.data[0].id))" not in jsx
    assert "handover_wallets" in jsx
    assert "fmt(val)" not in jsx and "Number(v)" not in jsx
    assert ".UZS" in jsx
    for lang in ('uz', 'ru', 'en'):
        src = _read('frontend', 'src', 'i18n', f'{lang}.js')
        for key in ('shift.cashDifference', 'shift.handoverSameWallet', 'shift.handoverCapped'):
            assert f"'{key}'" in src, (lang, key)


def test_no_shift_income_transaction_in_router():
    src = _read('app', 'routers', 'shifts.py')
    assert 'reference_type="shift"' not in src
    assert "WalletBalance" not in src
