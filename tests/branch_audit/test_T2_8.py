"""T2.8 — Kassa balansi manbalarini birlashtirish va sana/unumdorlik.

Qamrov: `report_utils.date_bounds` (yarim ochiq, Toshkent) va uch sahifada bir xil kun; `cash_service`
(`post_cash`/`reverse_cash` simmetriyasi UZS/USD, debt -> harakat yo'q, sessiya, begona kassa 404);
`wallet_service` (Moliya va Kassa API bir xil qoida: `is_open=False`, yumshoq o'chirish, 409, 404);
`get_kassa_balances_bulk` regressiyasi va `GET /kassa` so'rovlari soni kassa soniga bog'liq emasligi;
`GET /kassa/reconcile`; xarajat yaratish/o'chirish va sotuvni o'chirishda kassa jurnali = kesh;
`/finance/payments/income|expense` jamilari limitdan mustaqil; `X-Total-Count`; `sent_at`;
`/kassa/{id}/history` summary (filtrlar, valyuta bo'yicha); `is_default`; `detailed_balances` yo'q;
i18n pending kalitlari; migratsiya sintaksisi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T2_8.py -q -p no:cacheprovider
"""
import itertools
import json
import os
import py_compile
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.models.currency import Currency
from app.models.moliya import (
    CashTransfer, Expense, ExpenseCategory, KassaMovement, KassaSession, Transaction, Wallet, WalletBalance,
)
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.inventory import StockLevel
from app.models.user import UserRole, UserWallet
from app.routers.kassa import get_kassa_balances, get_kassa_balances_bulk
from app.schemas.sale import SaleCreate
from app.services import cash_service
from app.services.sale_create import create_sale
from app.utils.report_utils import LOCAL_TZ, date_bounds

_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, *, balance=0, is_open=False, session=False, active=True, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=active, is_open=is_open or session)
    db.add(w)
    db.flush()
    if session:
        db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
        db.flush()
    return w


def _km(db, wallet, direction, amount, *, ptype="cash", currency="UZS", ref=None, ref_id=None, created_at=None):
    m = KassaMovement(wallet_id=wallet.id, company_id=wallet.company_id, direction=direction, payment_type=ptype,
                      amount=Decimal(amount), currency=currency, reference_type=ref, reference_id=ref_id)
    if created_at is not None:
        m.created_at = created_at
    db.add(m)
    db.flush()
    return m


def _tx(db, company, branch, wallet, type_, amount, *, ptype="cash", currency="UZS", ref=None, ref_id=None,
        created_at=None, meta=None, user=None):
    t = Transaction(company_id=company.id, branch_id=branch.id, wallet_id=wallet.id if wallet else None, type=type_,
                    amount=Decimal(amount), payment_type=ptype, currency_code=currency, reference_type=ref,
                    reference_id=ref_id, meta=meta, user_id=user.id if user else None)
    if created_at is not None:
        t.created_at = created_at
    db.add(t)
    db.flush()
    return t


def _category(db, company, name="Ijara"):
    c = ExpenseCategory(name=name, company_id=company.id)
    db.add(c)
    db.flush()
    return c


def _bal(db, wallet):
    db.expire(wallet)
    return Decimal(str(wallet.balance or 0))


def _ledger_uzs(db, wallet):
    total = Decimal("0")
    for m in db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet.id, KassaMovement.currency == "UZS"):
        total += Decimal(str(m.amount)) if m.direction == "in" else -Decimal(str(m.amount))
    return total


def _product(db, company, wh, qty=10):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T28-{n}", barcode=f"B28-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty), variant_id=None))
    db.flush()
    return p


class _Counter:
    """`before_cursor_execute` bilan SQL so'rovlarni sanaydi (SELECT/INSERT/UPDATE/DELETE hammasi)."""

    def __init__(self, bind):
        self.bind = bind
        self.n = 0

    def _on(self, conn, cursor, statement, params, context, executemany):
        s = statement.lstrip().upper()
        if s.startswith(("SELECT", "INSERT", "UPDATE", "DELETE")):
            self.n += 1

    def __enter__(self):
        event.listen(self.bind, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(self.bind, "before_cursor_execute", self._on)


@pytest.fixture
def w(db, mk):
    """Korxona A (admin, kassir, filial, ombor, kassa) va korxona B (admin, kassa)."""
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba)
    wallet = _wallet(db, ca, ba, balance=0, session=True, name="Asosiy")
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    wallet_b = _wallet(db, cb, bb, balance=0, session=True, name="B kassa")
    db.add(ExpenseCategory(name="Ijara", company_id=ca.id))
    db.flush()
    return dict(ca=ca, ba=ba, wha=wha, admin=admin, cashier=cashier, wallet=wallet,
                cb=cb, bb=bb, admin_b=admin_b, wallet_b=wallet_b)


# ── 1. date_bounds ───────────────────────────────────────────────────────────

def test_date_bounds_half_open_tashkent():
    start, end = date_bounds("2026-10-14", "2026-10-14")
    assert start == datetime(2026, 10, 14, tzinfo=LOCAL_TZ)
    assert end == datetime(2026, 10, 15, tzinfo=LOCAL_TZ)
    assert start.utcoffset() == timedelta(hours=5)          # tz-aware, Toshkent (UTC+5)
    # 00:00 ichkarida, 23:59:59.999999 ichkarida, ertasi kun 00:00 tashqarida (yarim ochiq)
    assert start <= datetime(2026, 10, 14, 0, 0, tzinfo=LOCAL_TZ) < end
    assert start <= datetime(2026, 10, 14, 23, 59, 59, 999999, tzinfo=LOCAL_TZ) < end
    assert not (datetime(2026, 10, 15, 0, 0, tzinfo=LOCAL_TZ) < end)
    assert not (datetime(2026, 10, 13, 23, 59, 59, 999999, tzinfo=LOCAL_TZ) >= start)
    # str, date va datetime bir xil natija beradi
    assert date_bounds(date(2026, 10, 14), date(2026, 10, 14)) == (start, end)
    assert date_bounds(datetime(2026, 10, 14, 15, 0), datetime(2026, 10, 14, 1, 0)) == (start, end)


def test_date_bounds_month_year_end_and_open_ranges():
    _, end = date_bounds("2026-12-31", "2026-12-31")
    assert end == datetime(2027, 1, 1, tzinfo=LOCAL_TZ)
    _, end = date_bounds("2028-02-28", "2028-02-28")          # kabisa yil
    assert end == datetime(2028, 2, 29, tzinfo=LOCAL_TZ)
    start, end = date_bounds(None, None)
    assert start < datetime(2026, 1, 1, tzinfo=LOCAL_TZ) < end
    start, end = date_bounds("2026-10-14", None)
    assert start == datetime(2026, 10, 14, tzinfo=LOCAL_TZ) and end.year >= 2100
    start, end = date_bounds("", "")
    assert start < end


def test_date_bounds_invalid_string_is_400():
    with pytest.raises(HTTPException) as ei:
        date_bounds("14.10.2026", None)
    assert ei.value.status_code == 400


def test_finance_parse_helpers_use_date_bounds():
    from app.routers.finance import _parse_dt_end, _parse_dt_start
    assert _parse_dt_start("2026-10-14") == datetime(2026, 10, 14, tzinfo=LOCAL_TZ)
    assert _parse_dt_end("2026-10-14") == datetime(2026, 10, 15, tzinfo=LOCAL_TZ)


def test_same_day_in_income_history_and_cashier_report(db, client, w):
    """date_from=date_to bir kun: 02:30 (Toshkent) dagi yozuv Moliya, Kassa tarixi va Hisobotlarda bitta kunda."""
    day = datetime(2026, 10, 14, 2, 30)
    _tx(db, w["ca"], w["ba"], w["wallet"], "income", 700, ref="other_income", created_at=day)
    _km(db, w["wallet"], "in", 700, ref="other_income", created_at=day)
    # bir daqiqa oldingi kun oxiri va ertasi kun yarim tuni — chegaradan tashqarida
    _tx(db, w["ca"], w["ba"], w["wallet"], "income", 5, ref="other_income", created_at=datetime(2026, 10, 13, 23, 59, 59))
    _tx(db, w["ca"], w["ba"], w["wallet"], "income", 6, ref="other_income", created_at=datetime(2026, 10, 15, 0, 0, 0))
    _km(db, w["wallet"], "in", 5, ref="other_income", created_at=datetime(2026, 10, 13, 23, 59, 59))
    _km(db, w["wallet"], "in", 6, ref="other_income", created_at=datetime(2026, 10, 15, 0, 0, 0))
    sale = Sale(number="S2800001", cashier_id=w["admin"].id, company_id=w["ca"].id, warehouse_id=w["wha"].id,
                total_amount=Decimal("900"), paid_amount=Decimal("900"), payment_type=PaymentType.cash,
                status=SaleStatus.completed)
    sale.created_at = day
    db.add(sale)
    db.flush()
    cl = client.login(w["admin"])

    r = cl.get("/api/finance/payments/income", params={"date_from": "2026-10-14", "date_to": "2026-10-14"})
    assert r.status_code == 200, r.text
    assert [i["amount"] for i in r.json()["items"]] == [700.0]
    assert r.json()["summary"]["umumiy"] == 700.0

    r = cl.get(f"/api/kassa/{w['wallet'].id}/history", params={"date_from": "2026-10-14", "date_to": "2026-10-14"})
    assert r.status_code == 200, r.text
    assert [m["amount"] for m in r.json()["items"]] == [700.0]

    r = cl.get("/api/reports/cashier-report", params={"date_from": "2026-10-14", "date_to": "2026-10-14"})
    assert r.status_code == 200, r.text
    assert sum(e["sales_count"] for e in r.json()) == 1

    # Kechasi yarim tungacha: 23:59:59.999999 ham shu kunda
    late = datetime(2026, 10, 14, 23, 59, 59, 999999)
    _km(db, w["wallet"], "in", 11, ref="other_income", created_at=late)
    r = cl.get(f"/api/kassa/{w['wallet'].id}/history", params={"date_from": "2026-10-14", "date_to": "2026-10-14"})
    assert sorted(m["amount"] for m in r.json()["items"]) == [11.0, 700.0]


# ── 2. cash_service ──────────────────────────────────────────────────────────

def test_post_cash_reverse_cash_symmetry_uzs_and_usd(db, w):
    wallet, admin, branch = w["wallet"], w["admin"], w["ba"]
    kw = dict(user=admin, wallet=wallet, payment_type="cash", branch_id=branch.id)
    tx_uzs = cash_service.post_cash(db, direction="in", amount=1000, currency="UZS", reference_type="other_income",
                                    reference_id=7, description="UZS kirim", **kw)
    tx_usd = cash_service.post_cash(db, direction="in", amount=50, currency="USD", reference_type="other_income",
                                    reference_id=8, description="USD kirim", **kw)
    tx_out = cash_service.post_cash(db, direction="out", amount=300, currency="UZS", reference_type="other_expense",
                                    reference_id=9, description="UZS chiqim", **kw)
    # Wallet.balance faqat UZS; USD faqat jurnalda
    assert _bal(db, wallet) == Decimal("700")
    assert _ledger_uzs(db, wallet) == Decimal("700")
    assert db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet.id).count() == 3
    assert tx_uzs.type == "income" and tx_out.type == "expense"
    assert tx_uzs.company_id == w["ca"].id and tx_uzs.user_id == admin.id and tx_uzs.branch_id == branch.id
    assert tx_usd.currency_code == "USD"

    # Standart reverse_cash: hamyon, harakat va tranzaksiya o'chadi
    cash_service.reverse_cash(db, tx_out)
    db.flush()
    assert _bal(db, wallet) == Decimal("1000") and _ledger_uzs(db, wallet) == Decimal("1000")
    cash_service.reverse_cash(db, tx_usd)
    db.flush()
    assert _bal(db, wallet) == Decimal("1000")                       # USD balansga tegmagan edi
    assert db.query(KassaMovement).filter(KassaMovement.currency == "USD", KassaMovement.wallet_id == wallet.id).count() == 0
    cash_service.reverse_cash(db, tx_uzs)
    db.flush()
    assert _bal(db, wallet) == Decimal("0") and _ledger_uzs(db, wallet) == Decimal("0")
    assert db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet.id).count() == 0
    assert db.query(Transaction).filter(Transaction.wallet_id == wallet.id).count() == 0


def test_reverse_cash_void_keeps_history_and_balances(db, w):
    wallet, admin = w["wallet"], w["admin"]
    tx = cash_service.post_cash(db, user=admin, wallet=wallet, direction="out", amount=250, currency="UZS",
                                payment_type="cash", reference_type="other_expense", reference_id=5,
                                description="x", branch_id=w["ba"].id)
    assert _bal(db, wallet) == Decimal("-250")
    cash_service.reverse_cash(db, tx, user=admin, void=True, reference_type="transaction_void", reference_id=tx.id)
    db.flush()
    assert tx.voided_at is not None and tx.voided_by == admin.id
    assert _bal(db, wallet) == Decimal("0") and _ledger_uzs(db, wallet) == Decimal("0")
    mvs = db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet.id).order_by(KassaMovement.id).all()
    assert [(m.direction, m.reference_type) for m in mvs] == [("out", "other_expense"), ("in", "transaction_void")]
    counter = db.query(Transaction).filter(Transaction.reference_type == "transaction_void").one()
    assert counter.type == "income" and counter.voided_at is not None
    # Hisobotlarda ko'rinadigan (voided emas) yozuv qolmadi
    assert db.query(Transaction).filter(Transaction.wallet_id == wallet.id, Transaction.voided_at.is_(None)).count() == 0


@pytest.mark.parametrize("ptype", ["debt", "cashback"])
def test_post_cash_debt_and_cashback_write_no_movement(db, w, ptype):
    wallet = w["wallet"]
    tx = cash_service.post_cash(db, user=w["admin"], wallet=wallet, direction="in", amount=400, currency="UZS",
                                payment_type=ptype, reference_type="other_income", reference_id=1,
                                branch_id=w["ba"].id)
    assert tx.id is not None
    assert db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet.id).count() == 0
    assert _bal(db, wallet) == Decimal("0")
    cash_service.reverse_cash(db, tx)       # balans o'zgarmaydi (qarz/keshbek pul emas)
    db.flush()
    assert _bal(db, wallet) == Decimal("0")


def test_post_cash_binds_open_session_and_no_transaction_mode(db, w):
    wallet = w["wallet"]
    session = db.query(KassaSession).filter(KassaSession.wallet_id == wallet.id).one()
    mv = cash_service.post_cash(db, user=w["admin"], wallet=wallet, direction="in", amount=100, currency="UZS",
                                payment_type="cash", reference_type="invest", description="Invest",
                                with_transaction=False)
    assert isinstance(mv, KassaMovement) and mv.session_id == session.id
    assert db.query(Transaction).count() == 0                        # investitsiya P&L ga kirmaydi
    assert _bal(db, wallet) == Decimal("100")
    # Sessiya yopilsa — session_id bo'sh
    session.status = "closed"
    db.flush()
    mv2 = cash_service.post_cash(db, user=w["admin"], wallet=wallet, direction="in", amount=5, currency="UZS",
                                 payment_type="cash", reference_type="invest", with_transaction=False)
    assert mv2.session_id is None


def test_post_cash_foreign_wallet_404_and_validation(db, w):
    with pytest.raises(HTTPException) as ei:
        cash_service.post_cash(db, user=w["admin"], wallet=w["wallet_b"], direction="in", amount=10,
                               currency="UZS", payment_type="cash", branch_id=w["ba"].id)
    assert ei.value.status_code == 404
    assert _bal(db, w["wallet_b"]) == Decimal("0")
    for bad in (dict(direction="sideways", amount=10), dict(direction="in", amount=0)):
        with pytest.raises(HTTPException) as ei:
            cash_service.post_cash(db, user=w["admin"], wallet=w["wallet"], currency="UZS", payment_type="cash",
                                   branch_id=w["ba"].id, **bad)
        assert ei.value.status_code == 400
    # Kassasiz yozuv: faqat Transaction
    tx = cash_service.post_cash(db, user=w["admin"], wallet=None, direction="out", amount=10, currency="UZS",
                                payment_type="cash", reference_type="other_expense", branch_id=w["ba"].id)
    assert tx.wallet_id is None and db.query(KassaMovement).count() == 0


def test_find_kassa_movement_matches_amount_and_wallet(db, w):
    wallet, admin = w["wallet"], w["admin"]
    tx1 = cash_service.post_cash(db, user=admin, wallet=wallet, direction="out", amount=100, currency="UZS",
                                 payment_type="cash", reference_type="supplier_payment", reference_id=3,
                                 branch_id=w["ba"].id)
    tx2 = cash_service.post_cash(db, user=admin, wallet=wallet, direction="out", amount=200, currency="UZS",
                                 payment_type="cash", reference_type="supplier_payment", reference_id=3,
                                 branch_id=w["ba"].id)
    assert Decimal(str(cash_service.find_kassa_movement(db, tx1).amount)) == Decimal("100")
    assert Decimal(str(cash_service.find_kassa_movement(db, tx2).amount)) == Decimal("200")
    # Havolasiz: harakat tranzaksiyaning o'zi bilan bog'langan
    tx3 = cash_service.post_cash(db, user=admin, wallet=wallet, direction="in", amount=50, currency="UZS",
                                 payment_type="cash", reference_type=None, reference_id=None,
                                 branch_id=w["ba"].id, link_movement_to_tx=True)
    mv3 = cash_service.find_kassa_movement(db, tx3)
    assert mv3 is not None and mv3.reference_type == "transaction" and mv3.reference_id == tx3.id
    assert tx3.reference_id is None


# ── 3. Kassa CRUD: ikki API bir xil qoida ────────────────────────────────────

def test_finance_created_wallet_is_closed_and_openable_from_kassa(db, client, w):
    cl = client.login(w["admin"])
    r = cl.post("/api/finance/wallets", json={"name": "Bank hisobi", "type": "bank", "branch_id": w["ba"].id})
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    row = db.get(Wallet, wid)
    assert row.is_open is False and row.company_id == w["ca"].id
    assert db.query(KassaSession).filter(KassaSession.wallet_id == wid).count() == 0
    r = cl.post(f"/api/kassa/{wid}/open", json={"opening_balance": 0})
    assert r.status_code == 200, r.text
    assert db.query(KassaSession).filter(KassaSession.wallet_id == wid, KassaSession.status == "open").count() == 1
    # Kassa API ham xuddi shunday yopiq kassa yaratadi
    r = cl.post("/api/kassa", json={"name": "Yana", "branch_id": w["ba"].id, "opening_balance": 5000})
    assert r.status_code == 200, r.text
    k = db.get(Wallet, r.json()["id"])
    assert k.is_open is False and _bal(db, k) == Decimal("5000") and _ledger_uzs(db, k) == Decimal("5000")


def test_create_wallet_foreign_branch_rejected_in_both_apis(db, client, w):
    cl = client.login(w["admin"])
    before = db.query(Wallet).count()
    r = cl.post("/api/finance/wallets", json={"name": "X", "branch_id": w["bb"].id})
    assert r.status_code == 400
    r = cl.post("/api/kassa", json={"name": "X", "branch_id": w["bb"].id})
    assert r.status_code == 400
    assert db.query(Wallet).count() == before


@pytest.mark.parametrize("path,ok_status", [("finance/wallets", 204), ("kassa", 200)])
def test_delete_wallet_soft_delete_and_conflicts(db, client, w, path, ok_status):
    cl = client.login(w["admin"])
    # 409: ochiq sessiya
    with_session = _wallet(db, w["ca"], w["ba"], balance=0, session=True)
    r = cl.delete(f"/api/{path}/{with_session.id}")
    assert r.status_code == 409, r.text
    assert "ochiq sessiya" in r.json()["detail"] and db.get(Wallet, with_session.id).is_active is True
    # 409: kutilayotgan o'tkazma
    a = _wallet(db, w["ca"], w["ba"], balance=0)
    b = _wallet(db, w["ca"], w["ba"], balance=0)
    db.add(CashTransfer(company_id=w["ca"].id, sender_wallet_id=a.id, receiver_wallet_id=b.id, amount=Decimal("10"),
                        currency="UZS", payment_type="cash", status="pending", sent_by=w["admin"].id))
    db.flush()
    for target in (a, b):
        r = cl.delete(f"/api/{path}/{target.id}")
        assert r.status_code == 409, r.text
    # 409: qoldiq bor
    rich = _wallet(db, w["ca"], w["ba"], balance=500)
    r = cl.delete(f"/api/{path}/{rich.id}")
    assert r.status_code == 409, r.text
    assert db.get(Wallet, rich.id).is_active is True
    # Yumshoq o'chirish: qator va harakatlar qoladi, xodimga biriktirish tozalanadi
    clean = _wallet(db, w["ca"], w["ba"], balance=0)
    _km(db, clean, "in", 100)
    _km(db, clean, "out", 100)
    db.add(UserWallet(user_id=w["cashier"].id, wallet_id=clean.id, is_default=True))
    db.flush()
    r = cl.delete(f"/api/{path}/{clean.id}")
    assert r.status_code == ok_status, r.text
    row = db.get(Wallet, clean.id)
    assert row is not None and row.is_active is False
    assert db.query(KassaMovement).filter(KassaMovement.wallet_id == clean.id).count() == 2
    assert db.query(UserWallet).filter(UserWallet.wallet_id == clean.id).count() == 0
    # Takroriy o'chirish xato bermaydi
    assert cl.delete(f"/api/{path}/{clean.id}").status_code == ok_status


@pytest.mark.parametrize("path", ["finance/wallets", "kassa"])
def test_delete_foreign_wallet_404(db, client, w, path):
    r = client.login(w["admin"]).delete(f"/api/{path}/{w['wallet_b'].id}")
    assert r.status_code == 404
    assert db.get(Wallet, w["wallet_b"].id).is_active is True


def test_finance_wallets_list_default_order_and_no_detailed_balances(db, client, w):
    first = _wallet(db, w["ca"], w["ba"], name="Birinchi")
    inactive = _wallet(db, w["ca"], w["ba"], name="Nofaol", active=False)
    last = _wallet(db, w["ca"], w["ba"], name="Oxirgi")
    db.add(UserWallet(user_id=w["admin"].id, wallet_id=last.id, is_default=True))
    db.flush()
    cl = client.login(w["admin"])
    rows = cl.get("/api/finance/wallets").json()
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids)                                    # id bo'yicha tartiblangan
    assert inactive.id not in ids and w["wallet_b"].id not in ids  # nofaol va begona korxona yo'q
    by_id = {r["id"]: r for r in rows}
    assert by_id[last.id]["is_default"] is True
    assert by_id[first.id]["is_default"] is False
    assert all("detailed_balances" not in r for r in rows)
    assert "balance" in by_id[first.id]
    assert inactive.id in [r["id"] for r in cl.get("/api/finance/wallets", params={"include_inactive": "true"}).json()]
    # /kassa ro'yxati ham is_default beradi
    k = {r["id"]: r for r in cl.get("/api/kassa").json()}
    assert k[last.id]["is_default"] is True and k[first.id]["is_default"] is False


def test_super_admin_finance_wallets_scoped_to_own_company(db, client, mk, w):
    sa = mk.user(w["ca"], role=UserRole.super_admin)
    ids = {r["id"] for r in client.login(sa).get("/api/finance/wallets").json()}
    assert w["wallet"].id in ids and w["wallet_b"].id not in ids


def test_shift_handover_wallets_mark_default(db, client, w):
    other = _wallet(db, w["ca"], w["ba"], name="Boshqa")
    db.add(UserWallet(user_id=w["cashier"].id, wallet_id=other.id, is_default=True))
    db.flush()
    rows = client.login(w["cashier"]).get("/api/shifts/handover-wallets").json()
    by_id = {r["id"]: r for r in rows}
    assert by_id[other.id]["is_default"] is True
    assert by_id[w["wallet"].id]["is_default"] is False


# ── 4. Bulk balans ───────────────────────────────────────────────────────────

def _seed(db, wallet):
    _km(db, wallet, "in", 1000, ptype="cash")
    _km(db, wallet, "out", 300, ptype="cash")
    _km(db, wallet, "in", 50, ptype="cash", currency="USD")
    _km(db, wallet, "in", 700, ptype="card")
    _km(db, wallet, "in", 40, ptype="weird_type")
    _km(db, wallet, "in", 10, ptype="click", currency="UZS")
    _km(db, wallet, "out", 10, ptype="click", currency="UZS")      # nolga tushgan tur ko'rinmaydi


def _legacy_balances(db, wallet_id):
    """Eski usul: Python'da qatorma-qator yig'ish (regressiya etaloni)."""
    acc = {}
    for m in db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet_id).all():
        sign = 1 if m.direction == "in" else -1
        acc.setdefault(m.payment_type, {})
        acc[m.payment_type][m.currency] = acc[m.payment_type].get(m.currency, 0.0) + sign * float(m.amount)
    out = {}
    for ptype, cm in acc.items():
        nonzero = {c: v for c, v in cm.items() if v != 0}
        if nonzero:
            out[ptype] = nonzero
    return out


def _norm(bal):
    return {p: {x["currency"]: x["value"] for x in lst} for p, lst in bal.items() if p != "total" and lst}


def test_bulk_balances_equal_single_and_legacy(db, w):
    other = _wallet(db, w["ca"], w["ba"])
    empty = _wallet(db, w["ca"], w["ba"])
    _seed(db, w["wallet"])
    _km(db, other, "in", 5, ptype="humo")
    bulk = get_kassa_balances_bulk(db, [w["wallet"].id, other.id, empty.id])
    assert set(bulk) == {w["wallet"].id, other.id, empty.id}
    for wid in bulk:
        assert _norm(bulk[wid]) == _norm(get_kassa_balances(wid, db)) == _legacy_balances(db, wid)
    assert _norm(bulk[w["wallet"].id])["cash"] == {"UZS": 700.0, "USD": 50.0}
    assert _norm(bulk[w["wallet"].id])["weird_type"] == {"UZS": 40.0}
    assert "click" in bulk[w["wallet"].id] and bulk[w["wallet"].id]["click"] == []
    assert bulk[empty.id]["total"] == [] and bulk[other.id]["total"] == [{"currency": "UZS", "value": 5.0}]
    total = {x["currency"]: x["value"] for x in bulk[w["wallet"].id]["total"]}
    assert total == {"UZS": 1440.0, "USD": 50.0}
    assert get_kassa_balances_bulk(db, []) == {}


def test_bulk_balances_single_select_for_many_wallets(db, w):
    wallets = [_wallet(db, w["ca"], w["ba"]) for _ in range(20)]
    for wl in wallets:
        _seed(db, wl)
    with _Counter(db.get_bind()) as c:
        get_kassa_balances_bulk(db, [x.id for x in wallets])
    assert c.n == 1


def test_get_kassa_list_query_count_independent_of_wallet_count(db, client, w):
    cl = client.login(w["admin"])

    def _count():
        with _Counter(db.get_bind()) as c:
            r = cl.get("/api/kassa")
        assert r.status_code == 200, r.text
        return c.n, len(r.json())

    for _ in range(3):
        _seed(db, _wallet(db, w["ca"], w["ba"], session=True))
    n_small, len_small = _count()
    for _ in range(17):
        _seed(db, _wallet(db, w["ca"], w["ba"], session=True))
    n_big, len_big = _count()
    assert len_big - len_small == 17 and len_big >= 20
    assert n_big == n_small                    # kassa soniga bog'liq emas
    assert n_big <= 6                          # ro'yxat, meta, bitta balans va bitta sessiya so'rovi
    rows = cl.get("/api/kassa").json()
    assert all(r["session_id"] is not None for r in rows if r["id"] != w["wallet_b"].id)
    sample = rows[-1]
    assert _norm(sample["balances"]) == _norm(get_kassa_balances(sample["id"], db))


# ── 5. Kesh = jurnal: reconcile, xarajat, sotuv ──────────────────────────────

def _reconcile(client, user, **params):
    r = client.login(user).get("/api/kassa/reconcile", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_reconcile_zero_diff_and_detects_drift(db, client, w):
    cl = client.login(w["admin"])
    wallet = w["wallet"]
    cash_service.post_cash(db, user=w["admin"], wallet=wallet, direction="in", amount=900, currency="UZS",
                           payment_type="cash", reference_type="other_income", branch_id=w["ba"].id)
    cash_service.post_cash(db, user=w["admin"], wallet=wallet, direction="in", amount=40, currency="USD",
                           payment_type="cash", reference_type="other_income", branch_id=w["ba"].id)
    data = _reconcile(client, w["admin"])
    row = next(i for i in data["items"] if i["wallet_id"] == wallet.id)
    assert row == {**row, "cached": 900.0, "ledger": 900.0, "diff": 0.0}
    assert data["mismatched"] == 0
    # Kesh jurnaldan chetga chiqsa — diff ko'rinadi
    wallet.balance = Decimal("905")
    db.flush()
    data = _reconcile(client, w["admin"])
    row = next(i for i in data["items"] if i["wallet_id"] == wallet.id)
    assert row["diff"] == 5.0 and data["mismatched"] == 1
    # Ikki korxona izolyatsiyasi
    other_ids = {i["wallet_id"] for i in _reconcile(client, w["admin_b"])["items"]}
    assert w["wallet_b"].id in other_ids and wallet.id not in other_ids
    # Kassir (rol) reconcile'ni ko'ra olmaydi
    assert client.login(w["cashier"]).get("/api/kassa/reconcile").status_code == 403


def test_finance_expense_create_and_delete_keeps_journal_and_cache_equal(db, client, w):
    cl = client.login(w["admin"])
    wallet = w["wallet"]
    wallet.balance = Decimal("5000")
    _km(db, wallet, "in", 5000, ref="opening")
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.company_id == w["ca"].id).first()
    r = cl.post("/api/finance/expenses", json={"category_id": cat.id, "amount": 1200, "wallet_id": wallet.id,
                                               "description": "Ijara"})
    assert r.status_code == 201, r.text
    exp_id = r.json()["id"]
    assert _bal(db, wallet) == Decimal("3800") and _ledger_uzs(db, wallet) == Decimal("3800")
    tx = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == exp_id).one()
    assert tx.company_id == w["ca"].id and tx.user_id == w["admin"].id and tx.branch_id == w["ba"].id
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "expense",
                                        KassaMovement.reference_id == exp_id).one()
    assert mv.direction == "out" and mv.session_id is not None and mv.wallet_id == wallet.id
    assert all(i["diff"] == 0 for i in _reconcile(client, w["admin"])["items"])

    assert cl.delete(f"/api/finance/expenses/{exp_id}").status_code == 204
    assert _bal(db, wallet) == Decimal("5000") and _ledger_uzs(db, wallet) == Decimal("5000")
    db.refresh(tx)
    assert tx.voided_at is not None                             # Transaction topildi va bekor qilindi
    assert db.get(Expense, exp_id).voided_at is not None
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == "expense_void",
                                          KassaMovement.reference_id == exp_id).count() == 1
    assert all(i["diff"] == 0 for i in _reconcile(client, w["admin"])["items"])
    assert db.query(WalletBalance).count() == 0                 # WalletBalance'ga yozuv tushmaydi


def test_finance_manual_transaction_and_delete_keeps_journal_and_cache_equal(db, client, w):
    cl = client.login(w["admin"])
    wallet = w["wallet"]
    r = cl.post("/api/finance/transactions", json={"type": "income", "amount": 800, "wallet_id": wallet.id,
                                                   "reference_type": "other_income", "description": "Boshqa kirim"})
    assert r.status_code == 201, r.text
    tx_id = r.json()["id"]
    r = cl.post("/api/finance/transactions", json={"type": "expense", "amount": 150, "wallet_id": wallet.id,
                                                   "currency_code": "USD", "payment_type": "cash"})
    assert r.status_code == 201, r.text
    assert _bal(db, wallet) == Decimal("800") and _ledger_uzs(db, wallet) == Decimal("800")
    mv = db.query(KassaMovement).filter(KassaMovement.reference_id == tx_id).one()
    assert mv.reference_type == "other_income" and mv.session_id is not None
    assert cl.delete(f"/api/finance/transactions/{tx_id}").status_code == 204
    assert _bal(db, wallet) == Decimal("0") and _ledger_uzs(db, wallet) == Decimal("0")
    assert all(i["diff"] == 0 for i in _reconcile(client, w["admin"])["items"])
    # Begona korxona kassasiga yozib bo'lmaydi
    r = cl.post("/api/finance/transactions", json={"type": "income", "amount": 1, "wallet_id": w["wallet_b"].id})
    assert r.status_code == 404


def test_cash_sale_delete_keeps_transaction_journal_and_cache_equal(db, client, w):
    wallet = w["wallet"]
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale = create_sale(db, SaleCreate(
        items=[{"product_id": p.id, "quantity": 1, "unit_price": 1_000_000}], payment_type="cash",
        warehouse_id=w["wha"].id, paid_amount=Decimal("1000000"),
        payments=[{"type": "cash", "amount": Decimal("1000000")}],
    ), w["admin"])
    sale_id = sale.id
    assert _bal(db, wallet) == Decimal("1000000") and _ledger_uzs(db, wallet) == Decimal("1000000")
    assert all(i["diff"] == 0 for i in _reconcile(client, w["admin"])["items"])
    r = client.login(w["admin"]).delete(f"/api/sales/{sale_id}")
    assert r.status_code == 200, r.text
    assert db.query(Transaction).filter(Transaction.reference_type == "sale", Transaction.reference_id == sale_id).count() == 0
    assert _bal(db, wallet) == Decimal("0") and _ledger_uzs(db, wallet) == Decimal("0")
    assert all(i["diff"] == 0 for i in _reconcile(client, w["admin"])["items"])
    assert db.query(WalletBalance).count() == 0


def test_kassa_invest_withdraw_transfer_keep_cache_equal_to_journal(db, client, w):
    cl = client.login(w["admin"])
    a, b = w["wallet"], _wallet(db, w["ca"], w["ba"], session=True, name="Ikkinchi")
    assert cl.post(f"/api/kassa/{a.id}/invest", json={"amount": 1000}).status_code == 200
    assert cl.post(f"/api/kassa/{a.id}/withdraw", json={"amount": 200}).status_code == 200
    assert cl.post(f"/api/kassa/{a.id}/invest", json={"amount": 20, "currency": "USD"}).status_code == 200
    r = cl.post(f"/api/kassa/{a.id}/transfer/out", json={"receiver_wallet_id": b.id, "amount": 300})
    assert r.status_code == 200, r.text
    tid = r.json()["transfer_id"]
    assert _bal(db, a) == Decimal("500") and _bal(db, b) == Decimal("0")
    assert cl.post("/api/kassa/transfer/in", json={"transfer_id": tid}).status_code == 200
    assert _bal(db, b) == Decimal("300")
    r = cl.post(f"/api/kassa/{a.id}/transfer/out", json={"receiver_wallet_id": b.id, "amount": 100})
    assert cl.post("/api/kassa/transfer/reject", json={"transfer_id": r.json()["transfer_id"]}).status_code == 200
    assert _bal(db, a) == Decimal("500")
    # Invest/withdraw/transfer Transaction yozmaydi (P&L ga kirmaydi)
    assert db.query(Transaction).filter(Transaction.wallet_id.in_([a.id, b.id])).count() == 0
    assert all(i["diff"] == 0 for i in _reconcile(client, w["admin"])["items"])


# ── 6. To'lovlar hisoboti: summary limitdan mustaqil ─────────────────────────

def test_income_payments_summary_independent_of_limit_3000_rows(db, client, w):
    when = datetime(2026, 9, 10, 12, 0)
    rows = []
    for i in range(3000):
        rows.append(Transaction(company_id=w["ca"].id, branch_id=w["ba"].id, wallet_id=w["wallet"].id, type="income",
                                amount=Decimal("10"), payment_type="cash" if i % 3 else "card", currency_code="UZS",
                                reference_type="other_income", created_at=when))
    db.add_all(rows)
    db.flush()
    cl = client.login(w["admin"])
    r = cl.get("/api/finance/payments/income", params={"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 1000                            # standart sahifa
    assert body["total"] == 3000 and r.headers["x-total-count"] == "3000"
    assert body["summary"]["umumiy"] == 30000.0                  # butun davr jami (avval 10000 edi)
    assert body["summary"]["naqd"] == 20000.0 and body["summary"]["plastik"] == 10000.0
    assert body["summary_by_currency"]["UZS"]["umumiy"] == 30000.0
    small = cl.get("/api/finance/payments/income", params={"date_from": "2026-09-01", "date_to": "2026-09-30",
                                                           "limit": 10, "skip": 20}).json()
    assert len(small["items"]) == 10 and small["summary"] == body["summary"] and small["total"] == 3000
    # Sahifalar kesishmaydi
    first = cl.get("/api/finance/payments/income", params={"limit": 10}).json()["items"]
    nxt = cl.get("/api/finance/payments/income", params={"limit": 10, "skip": 10}).json()["items"]
    assert not ({i["id"] for i in first} & {i["id"] for i in nxt})


def test_income_summary_converts_currencies_and_isolates_companies(db, client, mk, w):
    db.add(Currency(name="USD", code="USD", rate=Decimal("12000"), company_id=w["ca"].id, is_active=True))
    db.flush()
    when = datetime(2026, 9, 10, 12, 0)
    _tx(db, w["ca"], w["ba"], w["wallet"], "income", 100, ref="sale", ref_id=1, created_at=when)
    _tx(db, w["ca"], w["ba"], w["wallet"], "income", 2, ptype="cash", currency="USD", ref="customer_payment",
        ref_id=1, created_at=when)
    _tx(db, w["cb"], w["bb"], w["wallet_b"], "income", 999, ref="sale", ref_id=2, created_at=when)
    body = client.login(w["admin"]).get("/api/finance/payments/income").json()
    assert body["total"] == 2
    assert body["summary"]["umumiy"] == 100 + 2 * 12000
    assert body["summary"]["sotuv_summasi"] == 100 and body["summary"]["mijoz_qarz_yopish"] == 24000
    assert body["summary_by_currency"]["USD"]["umumiy"] == 2 and body["summary_by_currency"]["UZS"]["sotuv"] == 100
    # Korxona B faqat o'zini ko'radi
    b = client.login(w["admin_b"]).get("/api/finance/payments/income").json()
    assert b["summary"]["umumiy"] == 999 and b["total"] == 1


def test_expense_payments_summary_independent_of_limit_and_converts(db, client, w):
    db.add(Currency(name="USD", code="USD", rate=Decimal("10000"), company_id=w["ca"].id, is_active=True))
    db.flush()
    when = datetime(2026, 9, 10, 12, 0)
    for i in range(12):
        _tx(db, w["ca"], w["ba"], w["wallet"], "expense", 100, ref="expense", ref_id=i + 1, created_at=when)
    _tx(db, w["ca"], w["ba"], w["wallet"], "expense", 3, currency="USD", ref="supplier_payment", ref_id=1,
        created_at=when, meta={"allocation": {}})
    # Eski (meta siz), valyutasiz ta'minotchi to'lovi UZS deb hisoblanadi (ta'minotchi topilmasa)
    _tx(db, w["ca"], w["ba"], w["wallet"], "expense", 50, ref="supplier_payment", ref_id=999, created_at=when)
    cl = client.login(w["admin"])
    r = cl.get("/api/finance/payments/expense", params={"limit": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 5 and body["total"] == 14 and r.headers["x-total-count"] == "14"
    s = body["summary"]
    assert s["xarajat"] == 1200.0
    assert s["taminotchi_qarz_yopish"] == 3 * 10000 + 50
    assert s["umumiy"] == 1200 + 30000 + 50 and s["naqd"] == s["umumiy"]
    full = cl.get("/api/finance/payments/expense", params={"limit": 1000}).json()
    assert full["summary"] == s


def test_transactions_and_expenses_pagination_headers(db, client, w):
    cat = db.query(ExpenseCategory).filter(ExpenseCategory.company_id == w["ca"].id).first()
    for i in range(7):
        _tx(db, w["ca"], w["ba"], w["wallet"], "income", 10 + i, ref="other_income")
        db.add(Expense(branch_id=w["ba"].id, category_id=cat.id, amount=Decimal(5 + i), currency="UZS",
                       company_id=w["ca"].id, wallet_id=w["wallet"].id))
    db.flush()
    cl = client.login(w["admin"])
    r = cl.get("/api/finance/transactions", params={"limit": 3, "skip": 2})
    assert r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) == 3
    assert r.headers["x-total-count"] == "7"
    r = cl.get("/api/finance/expenses", params={"limit": 4})
    assert len(r.json()) == 4 and r.headers["x-total-count"] == "7"
    assert len(cl.get("/api/finance/expenses").json()) == 7
    assert cl.get("/api/finance/transactions", params={"limit": 5000}).status_code == 422


# ── 7. Kassa tarixi summary va kutilayotgan o'tkazmalar ──────────────────────

def test_history_summary_follows_filters_and_splits_currencies(db, client, w):
    wallet = w["wallet"]
    d1, d2 = datetime(2026, 10, 14, 10, 0), datetime(2026, 10, 15, 10, 0)
    _km(db, wallet, "in", 1000, ptype="cash", ref="sale", created_at=d1)
    _km(db, wallet, "out", 300, ptype="cash", ref="expense", created_at=d1)
    _km(db, wallet, "in", 200, ptype="card", ref="sale", created_at=d1)
    _km(db, wallet, "in", 50, ptype="cash", currency="USD", ref="invest", created_at=d1)
    _km(db, wallet, "in", 9000, ptype="cash", ref="sale", created_at=d2)
    cl = client.login(w["admin"])
    url = f"/api/kassa/{wallet.id}/history"
    s = cl.get(url).json()["summary"]
    assert s["total_in"] == 10200.0 and s["total_out"] == 300.0 and s["balance"] == 9900.0   # UZS (moslik)
    assert s["UZS"] == {"total_in": 10200.0, "total_out": 300.0, "balance": 9900.0}
    assert s["USD"] == {"total_in": 50.0, "total_out": 0.0, "balance": 50.0}
    s = cl.get(url, params={"date_from": "2026-10-14", "date_to": "2026-10-14"}).json()["summary"]
    assert s["UZS"]["total_in"] == 1200.0 and s["total_out"] == 300.0
    s = cl.get(url, params={"direction": "in", "payment_type": "cash"}).json()["summary"]
    assert s["UZS"] == {"total_in": 10000.0, "total_out": 0.0, "balance": 10000.0}
    s = cl.get(url, params={"reference_type": "expense"}).json()["summary"]
    assert s["UZS"]["total_out"] == 300.0 and s["total_in"] == 0.0 and "USD" not in s
    body = cl.get(url, params={"limit": 2}).json()
    assert body["total"] == 5 and len(body["items"]) == 2
    # Begona korxona kassasi tarixi — 404
    assert cl.get(f"/api/kassa/{w['wallet_b'].id}/history").status_code == 404


def test_pending_transfers_have_sent_at(db, client, w):
    other = _wallet(db, w["ca"], w["ba"], balance=0)
    db.add(CashTransfer(company_id=w["ca"].id, sender_wallet_id=other.id, receiver_wallet_id=w["wallet"].id,
                        amount=Decimal("250"), currency="UZS", payment_type="cash", status="pending",
                        sent_by=w["admin"].id))
    db.flush()
    r = client.login(w["admin"]).get(f"/api/kassa/{w['wallet'].id}/transfers/pending")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["sent_at"] is not None and rows[0]["created_at"] == rows[0]["sent_at"]
    datetime.fromisoformat(rows[0]["sent_at"])
    assert rows[0]["sender_name"] == other.name
    # Begona korxona admini bu o'tkazmani ko'rmaydi
    assert client.login(w["admin_b"]).get(f"/api/kassa/{w['wallet'].id}/transfers/pending").json() == []


# ── 8. Fayllar: i18n va migratsiya ───────────────────────────────────────────

KEYS_T2_8 = ["kassa.defaultForMe", "kassa.sentAt", "kirimTolov.showingCount", "kirimTolov.loadMore"]


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


def test_i18n_pending_keys_same_in_three_languages():
    data = _merged_i18n(KEYS_T2_8)
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    for key in ("kassa.defaultForMe", "kassa.sentAt", "kirimTolov.showingCount", "kirimTolov.loadMore"):
        assert key in data["uz"] and all(data[lang][key] for lang in data)
    # Frontendda ishlatilgan kalitlar pending faylda bor
    kassa = open(os.path.join(ROOT, "frontend", "src", "pages", "admin", "Kassa.jsx"), encoding="utf-8").read()
    kirim = open(os.path.join(ROOT, "frontend", "src", "pages", "admin", "KirimTolovlar.jsx"), encoding="utf-8").read()
    for key in ("kassa.defaultForMe", "kassa.sentAt"):
        assert f"'{key}'" in kassa
    for key in ("kirimTolov.showingCount", "kirimTolov.loadMore"):
        assert f"'{key}'" in kirim


def test_migration_file_syntax_and_contents():
    path = os.path.join(ROOT, "alembic", "versions", "t2_8_cash_indexes.py")
    py_compile.compile(path, doraise=True)
    src = open(path, encoding="utf-8").read()
    assert "revision: str = 't2_8'" in src and "down_revision: Union[str, None] = 't2_7'" in src   # zanjirga ulangan
    for name in ("ix_km_wallet_ptype_cur_dir", "ix_km_reference", "ix_tx_wallet", "ix_expenses_company_created"):
        assert name in src
    assert "CONCURRENTLY IF NOT EXISTS" in src and "autocommit_block" in src
