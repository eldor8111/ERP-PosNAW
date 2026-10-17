"""T2.6 — mijoz va ta'minotchi qarzlari filial kesimida.

Qamrov: `customer_debt_log` jurnali va `customer_ledger` servisi (add_debt, set_balances, pay_debt, reverse_payment,
write_off, reconcile, debt_by_branch); FIFO to'g'ri birlikda (UZS/USD sotuv); ikki to'lov endpointi bir xil natija
beradi (qarz, Sale.paid_amount, Transaction.currency_code, KassaMovement.currency); kassa/summa/rol tekshiruvlari;
to'lovni o'chirish qarzni aynan qaytaradi (meta bor va yo'q); tranzaksiya tahririda summa o'zgarmaydi;
filial hisobotlari (`/reports/customer-debts`, `/reports/debt-collections`, `/finance/customer-debts`,
supplier `debt_by_branch`); `/customers/{id}/payments`; AI vositalari; agent ilovasi; migratsiya sintaksisi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T2_6.py -q -p no:cacheprovider
"""
import itertools
import os
import py_compile
from decimal import Decimal

import pytest
from sqlalchemy import func

from app.models.currency import Currency
from app.models.customer import Customer
from app.models.customer_debt_log import CustomerDebtLog as Log
from app.models.moliya import KassaMovement, Transaction, Wallet
from app.models.purchase_order import POStatus, PurchaseOrder
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services import customer_ledger as cl
from app.services import supplier_ledger as sl

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
D = Decimal


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _cur(db, company, code="USD", rate=12700):
    c = Currency(name=code, code=code, rate=rate, company_id=company.id, is_active=True)
    db.add(c)
    db.flush()
    return c


def _wallet(db, company, branch, balance=0, **kw):
    w = Wallet(name=f"Kassa {next(_seq)}", company_id=company.id, branch_id=branch.id if branch else None,
               balance=D(balance), is_active=True, is_open=True, **kw)
    db.add(w)
    db.flush()
    return w


def _customer(db, company, branch, balances=None, name=None):
    """Mijoz + `opening` jurnali (migratsiya/yaratish kabi)."""
    c = Customer(name=name or f"Mijoz {next(_seq)}", phone=f"9988{next(_seq):07d}", company_id=company.id,
                 branch_id=branch.id if branch else None)
    db.add(c)
    db.flush()
    if balances:
        cl._save(db, c, {k: D(str(v)) for k, v in balances.items()})
        cl.log_opening(db, c)
        db.flush()
    return c


def _sale(db, company, customer, wh, branch, user, total, *, paid=0, rate=1, created=None):
    s = Sale(number=f"S{next(_seq):06d}", cashier_id=user.id, total_amount=D(str(total)), paid_amount=D(str(paid)),
             payment_type=PaymentType.debt, status=SaleStatus.completed, company_id=company.id,
             warehouse_id=wh.id, branch_id=branch.id, customer_id=customer.id, exchange_rate=D(str(rate)))
    if created is not None:
        s.created_at = created
    db.add(s)
    db.flush()
    return s


def _credit(db, customer, user, *, currency, amount, sale=None, kind="sale"):
    """Sotuvdagi qarzni ledger orqali qo'shish (sale_create ledger'ga o'tgandagi kabi)."""
    row = cl.add_debt(db, customer, currency=currency, amount=amount, kind=kind, user=user, sale=sale)
    db.flush()
    return row


def _bal(c):
    return {k: float(v) for k, v in cl.balances(c).items()}


def _journal_sum(db, customer_id, currency):
    return float(db.query(func.coalesce(func.sum(Log.delta), 0)).filter(
        Log.customer_id == customer_id, Log.currency == currency).scalar() or 0)


@pytest.fixture
def world(db, mk):
    """Bitta korxona: Chilonzor + Yunusobod filiallari, har birida ombor, kassa va kassir; admin; USD kursi."""
    c = mk.company()
    chil = mk.branch(c, name="Chilonzor")
    yun = mk.branch(c, name="Yunusobod")
    w_chil = mk.warehouse(c, chil)
    w_yun = mk.warehouse(c, yun)
    admin = mk.user(c, role=UserRole.admin)
    cash_chil = mk.user(c, role=UserRole.cashier, branch=chil)
    cash_yun = mk.user(c, role=UserRole.cashier, branch=yun)
    k_chil = _wallet(db, c, chil)
    k_yun = _wallet(db, c, yun)
    _cur(db, c, "USD", 12700)
    return type("W", (), dict(
        c=c, chil=chil, yun=yun, w_chil=w_chil, w_yun=w_yun, admin=admin, cash_chil=cash_chil,
        cash_yun=cash_yun, k_chil=k_chil, k_yun=k_yun,
    ))


# ── Model va migratsiya ──────────────────────────────────────────────────────

def test_model_registered_and_migration_compiles():
    from app.database import Base
    import app.models  # noqa: F401
    assert "customer_debt_log" in Base.metadata.tables
    cols = Base.metadata.tables["customer_debt_log"].c
    for name in ("company_id", "customer_id", "branch_id", "cash_branch_id", "user_id", "kind", "currency",
                 "delta", "delta_uzs", "rate", "sale_id", "transaction_id", "reason", "created_at"):
        assert name in cols
    py_compile.compile(os.path.join(ROOT, "alembic", "versions", "t2_6_customer_debt_log.py"), doraise=True)
    src = open(os.path.join(ROOT, "alembic", "versions", "t2_6_customer_debt_log.py"), encoding="utf-8").read()
    assert "down_revision = 't2_2'" in src and "revision = 't2_6'" in src and "CREATE TABLE IF NOT EXISTS" in src


# ── add_debt / set_balances / invariant ──────────────────────────────────────

def test_add_debt_logs_branch_user_and_never_zero_branch(db, world):
    w = world
    cust = _customer(db, w.c, w.chil)
    sale = _sale(db, w.c, cust, w.w_yun, w.yun, w.admin, 500000)
    row = cl.add_debt(db, cust, currency="UZS", amount=500000, kind="sale", user=w.admin, sale=sale)
    assert row.branch_id == w.yun.id          # sotuv filiali mijoz filialidan ustun
    assert row.sale_id == sale.id and row.user_id == w.admin.id and row.kind == "sale"
    row2 = cl.add_debt(db, cust, currency="UZS", amount=1000, kind="ai", user=w.admin, reason="AI")
    assert row2.branch_id == w.chil.id         # sotuvsiz -> mijoz filiali
    assert all((r.branch_id or 1) != 0 for r in db.query(Log).all())
    assert _bal(cust) == {"UZS": 501000.0}
    assert float(cust.debt_balance) == 501000.0
    # kamaytirish balansdan ko'p bo'lsa nolga tushadi, jurnalga HAQIQIY o'zgarish yoziladi
    cl.add_debt(db, cust, currency="UZS", amount=-999999999, kind="edit", user=w.admin)
    assert _bal(cust) == {}
    assert _journal_sum(db, cust.id, "UZS") == pytest.approx(0, abs=0.01)


def test_set_balances_writes_edit_rows(db, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 1000000, "USD": 50})
    rows = cl.set_balances(db, cust, {"UZS": 700000, "USD": 50}, user=w.admin, reason="Tuzatish")
    assert len(rows) == 1 and rows[0].kind == "edit" and float(rows[0].delta) == -300000
    assert rows[0].user_id == w.admin.id and rows[0].branch_id == w.chil.id and rows[0].reason == "Tuzatish"
    assert _bal(cust) == {"UZS": 700000.0, "USD": 50.0}
    # debt_balance — joriy kurs bo'yicha UZS ekvivalenti
    assert float(cust.debt_balance) == pytest.approx(700000 + 50 * 12700)
    with pytest.raises(Exception):
        cl.set_balances(db, cust, {"UZS": -5}, user=w.admin)


# ── FIFO: to'g'ri birlik ─────────────────────────────────────────────────────

def test_fifo_units_usd_sale(db, world):
    w = world
    # 100 USD sotuv: total_amount UZS da (1 270 000), paid_amount sotuv valyutasida (USD)
    cust = _customer(db, w.c, w.chil)
    sale = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1270000, paid=0, rate=12700)
    _credit(db, cust, w.admin, currency="USD", amount=100, sale=sale)
    res = cl.allocate_fifo(db, cust, D("635000"))          # 50 USD ekvivalenti
    assert res == [(sale.id, D("635000"))]
    assert float(sale.paid_amount) == pytest.approx(50.0)  # USD birligida (eski xato: 50 * 12700 / 12700 emas, 635000/...)
    cl.allocate_fifo(db, cust, D("635000"))
    assert float(sale.paid_amount) == pytest.approx(100.0)
    assert cl.allocate_fifo(db, cust, D("1000")) == []     # sotuv to'liq yopilgan


def test_fifo_oldest_first_and_skips_returns_and_pending(db, world):
    from datetime import datetime, timedelta
    w = world
    cust = _customer(db, w.c, w.chil)
    now = datetime.utcnow()
    old = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1000, created=now - timedelta(days=3))
    new = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1000, created=now - timedelta(days=1))
    pend = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1000, created=now - timedelta(days=5))
    pend.status = SaleStatus.pending
    ret = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1000, created=now - timedelta(days=6))
    ret.number = "R000001"
    db.flush()
    res = cl.allocate_fifo(db, cust, D("1500"))
    assert [(sid, float(u)) for sid, u in res] == [(old.id, 1000.0), (new.id, 500.0)]
    assert float(pend.paid_amount) == 0 and float(ret.paid_amount) == 0


# ── pay_debt: yagona servis ──────────────────────────────────────────────────

def test_pay_debt_uzs_full(db, world):
    w = world
    cust = _customer(db, w.c, w.chil)
    sale = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1000000)
    _credit(db, cust, w.admin, currency="UZS", amount=1000000, sale=sale)
    res = cl.pay_debt(db, cust, user=w.cash_chil, payments=[{"amount": 1000000, "currency": "UZS"}],
                      wallet_id=w.k_chil.id, reason="Naqd")
    assert res["remaining_debt"] == 0 and _bal(cust) == {}
    assert float(sale.paid_amount) == 1000000
    tx = db.get(Transaction, res["transaction_ids"][0])
    assert tx.reference_type == "customer_payment" and tx.reference_id == cust.id
    assert tx.currency_code == "UZS" and tx.branch_id == w.chil.id and tx.user_id == w.cash_chil.id
    assert tx.meta["allocation"]["buckets"] == {"UZS": "1000000.0"} or float(tx.meta["allocation"]["buckets"]["UZS"]) == 1000000
    assert str(sale.id) in tx.meta["allocation"]["sales"]
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "customer_payment").one()
    assert mv.currency == "UZS" and float(mv.amount) == 1000000 and mv.wallet_id == w.k_chil.id
    assert float(db.get(Wallet, w.k_chil.id).balance) == 1000000
    rows = db.query(Log).filter(Log.kind == "payment").all()
    assert len(rows) == 1 and rows[0].transaction_id == tx.id and rows[0].cash_branch_id == w.chil.id
    assert rows[0].branch_id == w.chil.id and float(rows[0].delta) == -1000000
    assert cl.reconcile(db, w.c.id) == []


def test_pay_debt_partial_and_usd_cascade(db, world):
    w = world
    cust = _customer(db, w.c, w.chil)
    s_uzs = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 2000000)
    s_usd = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1270000, rate=12700)
    _credit(db, cust, w.admin, currency="UZS", amount=2000000, sale=s_uzs)
    _credit(db, cust, w.admin, currency="USD", amount=100, sale=s_usd)
    # 30 USD to'lov: avval USD chelagi
    r = cl.pay_debt(db, cust, user=w.admin, payments=[{"amount": 30, "currency": "USD"}], wallet_id=w.k_chil.id)
    assert _bal(cust) == {"UZS": 2000000.0, "USD": 70.0}
    tx = db.get(Transaction, r["transaction_ids"][0])
    assert tx.currency_code == "USD" and float(tx.amount) == 30
    mv = db.query(KassaMovement).filter(KassaMovement.reference_id == cust.id).one()
    assert mv.currency == "USD"
    assert float(db.get(Wallet, w.k_chil.id).balance) == 0        # valyutali pul hamyon (UZS) keshiga tegmaydi
    # FIFO: eng eski sotuv (UZS) 30*12700 = 381000 oldi, USD sotuv tegilmadi
    assert float(s_uzs.paid_amount) == pytest.approx(381000)
    assert float(s_usd.paid_amount) == 0
    # 100 USD to'lov: 70 USD o'z chelagi + 30 USD*12700 = 381000 UZS chelagidan
    cl.pay_debt(db, cust, user=w.admin, payments=[{"amount": 100, "currency": "USD"}], wallet_id=w.k_chil.id)
    assert _bal(cust)["UZS"] == pytest.approx(2000000 - 381000)
    assert "USD" not in _bal(cust)
    assert cl.reconcile(db, w.c.id) == []


def test_pay_debt_validations_do_not_change_debt(db, world):
    from fastapi import HTTPException
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000})
    before = dict(cust.debt_balances)

    def pay(amount, wallet=w.k_chil.id, user=w.admin, **kw):
        return cl.pay_debt(db, cust, user=user, payments=[{"amount": amount, "currency": "UZS", **kw}], wallet_id=wallet)

    with pytest.raises(HTTPException) as e:
        pay(0)
    assert e.value.status_code == 400 and e.value.detail == "To'lov miqdori musbat bo'lishi kerak"
    with pytest.raises(HTTPException) as e:
        pay(-5)
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        pay(100005)
    assert e.value.status_code == 400 and e.value.detail == "To'lov qarzdan ko'p"
    with pytest.raises(HTTPException) as e:
        pay(1000, payment_type="debt")
    assert e.value.status_code == 400
    # kassa yo'q (wallet_id berilmagan, korxonada ochiq kassa yo'q) -> 400, qarz o'zgarmaydi
    for wl in (w.k_chil, w.k_yun):
        wl.is_open = False
    db.flush()
    with pytest.raises(HTTPException) as e:
        pay(1000, wallet=None, user=w.admin)
    # korxonada >=2 filial: T1.10 qoidasi ("Bu filial uchun kassa sozlanmagan"), bitta filialda — "Ochiq kassa topilmadi"
    assert e.value.status_code == 400 and e.value.detail in ("Ochiq kassa topilmadi", "Bu filial uchun kassa sozlanmagan")
    assert cust.debt_balances == before
    assert db.query(Transaction).filter(Transaction.reference_type == "customer_payment").count() == 0


def test_pay_debt_no_wallet_single_branch_company(db, mk):
    from fastapi import HTTPException
    c, b, wh, u = mk.tenant()
    cust = _customer(db, c, b, {"UZS": 100000})
    with pytest.raises(HTTPException) as e:
        cl.pay_debt(db, cust, user=u, payments=[{"amount": 1000}])
    assert e.value.status_code == 400 and e.value.detail == "Ochiq kassa topilmadi"
    assert cust.debt_balances == {"UZS": 100000.0}
    assert db.query(Transaction).count() == 0 and db.query(Log).filter(Log.kind == "payment").count() == 0


def test_pay_debt_foreign_company_wallet_and_customer(db, mk, world):
    from fastapi import HTTPException
    w = world
    other_c, other_b, other_w, other_u = mk.tenant()
    foreign_wallet = _wallet(db, other_c, other_b)
    cust = _customer(db, w.c, w.chil, {"UZS": 50000})
    with pytest.raises(HTTPException) as e:
        cl.pay_debt(db, cust, user=w.admin, payments=[{"amount": 1000}], wallet_id=foreign_wallet.id)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        cl.pay_debt(db, cust, user=other_u, payments=[{"amount": 1000}], wallet_id=foreign_wallet.id)
    assert e.value.status_code == 404                       # begona korxona mijozi
    # kassir boshqa filial kassasidan foydalana olmaydi
    with pytest.raises(HTTPException) as e:
        cl.pay_debt(db, cust, user=w.cash_chil, payments=[{"amount": 1000}], wallet_id=w.k_yun.id)
    assert e.value.status_code == 403


# ── Ikki endpoint bir xil natija ─────────────────────────────────────────────

def _setup_usd_debtor(db, w):
    cust = _customer(db, w.c, w.chil)
    sale = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1270000, rate=12700)
    _credit(db, cust, w.admin, currency="USD", amount=100, sale=sale)
    return cust, sale


def test_two_pay_endpoints_give_same_result(db, client, world):
    w = world
    c1, s1 = _setup_usd_debtor(db, w)
    c2, s2 = _setup_usd_debtor(db, w)
    r1 = client.login(w.cash_chil).post(f"/api/customers/{c1.id}/pay-debt", json={
        "amount": 40, "currency": "USD", "payment_type": "cash", "reason": "USD to'lov", "wallet_id": w.k_chil.id})
    r2 = client.login(w.cash_chil).post(f"/api/finance/customer-debts/{c2.id}/pay", json={
        "amount": 40, "currency": "USD", "payment_type": "cash", "description": "USD to'lov", "wallet_id": w.k_chil.id})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    db.refresh(c1), db.refresh(c2), db.refresh(s1), db.refresh(s2)
    assert c1.debt_balances == c2.debt_balances == {"USD": 60.0}
    assert float(c1.debt_balance) == float(c2.debt_balance) == pytest.approx(60 * 12700)
    assert float(s1.paid_amount) == float(s2.paid_amount) == pytest.approx(40.0)
    for body in (r1.json(), r2.json()):
        assert body["transaction_ids"] and body["allocation"]
    t1, t2 = (db.get(Transaction, r.json()["transaction_ids"][0]) for r in (r1, r2))
    assert t1.currency_code == t2.currency_code == "USD"
    assert float(t1.amount) == float(t2.amount) == 40
    assert t1.meta["allocation"]["buckets"].keys() == t2.meta["allocation"]["buckets"].keys() == {"USD"}
    m1 = db.query(KassaMovement).filter(KassaMovement.reference_id == c1.id).one()
    m2 = db.query(KassaMovement).filter(KassaMovement.reference_id == c2.id).one()
    assert m1.currency == m2.currency == "USD"


def test_pay_endpoints_roles_and_amount(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000})
    wh_user = None
    from app.models.user import User  # noqa: F401
    store = type("M", (), {})
    # ombor xodimi -> 403 ikkala endpointda
    from tests.branch_audit.conftest import Maker
    wh_user = Maker(db).user(w.c, role=UserRole.warehouse, branch=w.chil)
    for url, body in (
        (f"/api/customers/{cust.id}/pay-debt", {"amount": 1000, "reason": "x", "wallet_id": w.k_chil.id}),
        (f"/api/finance/customer-debts/{cust.id}/pay", {"amount": 1000, "wallet_id": w.k_chil.id}),
    ):
        assert client.login(wh_user).post(url, json=body).status_code == 403
    # amount <= 0 va qarzdan ko'p
    r = client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt", json={"amount": 0, "reason": "x"})
    assert r.status_code == 400 and "musbat" in r.json()["detail"]
    r = client.login(w.admin).post(f"/api/finance/customer-debts/{cust.id}/pay", json={"amount": 0})
    assert r.status_code == 422
    r = client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt",
                                   json={"amount": 999999, "reason": "x", "wallet_id": w.k_chil.id})
    assert r.status_code == 400 and r.json()["detail"] == "To'lov qarzdan ko'p"
    r = client.login(w.admin).post(f"/api/finance/customer-debts/{cust.id}/pay",
                                   json={"amount": 999999, "wallet_id": w.k_chil.id})
    assert r.status_code == 400
    db.refresh(cust)
    assert cust.debt_balances == {"UZS": 100000.0}


def test_pay_debt_payments_array_is_atomic(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000})
    body = {"reason": "Aralash", "wallet_id": w.k_chil.id, "payments": [
        {"amount": 40000, "currency": "UZS", "payment_type": "cash"},
        {"amount": 30000, "currency": "UZS", "payment_type": "card"},
    ]}
    r = client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt", json=body)
    assert r.status_code == 200 and len(r.json()["transaction_ids"]) == 2
    db.refresh(cust)
    assert cust.debt_balances == {"UZS": 30000.0}
    # ikkinchi qator ortiqcha bo'lsa — hech biri saqlanmaydi
    bad = {"reason": "x", "wallet_id": w.k_chil.id, "payments": [
        {"amount": 20000, "currency": "UZS"}, {"amount": 20000, "currency": "UZS"}]}
    r = client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt", json=bad)
    assert r.status_code == 400
    db.refresh(cust)
    assert cust.debt_balances == {"UZS": 30000.0}
    assert db.query(Transaction).filter(Transaction.reference_type == "customer_payment").count() == 2


# ── To'lovni o'chirish / tahrirlash ──────────────────────────────────────────

def test_delete_usd_payment_restores_exactly(db, client, world):
    w = world
    cust, sale = _setup_usd_debtor(db, w)
    r = client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt", json={
        "amount": 100, "currency": "USD", "reason": "USD", "wallet_id": w.k_chil.id})
    assert r.status_code == 200, r.text
    db.refresh(cust), db.refresh(sale)
    assert cust.debt_balances == {} and float(sale.paid_amount) == pytest.approx(100.0)
    tx_id = r.json()["transaction_ids"][0]
    d = client.login(w.admin).delete(f"/api/finance/transactions/{tx_id}")
    assert d.status_code == 204, d.text
    db.refresh(cust), db.refresh(sale)
    assert cust.debt_balances == {"USD": 100.0}
    assert float(cust.debt_balance) == pytest.approx(100 * 12700)       # USD summa UZS deb qo'shilmaydi
    assert float(sale.paid_amount) == pytest.approx(0.0)
    assert db.query(Log).filter(Log.kind == "reversal", Log.transaction_id == tx_id).count() == 1
    assert cl.reconcile(db, w.c.id) == []
    # takroriy qaytarish hech narsa o'zgartirmaydi
    tx = db.get(Transaction, tx_id)
    assert cl.reverse_payment(db, tx) is False
    assert cust.debt_balances == {"USD": 100.0}


def test_reverse_legacy_payment_without_meta(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 500000})
    sale = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 500000, paid=0)
    tx = Transaction(company_id=w.c.id, branch_id=w.chil.id, wallet_id=w.k_chil.id, type="income",
                     amount=D("40"), currency_code="USD", payment_type="cash", reference_type="customer_payment",
                     reference_id=cust.id, user_id=w.admin.id, meta=None)
    db.add(tx)
    db.flush()
    r = client.login(w.admin).delete(f"/api/finance/transactions/{tx.id}")
    assert r.status_code == 204
    db.refresh(cust), db.refresh(sale)
    assert cust.debt_balances == {"UZS": 500000.0, "USD": 40.0}        # tx.currency_code chelagiga qaytdi
    assert float(sale.paid_amount) == 0                                # eski yozuvda Sale.paid_amount ga tegilmaydi


def test_update_customer_payment_tx_locks_amount_and_wallet(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000})
    r = client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt",
                                   json={"amount": 40000, "reason": "Birinchi", "wallet_id": w.k_chil.id})
    tx_id = r.json()["transaction_ids"][0]
    base = {"amount": 40000, "wallet_id": w.k_chil.id, "payment_type": "cash", "description": "Izoh"}
    bad = client.login(w.admin).put(f"/api/finance/transactions/{tx_id}", json={**base, "amount": 50000})
    assert bad.status_code == 400
    assert bad.json()["detail"] == "Mijoz to'lovining summasini o'zgartirib bo'lmaydi — o'chirib, qaytadan kiriting"
    bad2 = client.login(w.admin).put(f"/api/finance/transactions/{tx_id}", json={**base, "wallet_id": w.k_yun.id})
    assert bad2.status_code == 400
    ok = client.login(w.admin).put(f"/api/finance/transactions/{tx_id}",
                                   json={**base, "payment_type": "card", "description": "Yangi izoh"})
    assert ok.status_code == 200, ok.text
    tx = db.get(Transaction, tx_id)
    assert tx.payment_type == "card" and tx.description == "Yangi izoh" and float(tx.amount) == 40000
    mv = db.query(KassaMovement).filter(KassaMovement.reference_id == cust.id).one()
    assert mv.payment_type == "card" and mv.description == "Yangi izoh"
    db.refresh(cust)
    assert cust.debt_balances == {"UZS": 60000.0}


# ── Qo'lda tahrir, hisobdan chiqarish, reconcile ─────────────────────────────

def test_adjust_debt_logs_edit_with_user_and_branch(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 1000000})
    r = client.login(w.admin).post(f"/api/customers/{cust.id}/adjust-debt", json={
        "reason": "Kelishuv bo'yicha", "changes": [{"currency": "UZS", "delta": -500000}]})
    assert r.status_code == 200, r.text
    row = db.query(Log).filter(Log.kind == "edit").one()
    assert row.user_id == w.admin.id and row.branch_id == w.chil.id and float(row.delta) == -500000
    assert row.reason == "Kelishuv bo'yicha"
    db.refresh(cust)
    assert cust.debt_edited[-1]["user_id"] == w.admin.id
    # PUT orqali qarz o'zgarmaydi (T0.26) — jurnalga yangi qator tushmaydi
    n = db.query(Log).count()
    put = client.login(w.admin).put(f"/api/customers/{cust.id}", json={"name": cust.name, "debt_balances": {"UZS": 1}})
    assert put.status_code == 400
    assert db.query(Log).count() == n
    assert cl.reconcile(db, w.c.id) == []


def test_writeoff_admin_only_no_cash(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 200000})
    sale = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 200000)
    url = f"/api/customers/{cust.id}/debt-writeoff"
    assert client.login(w.cash_chil).post(url, json={"amount": 1000, "reason": "uzoq sabab"}).status_code == 403
    assert client.login(w.admin).post(url, json={"amount": 1000, "reason": "qisqa"[:3]}).status_code == 400
    assert client.login(w.admin).post(url, json={"amount": 999999, "reason": "juda katta summa"}).status_code == 400
    r = client.login(w.admin).post(url, json={"amount": 50000, "currency": "UZS", "reason": "Qaytarilmas qarz"})
    assert r.status_code == 200, r.text
    db.refresh(cust), db.refresh(sale)
    assert cust.debt_balances == {"UZS": 150000.0}
    assert float(sale.paid_amount) == 50000
    rows = db.query(Log).filter(Log.kind == "writeoff").all()
    assert len(rows) == 1 and float(rows[0].delta) == -50000 and rows[0].user_id == w.admin.id
    assert db.query(KassaMovement).count() == 0 and db.query(Transaction).count() == 0
    assert cl.reconcile(db, w.c.id) == []


def test_reconcile_invariant_dry_run_and_fix(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000})
    cust.debt_balances = {"UZS": 130000.0, "USD": 5.0}      # jurnalsiz to'g'ridan-to'g'ri yozuv (eski kod)
    db.flush()
    dry = client.login(w.admin).post("/api/customers/debt-log/reconcile?dry_run=true")
    assert dry.status_code == 200
    items = {(i["customer_id"], i["currency"]): i for i in dry.json()["items"]}
    assert items[(cust.id, "UZS")]["diff"] == 30000 and items[(cust.id, "USD")]["diff"] == 5
    assert db.query(Log).filter(Log.kind == "recalc").count() == 0
    fix = client.login(w.admin).post("/api/customers/debt-log/reconcile?dry_run=false")
    assert fix.status_code == 200 and fix.json()["count"] == 2
    assert db.query(Log).filter(Log.kind == "recalc").count() == 2
    again = client.login(w.admin).post("/api/customers/debt-log/reconcile?dry_run=true")
    assert again.json()["items"] == []
    # kassir reconcile qila olmaydi
    assert client.login(w.cash_chil).post("/api/customers/debt-log/reconcile").status_code == 403


# ── Filial kesimidagi hisobotlar ─────────────────────────────────────────────

def _two_branch_debts(db, w):
    """Chilonzor: A mijoz 3 mln (sotuv), Yunusobod: B mijoz 1 mln (sotuv), filialsiz: C mijoz 200 ming (opening)."""
    a = _customer(db, w.c, w.chil, name="Akmal")
    b = _customer(db, w.c, w.yun, name="Botir")
    c_ = _customer(db, w.c, None, {"UZS": 200000}, name="Sardor")
    sa = _sale(db, w.c, a, w.w_chil, w.chil, w.admin, 3000000)
    sb = _sale(db, w.c, b, w.w_yun, w.yun, w.admin, 1000000)
    _credit(db, a, w.admin, currency="UZS", amount=3000000, sale=sa)
    _credit(db, b, w.admin, currency="UZS", amount=1000000, sale=sb)
    return a, b, c_, sa, sb


def test_report_customer_debts_branch_filter_and_by_branch_sum(db, client, world):
    w = world
    a, b, c_, sa, sb = _two_branch_debts(db, w)
    r = client.login(w.admin).get(f"/api/reports/customer-debts?branch_id={w.chil.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert [i["customer_name"] for i in data["items"]] == ["Akmal"]
    assert data["items"][0]["branch_id"] == w.chil.id and data["items"][0]["branch_name"] == "Chilonzor"
    assert data["total_debt_uzs"] == 3000000
    full = client.login(w.admin).get("/api/reports/customer-debts").json()
    assert full["total_debt_uzs"] == 4200000 and full["count"] == 3
    by_sum = sum(x["debt_uzs"] for x in full["by_branch"]) + full["unassigned"]["debt_uzs"]
    assert by_sum == pytest.approx(full["total_debt_uzs"])
    assert full["unassigned"]["debt_uzs"] == 200000 and full["unassigned"]["debtor_count"] == 1
    by = {x["branch_name"]: x for x in full["by_branch"]}
    assert by["Chilonzor"]["debt_uzs"] == 3000000 and by["Yunusobod"]["debtor_count"] == 1
    un = client.login(w.admin).get("/api/reports/customer-debts?branch_id=-1").json()
    assert [i["customer_name"] for i in un["items"]] == ["Sardor"]


def test_report_branch_isolation_between_companies(db, mk, client, world):
    w = world
    _two_branch_debts(db, w)
    other_c, other_b, other_w, other_u = mk.tenant()
    # begona korxona filialini so'rash -> 404, o'z filialini so'rasa bo'sh
    assert client.login(other_u).get(f"/api/reports/customer-debts?branch_id={w.chil.id}").status_code == 404
    assert client.login(other_u).get(f"/api/finance/customer-debts?branch_id={w.chil.id}").status_code == 404
    assert client.login(other_u).get(f"/api/reports/supplier-debts?branch_id={w.chil.id}").status_code == 404
    mine = client.login(other_u).get(f"/api/reports/customer-debts?branch_id={other_b.id}")
    assert mine.status_code == 200 and mine.json()["items"] == [] and mine.json()["total_debt_uzs"] == 0
    full = client.login(other_u).get("/api/reports/customer-debts").json()
    assert full["items"] == [] and full["by_branch"] == []


def test_cross_branch_payment_reduces_sale_branch_and_collections(db, client, world):
    w = world
    a, b, c_, sa, sb = _two_branch_debts(db, w)
    # Akmal Chilonzorda olgan 3 mln qarzdan 1 mlnni Yunusobod kassirga to'laydi
    r = client.login(w.cash_yun).post(f"/api/customers/{a.id}/pay-debt", json={
        "amount": 1000000, "reason": "Yunusobodda to'ladi", "wallet_id": w.k_yun.id})
    assert r.status_code == 200, r.text
    data = cl.debt_by_branch(db, w.c.id)
    by = {x["branch_name"]: x for x in data["by_branch"]}
    assert by["Chilonzor"]["debt_uzs"] == 2000000          # Chilonzor kamaydi (FIFO sotuv filiali bo'yicha)
    assert by["Yunusobod"]["debt_uzs"] == 1000000          # Yunusobodning o'z qarzi o'zgarmadi
    row = db.query(Log).filter(Log.kind == "payment").one()
    assert row.branch_id == w.chil.id and row.cash_branch_id == w.yun.id
    rep = client.login(w.admin).get("/api/reports/debt-collections")
    assert rep.status_code == 200, rep.text
    j = rep.json()
    assert j["total_uzs"] == 1000000 and j["cross_branch_uzs"] == 1000000
    m = j["matrix"][0]
    assert (m["cash_branch_name"], m["debt_branch_name"], m["cross_branch"]) == ("Yunusobod", "Chilonzor", True)
    assert j["by_cash_branch"][0]["branch_name"] == "Yunusobod"
    assert j["by_debt_branch"][0]["branch_name"] == "Chilonzor"
    # filtr: Chilonzor (qarz egasi) bo'yicha ham ko'rinadi, begona filial 404
    f = client.login(w.admin).get(f"/api/reports/debt-collections?branch_id={w.chil.id}").json()
    assert f["total_uzs"] == 1000000
    assert client.login(w.admin).get("/api/reports/debt-collections?branch_id=999999").status_code == 404
    # to'lov o'chirilsa — Chilonzor qarzi qaytadi va undirish 0 bo'ladi
    tx_id = r.json()["transaction_ids"][0]
    assert client.login(w.admin).delete(f"/api/finance/transactions/{tx_id}").status_code == 204
    by2 = {x["branch_name"]: x for x in cl.debt_by_branch(db, w.c.id)["by_branch"]}
    assert by2["Chilonzor"]["debt_uzs"] == 3000000
    assert client.login(w.admin).get("/api/reports/debt-collections").json()["total_uzs"] == 0


def test_branch_report_exact_when_journal_is_incomplete(db, world):
    """Jurnalga tushmagan (eski kod yozgan) qarz mijoz filialiga yoziladi — filiallar yig'indisi baribir to'liq."""
    w = world
    cust = _customer(db, w.c, w.yun, {"UZS": 100000})
    cust.debt_balances = {"UZS": 250000.0}                # jurnalda faqat 100 ming
    cust.debt_balance = D("250000")
    db.flush()
    data = cl.debt_by_branch(db, w.c.id)
    total = sum(x["debt_uzs"] for x in data["by_branch"]) + data["unassigned"]["debt_uzs"]
    assert total == 250000
    assert data["by_branch"][0]["branch_name"] == "Yunusobod"


def test_finance_customer_debts_branch_and_overdue_formula(db, client, world):
    from datetime import date, timedelta
    w = world
    a, b, c_, sa, sb = _two_branch_debts(db, w)
    sa.debt_due_date = date.today() - timedelta(days=3)
    db.flush()
    r = client.login(w.admin).get(f"/api/finance/customer-debts?branch_id={w.chil.id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert [i["name"] for i in d["items"]] == ["Akmal"] and d["items"][0]["overdue"] is True
    assert d["total_debt"] == 3000000 and d["scope"] == "branch"
    full = client.login(w.admin).get("/api/finance/customer-debts").json()
    assert full["scope"] == "company" and "by_branch" in full and "unassigned" in full
    assert sum(x["debt_uzs"] for x in full["by_branch"]) + full["unassigned"]["debt_uzs"] == pytest.approx(full["total_debt"])
    # USD sotuv to'liq to'langach "muddati o'tgan" belgisi ketadi (paid_amount sotuv valyutasida)
    cust = _customer(db, w.c, w.chil)
    s = _sale(db, w.c, cust, w.w_chil, w.chil, w.admin, 1270000, rate=12700)
    s.debt_due_date = date.today() - timedelta(days=1)
    _credit(db, cust, w.admin, currency="USD", amount=100, sale=s)
    ov = client.login(w.admin).get("/api/finance/customer-debts").json()
    assert any(i["id"] == cust.id and i["overdue"] for i in ov["items"])
    client.login(w.admin).post(f"/api/finance/customer-debts/{cust.id}/pay", json={
        "amount": 100, "currency": "USD", "wallet_id": w.k_chil.id})
    ov2 = client.login(w.admin).get("/api/finance/customer-debts").json()
    assert not any(i["id"] == cust.id for i in ov2["items"])


# ── Mijoz kartasi: to'lovlar customer_id bo'yicha ────────────────────────────

def test_customer_payments_endpoint_by_id_not_name(db, client, world):
    w = world
    c1 = _customer(db, w.c, w.chil, {"UZS": 100000}, name="Akmal aka")
    c2 = _customer(db, w.c, w.yun, {"UZS": 100000}, name="Akmal aka")
    for cust, amt in ((c1, 10000), (c2, 20000)):
        assert client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt", json={
            "amount": amt, "reason": "x", "wallet_id": w.k_chil.id}).status_code == 200
    # kassir ham ko'ra oladi
    r = client.login(w.cash_chil).get(f"/api/customers/{c1.id}/payments")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["total"] == 1 and j["items"][0]["amount"] == 10000
    for key in ("id", "amount", "currency", "payment_type", "wallet_id", "wallet_name", "branch_id",
                "branch_name", "user_name", "description", "allocation", "created_at"):
        assert key in j["items"][0]
    assert j["items"][0]["wallet_name"] == w.k_chil.name
    r2 = client.login(w.admin).get(f"/api/customers/{c2.id}/payments").json()
    assert r2["total"] == 1 and r2["items"][0]["amount"] == 20000
    # sahifalash va sana
    assert client.login(w.admin).get(f"/api/customers/{c1.id}/payments?skip=1&limit=10").json()["items"] == []
    assert client.login(w.admin).get(f"/api/customers/{c1.id}/payments?date_from=2000-01-01&date_to=2000-01-02").json()["total"] == 0


def test_customer_payments_and_debt_log_company_isolation(db, mk, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 1000})
    other_c, other_b, other_w, other_u = mk.tenant()
    assert client.login(other_u).get(f"/api/customers/{cust.id}/payments").status_code == 404
    assert client.login(other_u).get(f"/api/customers/{cust.id}/debt-log").status_code == 404
    own = client.login(w.admin).get(f"/api/customers/{cust.id}/debt-log")
    assert own.status_code == 200 and own.json()["total"] == 1 and own.json()["items"][0]["kind"] == "opening"
    assert own.json()["items"][0]["branch_name"] == "Chilonzor"


def test_income_payments_items_have_reference_customer_branch(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000})
    client.login(w.admin).post(f"/api/customers/{cust.id}/pay-debt", json={
        "amount": 5000, "reason": "x", "wallet_id": w.k_chil.id})
    r = client.login(w.admin).get("/api/finance/payments/income")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["reference_id"] == cust.id and item["customer_id"] == cust.id and item["branch_id"] == w.chil.id


def test_history_uses_journal(db, client, world):
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000})
    client.login(w.admin).post(f"/api/customers/{cust.id}/adjust-debt", json={
        "reason": "Sabab yozildi", "changes": [{"currency": "UZS", "delta": 5000}]})
    r = client.login(w.cash_chil).get(f"/api/customers/{cust.id}/history")
    assert r.status_code == 200, r.text
    edits = [h for h in r.json() if h["op_type"] == "debt_edit"]
    kinds = sorted(h.get("kind") or "legacy" for h in edits)
    assert kinds == ["edit", "opening"]                    # adjust-debt ikki marta (jurnal + eski tarix) chiqmaydi
    e = next(h for h in edits if h.get("kind") == "edit")
    assert e["debt"] == 5000 and e["cashier"] == w.admin.name and e["branch_name"] == "Chilonzor"
    assert "Sabab yozildi" in e["description"]


# ── summary-stats va distributors-report ─────────────────────────────────────

def test_summary_stats_and_distributors_branch(db, client, world):
    w = world
    a, b, c_, sa, sb = _two_branch_debts(db, w)
    full = client.login(w.admin).get("/api/customers/summary-stats").json()
    assert full["total_debt"] == 4200000 and full["total_debtors"] == 3
    br = client.login(w.admin).get(f"/api/customers/summary-stats?branch_id={w.chil.id}").json()
    assert br["total_debt"] == 3000000 and br["total_debtors"] == 1 and br["total_customers"] == 1
    a.customer_type = "distributor"
    a.debt_limit = D("6000000")
    db.flush()
    rep = client.login(w.admin).get(f"/api/customers/distributors-report?branch_id={w.chil.id}").json()
    assert rep["items"][0]["debt"] == 3000000 and rep["items"][0]["limit_usage"] == 50.0
    other = client.login(w.admin).get(f"/api/customers/distributors-report?branch_id={w.yun.id}").json()
    assert other["items"] == []


# ── AI vositalari ────────────────────────────────────────────────────────────

def test_ai_tools_use_ledger(db, world):
    from app.services.ai_tools_registry import RecordDebtPaymentTool, RecordNewDebtTool
    w = world
    cust = _customer(db, w.c, w.chil, {"UZS": 100000}, name="Zafar Test")
    out = RecordNewDebtTool().execute(db, w.c.id, w.admin, customer_name="Zafar Test", amount=25000)
    assert "nasiya yozildi" in out["reply"]
    row = db.query(Log).filter(Log.kind == "ai").one()
    assert row.user_id == w.admin.id and row.branch_id == w.chil.id and float(row.delta) == 25000
    assert _bal(cust) == {"UZS": 125000.0}
    out = RecordDebtPaymentTool().execute(db, w.c.id, w.cash_chil, customer_name="Zafar Test", amount=25000)
    assert out["reply"].startswith("✅")
    assert _bal(cust) == {"UZS": 100000.0}
    tx = db.query(Transaction).filter(Transaction.reference_type == "customer_payment").one()
    assert tx.branch_id == w.chil.id and tx.wallet_id == w.k_chil.id            # branch_id=0 emas, kassa yagona qoida bilan
    assert db.query(KassaMovement).filter(KassaMovement.reference_id == cust.id).count() == 1
    # kassa topilmasa — xato javob, qarz o'zgarmaydi
    w.k_chil.is_open = False
    w.k_yun.is_open = False
    db.flush()
    out = RecordDebtPaymentTool().execute(db, w.c.id, w.admin, customer_name="Zafar Test", amount=1000)
    assert out["reply"].startswith("❌")
    assert _bal(cust) == {"UZS": 100000.0}
    assert cl.reconcile(db, w.c.id) == []


# ── Agent ilovasi ────────────────────────────────────────────────────────────

def test_agent_collect_payment_uses_service(db, mk, client, world):
    w = world
    agent = mk.user(w.c, role=UserRole.agent, branch=w.chil)
    cust = _customer(db, w.c, w.chil, {"UZS": 80000})
    cust.agent_id = agent.id
    w.c.distribution_enabled = True
    db.flush()
    r = client.login(agent).post("/api/mobile/agent/payments", json={"customer_id": cust.id, "amount": 30000})
    assert r.status_code == 200, r.text
    assert r.json()["remaining_debt"] == 50000
    db.refresh(cust)
    assert cust.debt_balances == {"UZS": 50000.0}
    tx = db.query(Transaction).filter(Transaction.reference_type == "customer_payment").one()
    assert tx.user_id == agent.id and tx.meta and "allocation" in tx.meta
    assert db.query(Log).filter(Log.kind == "payment", Log.transaction_id == tx.id).count() == 1


# ── Ta'minotchi kreditorligi filial kesimida ─────────────────────────────────

def _po(db, w, supplier, warehouse, debt, currency="UZS"):
    po = PurchaseOrder(number=f"PO{next(_seq):06d}", supplier_id=supplier.id, warehouse_id=warehouse.id,
                       company_id=w.c.id, status=POStatus.received, created_by=w.admin.id, currency=currency,
                       supplier_debt=D(str(debt)), supplier_debt_currency=currency)
    db.add(po)
    db.flush()
    return po


def test_supplier_debt_by_branch_and_unallocated(db, mk, client, world):
    w = world
    s = Supplier(name="Ta'minotchi 1", company_id=w.c.id, is_active=True)
    db.add(s)
    db.flush()
    _po(db, w, s, w.w_chil, 5000000)
    _po(db, w, s, w.w_yun, 3000000)
    sl._save(db, s, {"UZS": D("4000000")})            # HQ 4 mln to'ladi (8 mln - 4 mln), xaridlarga taqsimlanmagan
    db.flush()
    data = sl.debt_by_branch(db, w.c.id)
    by = {b["branch_name"]: b for b in data["by_branch"]}
    assert by["Chilonzor"]["debt_uzs"] == 5000000 and by["Yunusobod"]["debt_uzs"] == 3000000
    assert data["unallocated_payments"] == {"UZS": -4000000.0} and data["unallocated_payments_uzs"] == -4000000.0
    # filial filtri
    f = sl.debt_by_branch(db, w.c.id, w.yun.id)
    assert [r["supplier_id"] for r in f["suppliers"]] == [s.id] and f["suppliers"][0]["debt_uzs"] == 3000000
    # HTTP: ikkala endpoint
    for url in ("/api/reports/supplier-debts", "/api/finance/supplier-debts"):
        full = client.login(w.admin).get(url).json()
        assert full["unallocated_payments"] == {"UZS": -4000000.0}
        assert {b["branch_name"] for b in full["by_branch"]} == {"Chilonzor", "Yunusobod"}
        br = client.login(w.admin).get(f"{url}?branch_id={w.chil.id}").json()
        assert br["items"] and br["scope"] == "branch"
    rep = client.login(w.admin).get(f"/api/reports/supplier-debts?branch_id={w.chil.id}").json()
    assert rep["total_debt_uzs"] == 5000000 and rep["items"][0]["branch_name"] == "Chilonzor"
    # begona korxona ta'minotchisi/PO si ko'rinmaydi
    other_c, other_b, other_w, other_u = mk.tenant()
    assert sl.debt_by_branch(db, other_c.id)["by_branch"] == []


def test_supplier_debts_rate_map_once(db, client, world):
    """12-mezon: kurs so'rovlari ta'minotchi/valyuta soniga bog'liq emas (bitta rate_map)."""
    from sqlalchemy import event
    w = world
    for i in range(6):
        s = Supplier(name=f"T{i}", company_id=w.c.id, is_active=True)
        db.add(s)
        db.flush()
        sl._save(db, s, {"UZS": D("1000"), "USD": D("5")})
    db.flush()
    counts = []

    def run():
        n = {"c": 0}

        def _count(conn, cursor, statement, *a):
            if "currencies" in statement.lower():
                n["c"] += 1
        eng = db.get_bind()
        event.listen(eng, "before_cursor_execute", _count)
        try:
            assert client.login(w.admin).get("/api/finance/supplier-debts").status_code == 200
        finally:
            event.remove(eng, "before_cursor_execute", _count)
        return n["c"]

    first = run()
    for i in range(6, 12):
        s = Supplier(name=f"T{i}", company_id=w.c.id, is_active=True)
        db.add(s)
        db.flush()
        sl._save(db, s, {"UZS": D("1000"), "USD": D("5")})
    db.flush()
    assert run() <= first + 1                  # 2x ko'p ta'minotchi -> kurs so'rovlari ko'paymaydi


# ── Frontend: KirimTolovlar bitta so'rov ─────────────────────────────────────

def test_kirim_tolovlar_sends_single_payments_request():
    src = open(os.path.join(ROOT, "frontend", "src", "pages", "admin", "KirimTolovlar.jsx"), encoding="utf-8").read()
    assert "payments: valid.map(" in src
    assert "for (const row of valid) {\n          await api.post(`/customers/" not in src.replace("\r\n", "\n")
