"""T3.6 — Moliya va Kirim/Chiqim to'lovlari sahifalari.

Qamrov: `ExpenseIn(wallet_id="")` -> None (422 emas); xarajat filiali (body -> kassa -> foydalanuvchi) va
begona korxona kassasi/filiali; `GET /finance/expenses` `wallet_name`/`branch_name`; "Boshqa kirim"
(`POST /finance/transactions`, USD/UZS, `Transaction` + `KassaMovement` + `Wallet.balance` faqat UZS);
`/finance/payments/income|expense` filial/kassa/to'lov turi filtrlari, valyutalar aralashmasligi
(`summary_by_currency`, `summary_by_payment_type`, UZS ekvivalent), `branch_name`; kassa `invest` USD da
`Wallet.balance` o'zgarmaydi; mijoz qarzi to'lovi tanlangan kassa va to'lov turi bilan; `GET /kassa`
`branch_name`; frontend (fayl-matn) tekshiruvlari va i18n pending kalitlari.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_6.py -q -p no:cacheprovider
"""
import itertools
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.currency import Currency
from app.models.customer import Customer
from app.models.moliya import Expense, ExpenseCategory, KassaMovement, KassaSession, Transaction, Wallet
from app.models.user import UserRole
from app.routers.finance import ExpenseIn, TransactionIn
from app.services import customer_ledger as cl

_seq = itertools.count(1)
ROOT = Path(__file__).resolve().parents[2]
ADMIN_JSX = ROOT / "frontend" / "src" / "pages" / "admin"
PENDING = ROOT / "tests" / "branch_audit" / "i18n_pending" / "T3.6.json"


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, *, balance=0, session=True, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=True, is_open=session)
    db.add(w)
    db.flush()
    if session:
        db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
        db.flush()
    return w


def _tx(db, company, branch, wallet, type_, amount, *, ptype="cash", currency="UZS", ref=None, ref_id=None):
    t = Transaction(company_id=company.id, branch_id=branch.id if branch else None,
                    wallet_id=wallet.id if wallet else None, type=type_, amount=Decimal(amount),
                    payment_type=ptype, currency_code=currency, reference_type=ref, reference_id=ref_id)
    t.created_at = datetime(2026, 9, 10, 12, 0)
    db.add(t)
    db.flush()
    return t


@pytest.fixture
def w(db, mk):
    """Korxona A: ikki filial (ba, ba2), har birida kassa; admin; kategoriya; USD kursi. Korxona B: admin, filial, kassa."""
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    ba2 = mk.branch(ca, name="Ikkinchi filial")
    wa = _wallet(db, ca, ba, name="A1 kassa")
    wa2 = _wallet(db, ca, ba2, name="A2 kassa")
    cat = ExpenseCategory(name="Kommunal", company_id=ca.id)
    db.add(cat)
    db.add(Currency(name="USD", code="USD", rate=Decimal("12000"), company_id=ca.id, is_active=True))
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    wb = _wallet(db, cb, bb, name="B kassa")
    db.flush()
    return dict(ca=ca, ba=ba, ba2=ba2, admin=admin, wa=wa, wa2=wa2, cat=cat, cb=cb, bb=bb, admin_b=admin_b, wb=wb)


# ── 1. Sxemalar ──────────────────────────────────────────────────────────────

def test_expense_in_blank_wallet_becomes_none():
    d = ExpenseIn(category_id=1, amount=10, wallet_id="", branch_id="")
    assert d.wallet_id is None and d.branch_id is None
    assert ExpenseIn(category_id=1, amount=10, wallet_id="7").wallet_id == 7
    assert ExpenseIn(category_id=1, amount=10).branch_id is None


def test_transaction_in_keeps_currency_and_payment_type():
    d = TransactionIn(type="income", amount=5, currency_code="USD", payment_type="card", wallet_id="")
    assert d.currency_code == "USD" and d.payment_type == "card" and d.wallet_id is None and d.branch_id is None
    d2 = TransactionIn(type="income", amount=5)
    assert d2.currency_code == "UZS" and d2.payment_type == "cash"


# ── 2. Xarajat ───────────────────────────────────────────────────────────────

def test_expense_with_blank_wallet_is_not_422(db, client, w):
    r = client.login(w["admin"]).post("/api/finance/expenses", json={
        "category_id": w["cat"].id, "amount": 1000, "wallet_id": "", "description": "kommunal"})
    assert r.status_code == 201, r.text
    e = db.get(Expense, r.json()["id"])
    assert e.wallet_id is None and e.branch_id == w["ba"].id      # foydalanuvchi filialiga tushadi


def test_expense_written_to_selected_branch_and_listed_with_names(db, client, w):
    cl_ = client.login(w["admin"])
    r = cl_.post("/api/finance/expenses", json={
        "category_id": w["cat"].id, "amount": 2500, "branch_id": w["ba2"].id, "wallet_id": w["wa2"].id})
    assert r.status_code == 201, r.text
    e = db.get(Expense, r.json()["id"])
    assert e.branch_id == w["ba2"].id and e.wallet_id == w["wa2"].id and e.company_id == w["ca"].id
    tx = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == e.id).one()
    assert tx.branch_id == w["ba2"].id and tx.company_id == w["ca"].id
    row = next(x for x in cl_.get("/api/finance/expenses").json() if x["id"] == e.id)
    assert row["wallet_id"] == w["wa2"].id and row["wallet_name"] == "A2 kassa" and row["branch_name"] == "Ikkinchi filial"
    # filial filtri
    only1 = cl_.get("/api/finance/expenses", params={"branch_id": w["ba"].id}).json()
    assert all(x["branch_id"] == w["ba"].id for x in only1) and e.id not in [x["id"] for x in only1]


def test_expense_branch_defaults_to_wallet_branch(db, client, w):
    r = client.login(w["admin"]).post("/api/finance/expenses", json={
        "category_id": w["cat"].id, "amount": 300, "wallet_id": w["wa2"].id})
    assert r.status_code == 201, r.text
    assert db.get(Expense, r.json()["id"]).branch_id == w["ba2"].id


def test_expense_foreign_wallet_and_branch_rejected(client, w):
    cl_ = client.login(w["admin"])
    r = cl_.post("/api/finance/expenses", json={"category_id": w["cat"].id, "amount": 1, "wallet_id": w["wb"].id})
    assert r.status_code == 404
    r = cl_.post("/api/finance/expenses", json={"category_id": w["cat"].id, "amount": 1, "branch_id": w["bb"].id})
    assert r.status_code in (400, 404)


# ── 3. "Boshqa kirim" ────────────────────────────────────────────────────────

def test_other_income_usd_writes_transaction_and_movement_without_touching_balance(db, client, w):
    r = client.login(w["admin"]).post("/api/finance/transactions", json={
        "type": "income", "amount": 150, "currency_code": "USD", "payment_type": "card",
        "wallet_id": w["wa2"].id, "reference_type": "other_income", "description": "Ijara"})
    assert r.status_code == 201, r.text
    tx = db.get(Transaction, r.json()["id"])
    assert tx.currency_code == "USD" and tx.payment_type == "card"
    assert tx.user_id == w["admin"].id and tx.branch_id == w["ba2"].id and tx.company_id == w["ca"].id
    mv = db.query(KassaMovement).filter(KassaMovement.wallet_id == w["wa2"].id).one()
    assert mv.currency == "USD" and mv.direction == "in" and mv.payment_type == "card" and mv.session_id
    db.refresh(w["wa2"])
    assert float(w["wa2"].balance) == 0          # valyutali kirim Wallet.balance ni o'zgartirmaydi


def test_other_income_uzs_increases_balance_and_foreign_wallet_404(db, client, w):
    cl_ = client.login(w["admin"])
    r = cl_.post("/api/finance/transactions", json={
        "type": "income", "amount": 2000000, "wallet_id": w["wa"].id, "reference_type": "other_income"})
    assert r.status_code == 201, r.text
    db.refresh(w["wa"])
    assert float(w["wa"].balance) == 2000000
    tx = db.get(Transaction, r.json()["id"])
    assert tx.currency_code == "UZS" and tx.payment_type == "cash" and tx.branch_id == w["ba"].id
    r = cl_.post("/api/finance/transactions", json={
        "type": "income", "amount": 5, "wallet_id": w["wb"].id, "reference_type": "other_income"})
    assert r.status_code == 404


# ── 4. Kirim/Chiqim to'lovlari: filtrlar va jamlar ───────────────────────────

def _seed_income(db, w):
    _tx(db, w["ca"], w["ba"], w["wa"], "income", 1000, currency="USD", ref="other_income")
    _tx(db, w["ca"], w["ba"], w["wa"], "income", 50000, ref="sale", ref_id=1)
    _tx(db, w["ca"], w["ba2"], w["wa2"], "income", 7000, ptype="card", ref="sale", ref_id=2)
    _tx(db, w["cb"], w["bb"], w["wb"], "income", 999, ref="sale", ref_id=3)


def test_income_summary_does_not_mix_currencies(db, client, w):
    _seed_income(db, w)
    body = client.login(w["admin"]).get("/api/finance/payments/income").json()
    assert body["total"] == 3
    sbc = body["summary_by_currency"]
    assert sbc["USD"]["umumiy"] == 1000 and sbc["UZS"]["umumiy"] == 57000
    # umumiy: 1000 USD kurs bo'yicha so'mga aylanadi (1000 so'm bo'lib qo'shilmaydi)
    assert body["summary"]["umumiy"] == 1000 * 12000 + 57000
    spt = body["summary_by_payment_type"]
    assert spt["cash"]["by_currency"] == {"USD": 1000.0, "UZS": 50000.0}
    assert spt["card"]["by_currency"] == {"UZS": 7000.0} and spt["card"]["umumiy"] == 7000.0


def test_income_filters_branch_wallet_payment_type_and_names(db, client, w):
    _seed_income(db, w)
    cl_ = client.login(w["admin"])
    b2 = cl_.get("/api/finance/payments/income", params={"branch_id": w["ba2"].id}).json()
    assert b2["total"] == 1 and b2["summary"]["umumiy"] == 7000 and list(b2["summary_by_currency"]) == ["UZS"]
    it = b2["items"][0]
    assert it["branch_id"] == w["ba2"].id and it["branch_name"] == "Ikkinchi filial" and it["wallet_id"] == w["wa2"].id
    assert cl_.get("/api/finance/payments/income", params={"wallet_id": w["wa"].id}).json()["total"] == 2
    cash = cl_.get("/api/finance/payments/income", params={"payment_type": "cash"}).json()
    assert cash["total"] == 2 and cash["summary"]["plastik"] == 0
    # Filialsiz tanlanmasa hamma filial ko'rinadi
    assert cl_.get("/api/finance/payments/income").json()["total"] == 3


def test_income_company_isolation(db, client, w):
    _seed_income(db, w)
    # A foydalanuvchisi B kassasi / B filiali bo'yicha so'rasa hech narsa ko'rmaydi
    cl_ = client.login(w["admin"])
    assert cl_.get("/api/finance/payments/income", params={"wallet_id": w["wb"].id}).json()["total"] == 0
    assert cl_.get("/api/finance/payments/income", params={"branch_id": w["bb"].id}).json()["total"] == 0
    # Ijobiy: B o'z ma'lumotini ko'radi
    b = client.login(w["admin_b"]).get("/api/finance/payments/income").json()
    assert b["total"] == 1 and b["summary"]["umumiy"] == 999


def test_expense_payments_by_currency_branch_and_wallet(db, client, w):
    _tx(db, w["ca"], w["ba"], w["wa"], "expense", 100, ref="expense", ref_id=1)
    _tx(db, w["ca"], w["ba"], w["wa"], "expense", 5, currency="USD", ref="expense", ref_id=2)
    _tx(db, w["ca"], w["ba2"], w["wa2"], "expense", 300, ptype="card", ref="expense", ref_id=3)
    _tx(db, w["cb"], w["bb"], w["wb"], "expense", 777, ref="expense", ref_id=4)
    cl_ = client.login(w["admin"])
    body = cl_.get("/api/finance/payments/expense").json()
    assert body["total"] == 3
    assert body["summary_by_currency"]["USD"]["umumiy"] == 5 and body["summary_by_currency"]["USD"]["xarajat"] == 5
    assert body["summary_by_currency"]["UZS"]["umumiy"] == 400
    assert body["summary"]["umumiy"] == 100 + 5 * 12000 + 300
    assert body["summary_by_payment_type"]["card"]["umumiy"] == 300
    b2 = cl_.get("/api/finance/payments/expense", params={"branch_id": w["ba2"].id}).json()
    assert b2["total"] == 1 and b2["items"][0]["branch_name"] == "Ikkinchi filial"
    assert cl_.get("/api/finance/payments/expense", params={"wallet_id": w["wb"].id}).json()["total"] == 0
    assert cl_.get("/api/finance/payments/expense", params={"payment_type": "card"}).json()["total"] == 1


# ── 5. Kassa ─────────────────────────────────────────────────────────────────

def test_kassa_invest_usd_does_not_change_wallet_balance(db, client, w):
    cl_ = client.login(w["admin"])
    r = cl_.post(f"/api/kassa/{w['wa'].id}/invest", json={"amount": 300, "currency": "USD", "payment_type": "cash"})
    assert r.status_code == 200, r.text
    db.refresh(w["wa"])
    assert float(w["wa"].balance) == 0
    mv = db.query(KassaMovement).filter(KassaMovement.wallet_id == w["wa"].id).one()
    assert mv.currency == "USD" and mv.direction == "in"
    r = cl_.post(f"/api/kassa/{w['wa'].id}/invest", json={"amount": 1000, "currency": "UZS", "payment_type": "cash"})
    assert r.status_code == 200, r.text
    db.refresh(w["wa"])
    assert float(w["wa"].balance) == 1000


def test_kassa_list_has_branch_name_and_isolation(client, w):
    rows = client.login(w["admin"]).get("/api/kassa").json()
    items = rows if isinstance(rows, list) else rows.get("items", rows)
    by_name = {k["name"]: k for k in items}
    assert by_name["A2 kassa"]["branch_name"] == "Ikkinchi filial"
    assert "B kassa" not in by_name


# ── 6. Mijoz qarzi to'lovi: tanlangan kassa va to'lov turi ───────────────────

def test_customer_debt_payment_uses_chosen_wallet_and_payment_type(db, client, w):
    c = Customer(name="Qarzdor", phone=f"9977{next(_seq):07d}", company_id=w["ca"].id, branch_id=w["ba"].id)
    db.add(c)
    db.flush()
    cl.add_debt(db, c, currency="UZS", amount=Decimal("50000"), kind="sale", user=w["admin"], sale=None)
    db.flush()
    r = client.login(w["admin"]).post(f"/api/finance/customer-debts/{c.id}/pay", json={
        "amount": 20000, "currency": "UZS", "wallet_id": w["wa"].id, "payment_type": "card"})
    assert r.status_code == 200, r.text
    mv = db.query(KassaMovement).filter(KassaMovement.wallet_id == w["wa"].id).one()
    assert mv.payment_type == "card" and mv.direction == "in"
    tx = db.get(Transaction, r.json()["transaction_ids"][0])
    assert tx.wallet_id == w["wa"].id and tx.payment_type == "card" and tx.user_id == w["admin"].id
    # Begona korxona kassasi bilan to'lov bo'lmaydi
    r = client.login(w["admin"]).post(f"/api/finance/customer-debts/{c.id}/pay", json={
        "amount": 1000, "wallet_id": w["wb"].id})
    assert r.status_code == 404


# ── 7. Frontend (fayl-matn) va i18n ──────────────────────────────────────────

def _read(name):
    return (ADMIN_JSX / name).read_text(encoding="utf-8")


def test_finance_jsx_expense_form():
    src = _read("Finance.jsx")
    assert "branch_id: 1" not in src
    assert "BLANK_EXPENSE" in src and "buildExpensePayload" in src
    assert "setForm({ ...BLANK_EXPENSE" in src
    assert "finance.mainCashbox" not in src          # "(Asosiy kassa)" varianti olib tashlangan
    assert "finance.selectWallet" in src and "finance.createWalletFirst" in src
    assert "wallet_id: form.wallet_id ? Number(form.wallet_id) : null" in src
    # mijoz qarzi to'lovida ham kassa va to'lov turi yuboriladi
    assert re.search(r"payModal\.type === 'supplier' \|\| payModal\.type === 'customer'", src)
    assert "body.wallet_id" not in src and "payment_type: payType" in src


def test_other_pages_frontend():
    kirim = _read("KirimTolovlar.jsx")
    assert re.search(r"branch_id:\s*txBranch", kirim) or "txBranch" in kirim
    assert "summary_by_currency" in kirim and "summary_by_currency" in _read("ChiqimTolovlar.jsx")
    kassa = _read("Kassa.jsx")
    assert "currency: form.currency ?? 'UZS'" in kassa      # ochish
    assert "k.branch_name" in kassa                          # qabul qiluvchilar ro'yxati
    assert kassa.count("<CurrencyField") >= 3                # ochish, invest/withdraw, xarajat
    # ochish modali ham faol valyutalarni yuklashi shart (aks holda CurrencyField chiqmaydi)
    assert "['open', 'expense', 'invest', 'withdraw'].includes(type)" in kassa
    assert kassa.index("['open', 'expense', 'invest', 'withdraw'].includes(type)") < kassa.index("'/currencies/active'")


def test_pending_i18n_keys_same_in_all_langs():
    data = json.loads(PENDING.read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    assert {"finance.selectWallet", "finance.createWalletFirst"} <= set(data["uz"])
    assert all(v.strip() for lang in data.values() for v in lang.values())
