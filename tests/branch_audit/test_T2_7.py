"""T2.7 — ko'p valyuta: kassa, xarajat, kurs korxonaga bog'liq.

Qamrov: currency_service (get_rate/rate_map/to_uzs/amount_uzs_sql/require_active_currency), report_utils.currency_rate_map
ustuvorligi, mijoz qarzi kursi (recalc-debts, pay-debt GET/POST), kassa xarajat/invest/withdraw da Wallet.balance faqat UZS,
Expense.currency/exchange_rate/amount_uzs, finance xarajati va cash-balance UZS ekvivalenti, migratsiya backfill.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T2_7.py -q -p no:cacheprovider
"""
import importlib.util
import itertools
import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import func, text

from app.models.currency import Currency
from app.models.customer import Customer
from app.models.moliya import Expense, ExpenseCategory, KassaMovement, Transaction, Wallet
from app.models.user import UserRole
from app.services import currency_service as cs
from app.services import supplier_ledger

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
D = Decimal


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _cur(db, company, code="USD", rate=12700, active=True, name=None):
    c = Currency(name=name or code, code=code, rate=rate, company_id=company.id if company else None,
                 is_active=active)
    db.add(c)
    db.flush()
    return c


def _wallet(db, company, branch, balance=1000):
    w = Wallet(name=f"Kassa {next(_seq)}", company_id=company.id, branch_id=branch.id, balance=D(balance),
               is_active=True, is_open=True)
    db.add(w)
    db.flush()
    return w


def _cat(db, company):
    c = ExpenseCategory(name=f"Kat {next(_seq)}", company_id=company.id)
    db.add(c)
    db.flush()
    return c


def _customer(db, company, branch, balances=None, debt_balance=0):
    c = Customer(name=f"Mijoz {next(_seq)}", phone=f"9988{next(_seq):07d}", company_id=company.id,
                 branch_id=branch.id, debt_balances=balances or {}, debt_balance=D(debt_balance))
    db.add(c)
    db.flush()
    return c


def _world(mk, db):
    """Ikki korxona: bir xil USD kodi, turli kurs (A=12700, B=12000), har birida kassa va kategoriya."""
    ca, ba, _wa, ua = mk.tenant()
    cb, bb, _wb, ub = mk.tenant()
    _cur(db, ca, "USD", 12700)
    _cur(db, cb, "USD", 12000)
    return dict(ca=ca, ba=ba, ua=ua, cb=cb, bb=bb, ub=ub,
                wa=_wallet(db, ca, ba), wb=_wallet(db, cb, bb), cat_a=_cat(db, ca), cat_b=_cat(db, cb))


def _bal(db, w):
    db.refresh(w)
    return D(str(w.balance))


# ── currency_service ─────────────────────────────────────────────────────────

def test_get_rate_is_company_scoped(mk, db):
    w = _world(mk, db)
    assert cs.get_rate(db, w["ca"].id, "USD") == D("12700")
    assert cs.get_rate(db, w["cb"].id, "usd") == D("12000")
    assert cs.get_rate(db, w["ca"].id, "UZS") == 1
    assert cs.get_rate(db, w["ca"].id, "EUR") == 1          # topilmasa 1
    # supplier_ledger.currency_rate — alias, xuddi shu natija
    assert supplier_ledger.currency_rate(db, w["ca"].id, "USD") == D("12700")


def test_get_rate_company_row_beats_global_and_falls_back(mk, db):
    c = mk.company()
    _cur(db, None, "USD", 11000)                     # global
    _cur(db, None, "EUR", 14000)
    assert cs.get_rate(db, c.id, "USD") == D("11000")      # korxona qatori yo'q -> global
    _cur(db, c, "USD", 12500)
    assert cs.get_rate(db, c.id, "USD") == D("12500")      # korxona qatori ustun
    assert cs.get_rate(db, c.id, "EUR") == D("14000")
    assert cs.get_rate(db, None, "USD") == D("11000")      # super_admin: faqat global
    zero = mk.company()
    _cur(db, zero, "GBP", 0)
    assert cs.get_rate(db, zero.id, "GBP") == 1            # rate<=0 -> 1


def test_rate_map_priority_is_deterministic(mk, db):
    c = mk.company()
    # global qatorlar DB da KEYIN qo'shiladi: eski kod setdefault bilan shuni tanlab olardi
    _cur(db, c, "USD", 12500)
    _cur(db, None, "USD", 11000)
    _cur(db, None, "EUR", 14000)
    other = mk.company()
    _cur(db, other, "USD", 9999)
    _cur(db, other, "RUB", 150)
    for _ in range(3):
        m = cs.rate_map(db, c.id)
        assert m["USD"] == D("12500")
        assert m["EUR"] == D("14000")
        assert m["UZS"] == 1
        assert "RUB" not in m                                # begona korxona kursi yo'q
    assert cs.rate_map(db, None)["USD"] == D("11000")        # super_admin: faqat global
    assert "RUB" not in cs.rate_map(db, None)


def test_report_utils_currency_rate_map_uses_company_row(mk, db):
    from app.utils.report_utils import currency_rate_map
    c = mk.company()
    _cur(db, c, "USD", 12500)
    _cur(db, None, "USD", 11000)
    for _ in range(3):
        m = currency_rate_map(db, c.id)
        assert m["USD"] == 12500.0 and m["UZS"] == 1.0
    c2 = mk.company()
    assert currency_rate_map(db, c2.id)["USD"] == 11000.0    # korxona qatori yo'q -> global


def test_to_uzs_and_amount_uzs_sql(mk, db):
    rates = {"UZS": D(1), "USD": D("12700")}
    assert cs.to_uzs(100, "USD", rates) == D("1270000")
    assert cs.to_uzs(100, "uzs", rates) == D("100")
    assert cs.to_uzs(100, "XXX", rates) == D("100")          # kursi noma'lum -> 1
    c, b, _w, _u = mk.tenant()
    for amt, cur in ((100, "USD"), (5000, "UZS"), (10, None)):
        db.add(Transaction(company_id=c.id, branch_id=b.id, type="income", amount=D(amt), currency_code=cur))
    db.flush()
    total = db.query(func.sum(cs.amount_uzs_sql(Transaction.amount, Transaction.currency_code, rates))) \
        .filter(Transaction.company_id == c.id).scalar()
    assert D(str(total)) == D("1270000") + D("5000") + D("10")


def test_require_active_currency(mk, db):
    w = _world(mk, db)
    _cur(db, w["cb"], "EUR", 14000)
    _cur(db, w["ca"], "RUB", 150, active=False)
    from fastapi import HTTPException
    assert cs.require_active_currency(db, w["ca"].id, "usd") == "USD"
    assert cs.require_active_currency(db, w["ca"].id, None) == "UZS"
    for code in ("EUR", "RUB", "XXX"):                       # begona / nofaol / noma'lum
        with pytest.raises(HTTPException) as e:
            cs.require_active_currency(db, w["ca"].id, code)
        assert e.value.status_code == 400
        assert code in e.value.detail


# ── Mijoz qarzi: kurs korxonaniki ────────────────────────────────────────────

def test_calc_debt_in_uzs_uses_company_rate(mk, db):
    from app.routers.customers import _calc_debt_in_uzs, _recalc_debt_uzs
    w = _world(mk, db)
    assert _calc_debt_in_uzs({"USD": 100, "UZS": 1000}, db, company_id=w["ca"].id) == D("1271000")
    assert _calc_debt_in_uzs({"USD": 100}, db, company_id=w["cb"].id) == D("1200000")
    assert _recalc_debt_uzs({"usd": 100}, db, w["cb"].id) == D("1200000")
    rm = cs.rate_map(db, w["ca"].id)
    assert _calc_debt_in_uzs({"USD": 100}, db, rm) == D("1270000")


def test_recalc_debts_only_own_company_with_own_rate(mk, db, client):
    w = _world(mk, db)
    ca1 = _customer(db, w["ca"], w["ba"], {"USD": 100}, debt_balance=1)
    cb1 = _customer(db, w["cb"], w["bb"], {"USD": 100}, debt_balance=777)
    r = client.login(w["ua"]).post("/api/customers/recalc-debts")
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1
    db.refresh(ca1)
    db.refresh(cb1)
    assert D(str(ca1.debt_balance)) == D("1270000")          # A kursi (B kursi 12000 emas)
    assert D(str(cb1.debt_balance)) == D("777")              # B mijozi tegilmadi


def test_recalc_debts_forbidden_for_cashier(mk, db, client):
    c, b, _w, _u = mk.tenant()
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    r = client.login(cashier).post("/api/customers/recalc-debts")
    assert r.status_code == 403


def test_pay_debt_get_returns_only_own_currencies(mk, db, client):
    w = _world(mk, db)
    _cur(db, w["cb"], "EUR", 14000, name="Yevro B")
    cust = _customer(db, w["ca"], w["ba"], {"USD": 50}, debt_balance=635000)
    r = client.login(w["ua"]).get(f"/api/customers/{cust.id}/pay-debt")
    assert r.status_code == 200, r.text
    cur = {c["code"]: c["rate"] for c in r.json()["currencies"]}
    assert cur == {"USD": 12700.0}                           # B ning USD (12000) va EUR si yo'q


def test_pay_debt_get_hides_inactive_currency(mk, db, client):
    w = _world(mk, db)
    _cur(db, w["ca"], "EUR", 14000, active=False)
    cust = _customer(db, w["ca"], w["ba"], {"USD": 50}, debt_balance=635000)
    r = client.login(w["ua"]).get(f"/api/customers/{cust.id}/pay-debt")
    assert {c["code"] for c in r.json()["currencies"]} == {"USD"}


def test_adjust_debt_rejects_foreign_company_currency(mk, db, client):
    w = _world(mk, db)
    _cur(db, w["cb"], "EUR", 14000)
    cust = _customer(db, w["ca"], w["ba"], {}, 0)
    r = client.login(w["ua"]).post(f"/api/customers/{cust.id}/adjust-debt",
                                   json={"reason": "test", "changes": [{"currency": "EUR", "delta": 10}]})
    assert r.status_code == 400
    r = client.login(w["ua"]).post(f"/api/customers/{cust.id}/adjust-debt",
                                   json={"reason": "test", "changes": [{"currency": "USD", "delta": 10}]})
    assert r.status_code == 200, r.text
    db.refresh(cust)
    assert D(str(cust.debt_balance)) == D("127000")          # A kursi


def _pay(client, user, cust, wallet, amount, currency):
    return client.login(user).post(f"/api/customers/{cust.id}/pay-debt", json={
        "reason": "to'lov", "wallet_id": wallet.id,
        "payments": [{"amount": amount, "currency": currency, "payment_type": "cash"}],
    })


def test_pay_debt_usd_does_not_touch_wallet_balance(mk, db, client):
    w = _world(mk, db)
    cust = _customer(db, w["ca"], w["ba"], {"USD": 300}, debt_balance=300 * 12700)
    r = _pay(client, w["ua"], cust, w["wa"], 100, "USD")
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("1000")                    # Wallet.balance o'zgarmadi
    km = db.query(KassaMovement).filter_by(reference_type="customer_payment", reference_id=cust.id).one()
    assert km.currency == "USD" and D(str(km.amount)) == D("100")
    tx = db.query(Transaction).filter_by(reference_type="customer_payment", reference_id=cust.id).one()
    assert tx.currency_code == "USD"
    db.refresh(cust)
    assert D(str(cust.debt_balance)) == D(300 * 12700 - 100 * 12700)   # A kursi bilan


def test_pay_debt_uzs_increases_wallet_balance(mk, db, client):
    w = _world(mk, db)
    cust = _customer(db, w["ca"], w["ba"], {"UZS": 50000}, debt_balance=50000)
    r = _pay(client, w["ua"], cust, w["wa"], 20000, "UZS")
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("21000")
    km = db.query(KassaMovement).filter_by(reference_type="customer_payment", reference_id=cust.id).one()
    assert km.currency == "UZS"


def test_pay_debt_uses_company_rate_for_cross_currency(mk, db, client):
    w = _world(mk, db)
    cust = _customer(db, w["ca"], w["ba"], {"USD": 100}, debt_balance=100 * 12700)
    r = _pay(client, w["ua"], cust, w["wa"], 635000, "UZS")   # 635000 UZS = 50 USD (A kursi)
    assert r.status_code == 200, r.text
    db.refresh(cust)
    assert float(cust.debt_balances["USD"]) == pytest.approx(50.0)


# ── Kassa: xarajat ───────────────────────────────────────────────────────────

def _do_expense(client, user, wallet, cat, amount, currency=None, **kw):
    body = {"wallet_id": wallet.id, "category_id": cat.id, "amount": amount, "description": "yuk tashish", **kw}
    if currency is not None:
        body["currency"] = currency
    return client.login(user).post("/api/kassa/do-expense", json=body)


def test_kassa_usd_expense_keeps_currency_and_wallet(mk, db, client):
    w = _world(mk, db)
    r = _do_expense(client, w["ua"], w["wa"], w["cat_a"], 200, "USD")
    assert r.status_code == 200, r.text
    eid = r.json()["expense_id"]
    assert _bal(db, w["wa"]) == D("1000")                    # Wallet.balance o'zgarmadi
    e = db.get(Expense, eid)
    assert e.currency == "USD" and D(str(e.exchange_rate)) == D("12700")
    assert D(str(e.amount_uzs)) == D("2540000") and D(str(e.amount)) == D("200")   # 200 * A kursi
    km = db.query(KassaMovement).filter_by(reference_type="expense", reference_id=eid).one()
    assert km.currency == "USD"
    tx = db.query(Transaction).filter_by(reference_type="expense", reference_id=eid).one()
    assert tx.currency_code == "USD"


def test_kassa_uzs_expense_decreases_wallet_and_records_uzs(mk, db, client):
    w = _world(mk, db)
    r = _do_expense(client, w["ua"], w["wa"], w["cat_a"], 300)   # currency berilmagan -> UZS
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("700")
    e = db.get(Expense, r.json()["expense_id"])
    assert e.currency == "UZS" and D(str(e.amount_uzs)) == D("300") and D(str(e.exchange_rate)) == 1
    tx = db.query(Transaction).filter_by(reference_type="expense", reference_id=e.id).one()
    assert tx.currency_code == "UZS"


def test_kassa_expense_rejects_unknown_foreign_or_inactive_currency(mk, db, client):
    w = _world(mk, db)
    _cur(db, w["cb"], "EUR", 14000)
    _cur(db, w["ca"], "RUB", 150, active=False)
    for code in ("EUR", "RUB", "XXX"):
        r = _do_expense(client, w["ua"], w["wa"], w["cat_a"], 10, code)
        assert r.status_code == 400, (code, r.text)
        assert "Noma'lum yoki nofaol valyuta" in r.json()["detail"]
    assert _bal(db, w["wa"]) == D("1000")
    assert db.query(Expense).filter_by(company_id=w["ca"].id).count() == 0


def test_kassa_expense_uses_own_company_rate_not_foreign(mk, db, client):
    w = _world(mk, db)
    r = _do_expense(client, w["ub"], w["wb"], w["cat_b"], 100, "USD")
    assert r.status_code == 200, r.text
    e = db.get(Expense, r.json()["expense_id"])
    assert D(str(e.amount_uzs)) == D("1200000")              # B kursi 12000


def test_kassa_expense_isolation_between_companies(mk, db, client):
    w = _world(mk, db)
    r = _do_expense(client, w["ua"], w["wb"], w["cat_a"], 10, "USD")     # A -> B kassasi
    assert r.status_code == 404
    own = _do_expense(client, w["ua"], w["wa"], w["cat_a"], 10, "USD")
    assert own.status_code == 200
    eid = own.json()["expense_id"]
    # B admini A xarajatini tahrirlay/o'chira olmaydi
    assert client.login(w["ub"]).put(f"/api/kassa/expense/{eid}", json={"amount": 5}).status_code == 404
    assert client.login(w["ub"]).delete(f"/api/kassa/expense/{eid}").status_code == 404


def test_kassa_uzs_expense_update_and_delete_restore_wallet(mk, db, client):
    w = _world(mk, db)
    eid = _do_expense(client, w["ua"], w["wa"], w["cat_a"], 300).json()["expense_id"]
    assert _bal(db, w["wa"]) == D("700")
    r = client.login(w["ua"]).put(f"/api/kassa/expense/{eid}", json={"amount": 500})
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("500")                     # 1000 - 500
    e = db.get(Expense, eid)
    assert D(str(e.amount_uzs)) == D("500")
    r = client.login(w["ua"]).delete(f"/api/kassa/expense/{eid}")
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("1000")                    # to'liq tiklandi


def test_kassa_usd_expense_update_and_delete_leave_wallet_untouched(mk, db, client):
    w = _world(mk, db)
    eid = _do_expense(client, w["ua"], w["wa"], w["cat_a"], 200, "USD").json()["expense_id"]
    r = client.login(w["ua"]).put(f"/api/kassa/expense/{eid}", json={"amount": 300})
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("1000")
    e = db.get(Expense, eid)
    assert D(str(e.amount)) == D("300") and D(str(e.amount_uzs)) == D("3810000")
    assert db.query(KassaMovement).filter_by(reference_type="expense", reference_id=eid).one().amount == 300
    r = client.login(w["ua"]).delete(f"/api/kassa/expense/{eid}")
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("1000")
    void_km = db.query(KassaMovement).filter_by(reference_type="expense_void", reference_id=eid).one()
    assert void_km.currency == "USD"


def test_kassa_expense_currency_change_recomputes_and_switches_wallet_rule(mk, db, client):
    w = _world(mk, db)
    eid = _do_expense(client, w["ua"], w["wa"], w["cat_a"], 100).json()["expense_id"]   # UZS: 1000 -> 900
    assert _bal(db, w["wa"]) == D("900")
    r = client.login(w["ua"]).put(f"/api/kassa/expense/{eid}", json={"currency": "USD"})
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("1000")                    # UZS chiqim qaytarildi, USD balansga tegmaydi
    e = db.get(Expense, eid)
    assert e.currency == "USD" and D(str(e.exchange_rate)) == D("12700") and D(str(e.amount_uzs)) == D("1270000")
    assert db.query(KassaMovement).filter_by(reference_type="expense", reference_id=eid).one().currency == "USD"
    assert db.query(Transaction).filter_by(reference_type="expense", reference_id=eid).one().currency_code == "USD"
    # noma'lum valyutaga o'tkazib bo'lmaydi
    r = client.login(w["ua"]).put(f"/api/kassa/expense/{eid}", json={"currency": "XXX"})
    assert r.status_code == 400
    assert _bal(db, w["wa"]) == D("1000")


def test_kassa_expense_list_exposes_currency_and_amount_uzs(mk, db, client):
    w = _world(mk, db)
    _do_expense(client, w["ua"], w["wa"], w["cat_a"], 200, "USD")
    r = client.login(w["ua"]).get(f"/api/kassa/{w['wa'].id}/expenses")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["currency"] == "USD" and item["amount"] == 200.0 and item["amount_uzs"] == 2540000.0


# ── Kassa: invest / withdraw ─────────────────────────────────────────────────

def test_invest_withdraw_wallet_balance_only_for_uzs(mk, db, client):
    w = _world(mk, db)
    c = client.login(w["ua"])
    wid = w["wa"].id
    assert c.post(f"/api/kassa/{wid}/invest", json={"amount": 100, "currency": "USD"}).status_code == 200
    assert _bal(db, w["wa"]) == D("1000")                    # USD invest balansga tegmaydi
    assert c.post(f"/api/kassa/{wid}/invest", json={"amount": 500, "currency": "UZS"}).status_code == 200
    assert _bal(db, w["wa"]) == D("1500")
    r = c.post(f"/api/kassa/{wid}/withdraw", json={"amount": 40, "currency": "USD"})
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("1500")                    # USD withdraw ham tegmaydi
    r = c.post(f"/api/kassa/{wid}/withdraw", json={"amount": 200, "currency": "UZS"})
    assert r.status_code == 200, r.text
    assert _bal(db, w["wa"]) == D("1300")
    cur = {m.currency for m in db.query(KassaMovement).filter_by(wallet_id=wid).all()}
    assert cur == {"USD", "UZS"}


# ── Finance: xarajat va cash-balance ─────────────────────────────────────────

def test_finance_usd_expense_records_currency_everywhere(mk, db, client):
    w = _world(mk, db)
    r = client.login(w["ua"]).post("/api/finance/expenses", json={
        "category_id": w["cat_a"].id, "amount": 200, "wallet_id": w["wa"].id, "currency": "USD"})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert _bal(db, w["wa"]) == D("1000")
    e = db.get(Expense, eid)
    assert e.currency == "USD" and D(str(e.amount_uzs)) == D("2540000")
    assert db.query(Transaction).filter_by(reference_type="expense", reference_id=eid).one().currency_code == "USD"
    km = db.query(KassaMovement).filter_by(reference_type="expense", reference_id=eid).one()
    assert km.currency == "USD"
    lst = client.login(w["ua"]).get("/api/finance/expenses").json()
    row = [x for x in lst if x["id"] == eid][0]
    assert row["currency"] == "USD" and row["amount_uzs"] == 2540000.0
    # bekor qilish: USD xarajat balansga tegmaydi
    assert client.login(w["ua"]).delete(f"/api/finance/expenses/{eid}").status_code == 204
    assert _bal(db, w["wa"]) == D("1000")


def test_finance_uzs_expense_default_and_void_restore(mk, db, client):
    w = _world(mk, db)
    r = client.login(w["ua"]).post("/api/finance/expenses", json={
        "category_id": w["cat_a"].id, "amount": 250, "wallet_id": w["wa"].id})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    assert _bal(db, w["wa"]) == D("750")
    assert db.get(Expense, eid).currency == "UZS"
    assert client.login(w["ua"]).delete(f"/api/finance/expenses/{eid}").status_code == 204
    assert _bal(db, w["wa"]) == D("1000")


def test_finance_expense_rejects_foreign_currency(mk, db, client):
    w = _world(mk, db)
    _cur(db, w["cb"], "EUR", 14000)
    r = client.login(w["ua"]).post("/api/finance/expenses", json={
        "category_id": w["cat_a"].id, "amount": 10, "wallet_id": w["wa"].id, "currency": "EUR"})
    assert r.status_code == 400


def test_cash_balance_totals_are_uzs_equivalent(mk, db, client):
    w = _world(mk, db)
    ca, ba = w["ca"], w["ba"]
    for amt, cur, typ in ((100, "USD", "income"), (5000, "UZS", "income"), (10, "USD", "expense"),
                          (1000, "UZS", "expense")):
        db.add(Transaction(company_id=ca.id, branch_id=ba.id, type=typ, amount=D(amt), currency_code=cur,
                           payment_type="cash"))
    # B korxonasi yozuvi A hisobotiga kirmasligi kerak
    db.add(Transaction(company_id=w["cb"].id, branch_id=w["bb"].id, type="income", amount=D(999),
                       currency_code="USD", payment_type="cash"))
    db.flush()
    r = client.login(w["ua"]).get("/api/finance/cash-balance")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["income_by_currency"] == {"USD": 100.0, "UZS": 5000.0}
    assert j["expense_by_currency"] == {"USD": 10.0, "UZS": 1000.0}
    assert j["total_income"] == pytest.approx(100 * 12700 + 5000)
    assert j["total_expense"] == pytest.approx(10 * 12700 + 1000)
    assert j["total_income_uzs"] == j["total_income"] and j["total_expense_uzs"] == j["total_expense"]
    assert j["balance_uzs"] == pytest.approx(j["total_income"] - j["total_expense"])


def test_dashboard_cash_balance_is_uzs_equivalent(mk, db, client):
    w = _world(mk, db)
    for amt, cur, typ in ((100, "USD", "income"), (5000, "UZS", "income"), (10, "USD", "expense")):
        db.add(Transaction(company_id=w["ca"].id, branch_id=w["ba"].id, type=typ, amount=D(amt),
                           currency_code=cur, payment_type="cash"))
    db.flush()
    r = client.login(w["ua"]).get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["cash_balance"] == pytest.approx(90 * 12700 + 5000)
    assert j["cash_balance_by_currency"] == {"USD": 90.0, "UZS": 5000.0}


# ── currencies.py: kurs o'zgarganda faqat o'z korxonasi qarzlari ─────────────

def test_currency_update_recalculates_only_own_customers(mk, db, client):
    w = _world(mk, db)
    ca1 = _customer(db, w["ca"], w["ba"], {"USD": 10}, debt_balance=1)
    cb1 = _customer(db, w["cb"], w["bb"], {"USD": 10}, debt_balance=555)
    usd_a = db.query(Currency).filter_by(company_id=w["ca"].id, code="USD").one()
    r = client.login(w["ua"]).patch(f"/api/currencies/{usd_a.id}", json={"rate": 13000})
    assert r.status_code == 200, r.text
    db.refresh(ca1)
    db.refresh(cb1)
    assert D(str(ca1.debt_balance)) == D("130000")
    assert D(str(cb1.debt_balance)) == D("555")


# ── Migratsiya backfill ──────────────────────────────────────────────────────

def _load_migration():
    path = os.path.join(ROOT, "alembic", "versions", "t2_7_expense_currency.py")
    spec = importlib.util.spec_from_file_location("t2_7_expense_currency", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_metadata_and_syntax():
    m = _load_migration()
    assert m.revision == "t2_7" and m.down_revision == "t2_6"   # zanjirga ulangan
    src = open(os.path.join(ROOT, "alembic", "versions", "t2_7_expense_currency.py"), encoding="utf-8").read()
    assert "ADD COLUMN IF NOT EXISTS currency VARCHAR(3) NOT NULL DEFAULT 'UZS'" in src
    assert "DROP COLUMN IF EXISTS" in src


def test_migration_backfill_derives_currency_from_kassa_movements(mk, db):
    m = _load_migration()
    ca, ba, _w, _u = mk.tenant()
    cb, bb, _w2, _u2 = mk.tenant()
    _cur(db, ca, "USD", 12700)
    _cur(db, None, "USD", 11000)             # global qator — korxona qatori ustun bo'lishi kerak
    _cur(db, None, "EUR", 14000)             # faqat global
    cat_a, cat_b = _cat(db, ca), _cat(db, cb)
    wal = _wallet(db, ca, ba)

    def exp(company, branch, cat, amount):
        e = Expense(company_id=company.id, branch_id=branch.id, category_id=cat.id, amount=D(amount))
        db.add(e)
        db.flush()
        return e

    e_uzs = exp(ca, ba, cat_a, 5000)
    e_usd = exp(ca, ba, cat_a, 200)
    e_eur = exp(ca, ba, cat_a, 10)
    e_b = exp(cb, bb, cat_b, 50)             # B da USD kursi yo'q, global bor
    e_norate = exp(ca, ba, cat_a, 7)
    for e, cur in ((e_uzs, "UZS"), (e_usd, "USD"), (e_eur, "EUR"), (e_b, "USD"), (e_norate, "GBP")):
        db.add(KassaMovement(wallet_id=wal.id, company_id=e.company_id, direction="out", amount=e.amount,
                             currency=cur, reference_type="expense", reference_id=e.id))
        db.add(Transaction(company_id=e.company_id, branch_id=e.branch_id, type="expense", amount=e.amount,
                           currency_code="UZS", reference_type="expense", reference_id=e.id))
    db.flush()

    for _ in range(2):                       # idempotent
        for sql in m.SQL_BACKFILL:
            db.execute(text(sql))
        db.expire_all()
        assert (e_uzs.currency, D(str(e_uzs.amount_uzs))) == ("UZS", D("5000"))
        assert (e_usd.currency, D(str(e_usd.exchange_rate)), D(str(e_usd.amount_uzs))) == ("USD", D("12700"), D("2540000"))
        assert (e_eur.currency, D(str(e_eur.amount_uzs))) == ("EUR", D("140000"))
        assert (e_b.currency, D(str(e_b.amount_uzs))) == ("USD", D("550000"))
        assert e_norate.currency == "GBP" and e_norate.amount_uzs is None and e_norate.exchange_rate is None
        codes = {t.reference_id: t.currency_code for t in db.query(Transaction).filter_by(reference_type="expense")}
        assert codes[e_uzs.id] == "UZS" and codes[e_usd.id] == "USD" and codes[e_eur.id] == "EUR"
        assert codes[e_norate.id] == "GBP"


# ── Frontend / kodni statik tekshirish ───────────────────────────────────────

def test_no_unscoped_currency_lookup_left_in_changed_routers():
    for rel in ("app/routers/customers.py", "app/routers/finance.py"):
        src = open(os.path.join(ROOT, rel), encoding="utf-8").read()
        assert "CurrencyModel.code == curr).first()" not in src
        assert "CurrencyModel.code == currency).first()" not in src
        assert "db.query(Currency).all()" not in src
        assert "db.query(CurrencyModel).all()" not in src


KEYS_T2_7 = ["expense.currency", "expense.amountUzs"]


def _merged_i18n(keys):
    """T2.x i18n kalitlari uz/ru/en lug'atlariga birlashtirilgan (pending fayl o'chirilgan):
    {til: {kalit: qiymat}}; kalit lug'atda yo'q bo'lsa KeyError."""
    import re as _re
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'i18n'))
    out = {}
    for lang in ('uz', 'ru', 'en'):
        with open(os.path.join(base, lang + '.js'), encoding='utf-8') as f:
            txt = f.read()
        found = {m.group(1): m.group(2) for m in _re.finditer(r"^\s*'([^']+)':\s*(.+?),?\s*$", txt, _re.M)}
        out[lang] = {k: found[k] for k in keys}
    return out


def test_pending_i18n_keys_consistent():
    data = _merged_i18n(KEYS_T2_7)
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"]) and "expense.currency" in data["uz"]


# ── Mijoz tarixidagi "qarz tahriri": kurs korxonaniki (tekshiruvchi topgan regressiya) ──────────────

def test_customer_history_debt_edit_uses_company_usd_rate(mk, db, client):
    w = _world(mk, db)
    cust = _customer(db, w["ca"], w["ba"], balances={"USD": 100})
    cust.debt_edited = [{
        "edited_from": {"USD": 100}, "edited_to": {"USD": 150},
        "edited_at": "2026-10-01T10:00:00", "reason": "tuzatish", "edited_by": {"id": w["ua"].id, "name": "x"},
    }]
    db.flush()
    r = client.login(w["ua"]).get(f"/api/customers/{cust.id}/history")
    assert r.status_code == 200, r.text
    body = r.json()
    rows = body if isinstance(body, list) else (body.get("items") or body.get("history") or [])
    edits = [x for x in rows if isinstance(x, dict) and x.get("op_type") == "debt_edit" and not x.get("id")]
    assert edits, r.text
    # 50 USD * A korxona kursi 12700 (global/begona 1:1 emas)
    assert float(edits[0]["amount"]) == pytest.approx(50 * 12700)


def test_customer_history_foreign_company_404(mk, db, client):
    w = _world(mk, db)
    cust = _customer(db, w["ca"], w["ba"])
    r = client.login(w["ub"]).get(f"/api/customers/{cust.id}/history")
    assert r.status_code in (403, 404)


def test_calc_debt_in_uzs_callers_pass_company_or_rate_map():
    import ast
    src = open(os.path.join(ROOT, "app/routers/customers.py"), encoding="utf-8").read()
    bad = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_calc_debt_in_uzs":
            has_company = any(k.arg == "company_id" for k in node.keywords)
            has_map = len(node.args) >= 3
            if not (has_company or has_map):
                bad.append(node.lineno)
    assert not bad, f"_calc_debt_in_uzs company_id/currency_map siz chaqirilgan qatorlar: {bad}"
