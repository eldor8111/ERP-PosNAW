"""T0.29 — To'lov turlari va kassa balansi (naqd bo'lmagan to'lovlar).

Qamrov: qarz/keshbek qatorlari pul oqimiga (Transaction) yozilmaydi; eski debt/cashback
Transaction'lar hisobotdan yashiriladi; bank/visa kassa balansi, X-hisobot va yopilishda
ko'rinadi; get_kassa_balances bitta so'rov; mijozdan qarzga qaytarishda Transaction yo'q;
POS har to'lov turini alohida yuboradi; pay-debt yaroqsiz turni rad etadi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T0_29.py -q -p no:cacheprovider
"""
import itertools
from decimal import Decimal

import pytest
from sqlalchemy import event, func

from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.moliya import (
    CASH_PAYMENT_TYPES, NON_CASH_PAYMENT_TYPES, PAYMENT_TYPES,
    KassaMovement, KassaSession, Transaction, Wallet,
)
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SalePayment, SaleStatus
from app.models.user import UserRole
from app.schemas.sale import SaleCreate
from app.services.sale_create import create_sale

_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch, balance=0):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _customer(db, company, debt=0, bonus=0):
    n = next(_seq)
    c = Customer(name=f"Mijoz {n}", company_id=company.id, phone=f"99890{n:07d}",
                 debt_balance=Decimal(debt), debt_balances={"UZS": float(debt)} if debt else {},
                 bonus_balance=Decimal(bonus))
    db.add(c)
    db.flush()
    return c


def _product(db, company, wh, qty=100, cost="500"):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T029-{n}", barcode=f"B029-{n}", company_id=company.id,
                cost_price=Decimal(cost), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


@pytest.fixture
def w(db, mk):
    """Korxona A (admin, kassir, kassa, mijoz, mahsulot) va korxona B (admin, kassa)."""
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba)
    wallet = _wallet(db, ca, ba, 0)
    cust = _customer(db, ca, debt=0, bonus=50000)
    prod = _product(db, ca, wha)
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    wallet_b = _wallet(db, cb, bb, 0)
    return dict(ca=ca, ba=ba, wha=wha, admin=admin, cashier=cashier, wallet=wallet, cust=cust,
                prod=prod, cb=cb, admin_b=admin_b, wallet_b=wallet_b)


def _sale_data(w, price, payments=None, payment_type="mixed", paid_amount=None, **extra):
    body = dict(items=[{"product_id": w['prod'].id, "quantity": 1, "unit_price": price}],
                payment_type=payment_type, warehouse_id=w['wha'].id, customer_id=w['cust'].id)
    if payments is not None:
        body['payments'] = payments
    if paid_amount is None:
        paid_amount = sum((Decimal(str(p['amount'])) for p in (payments or [])
                           if p['type'] not in NON_CASH_PAYMENT_TYPES), Decimal("0"))
    body['paid_amount'] = paid_amount
    body.update(extra)
    return SaleCreate(**body)


def _txs(db, **kw):
    q = db.query(Transaction)
    for k, v in kw.items():
        q = q.filter(getattr(Transaction, k) == v)
    return q.all()


def _kms(db, wallet):
    return db.query(KassaMovement).filter(KassaMovement.wallet_id == wallet.id).all()


def _tx(db, company, branch, wallet, amount, ptype, ref="sale", ttype="income"):
    t = Transaction(company_id=company.id, branch_id=branch.id, wallet_id=wallet.id, type=ttype,
                    amount=Decimal(amount), payment_type=ptype, currency_code="UZS",
                    reference_type=ref, reference_id=1, description="test")
    db.add(t)
    db.flush()
    return t


# ── 1, 2. 4 mln naqd + 6 mln qarz ────────────────────────────────────────────

def test_cash_plus_debt_line_writes_only_cash_transaction(db, w):
    sale = create_sale(db, _sale_data(w, 10_000_000, payments=[
        {"type": "cash", "amount": 4_000_000}, {"type": "debt", "amount": 6_000_000}]), w['admin'])
    txs = _txs(db)
    assert len(txs) == 1 and txs[0].type == "income" and txs[0].payment_type == "cash"
    assert Decimal(str(txs[0].amount)) == Decimal("4000000")
    assert db.query(SalePayment).filter(SalePayment.sale_id == sale.id).count() == 2
    kms = _kms(db, w['wallet'])
    assert len(kms) == 1 and kms[0].payment_type == "cash" and kms[0].direction == "in"
    db.refresh(w['wallet'])
    assert Decimal(str(w['wallet'].balance)) == Decimal("4000000")


def test_debt_later_paid_total_income_is_10m_not_16m(client, db, w):
    create_sale(db, _sale_data(w, 10_000_000, payments=[
        {"type": "cash", "amount": 4_000_000}, {"type": "debt", "amount": 6_000_000}]), w['admin'])
    db.refresh(w['cust'])
    assert w['cust'].debt_balances["UZS"] == 6000000.0
    r = client.login(w['cashier']).post(f"/api/customers/{w['cust'].id}/pay-debt",
                                        json={"amount": 6_000_000, "payment_type": "cash", "reason": "to'lov",
                                              "wallet_id": w['wallet'].id})
    assert r.status_code == 200, r.text
    r = client.login(w['admin']).get("/api/finance/cash-balance")
    assert r.status_code == 200, r.text
    assert r.json()["income_by_currency"]["UZS"] == 10_000_000.0


def test_single_path_debt_sale_writes_no_transaction(db, w):
    # payment_type=debt, paid_amount>0 (chekka holat): Transaction ham, KassaMovement ham yo'q
    create_sale(db, _sale_data(w, 1000, payment_type="debt", paid_amount=Decimal("0")), w['admin'])
    assert _txs(db) == [] and _kms(db, w['wallet']) == []


def test_single_cash_path_still_writes_transaction(db, w):
    create_sale(db, _sale_data(w, 1000, payment_type="cash", paid_amount=Decimal("1000")), w['admin'])
    txs = _txs(db)
    assert len(txs) == 1 and txs[0].payment_type == "cash"
    assert len(_kms(db, w['wallet'])) == 1


# ── 3. Eski debt/cashback Transaction'lar hisobotda ko'rinmaydi ──────────────

def test_legacy_noncash_transactions_hidden_from_reports(client, db, w):
    _tx(db, w['ca'], w['ba'], w['wallet'], 5_000_000, "cash")
    _tx(db, w['ca'], w['ba'], w['wallet'], 7_000_000, "debt")
    _tx(db, w['ca'], w['ba'], w['wallet'], 3_000_000, "cashback")
    _tx(db, w['ca'], w['ba'], w['wallet'], 2_000_000, None)          # payment_type NULL — saqlanadi
    _tx(db, w['ca'], w['ba'], w['wallet'], 9_000_000, "debt", ttype="expense")
    c = client.login(w['admin'])
    r = c.get("/api/finance/cash-balance").json()
    assert r["income_by_currency"]["UZS"] == 7_000_000.0
    assert "UZS" not in r["expense_by_currency"] or r["expense_by_currency"]["UZS"] == 0
    items = c.get("/api/finance/payments/income").json()["items"]
    assert sorted(i["amount"] for i in items) == [2_000_000.0, 5_000_000.0]
    assert c.get("/api/finance/payments/expense").json()["items"] == []
    d = c.get("/api/dashboard/summary").json()
    assert d["cash_balance"] == 7_000_000.0


def test_legacy_rows_stay_in_db(db, w):
    _tx(db, w['ca'], w['ba'], w['wallet'], 7_000_000, "debt")
    assert db.query(Transaction).filter(Transaction.payment_type == "debt").count() == 1


def test_reports_isolated_between_companies(client, db, w):
    _tx(db, w['ca'], w['ba'], w['wallet'], 5_000_000, "cash")
    r = client.login(w['admin_b']).get("/api/finance/cash-balance").json()
    assert r["income_by_currency"] == {}
    r = client.login(w['admin']).get("/api/finance/cash-balance").json()
    assert r["income_by_currency"]["UZS"] == 5_000_000.0


# ── 4. Keshbek ───────────────────────────────────────────────────────────────

def test_cashback_line_writes_no_transaction_and_bonus_decreases(db, w):
    create_sale(db, _sale_data(w, 10_000, payments=[
        {"type": "cash", "amount": 6_000}, {"type": "cashback", "amount": 4_000}]), w['admin'])
    txs = _txs(db)
    assert [(t.payment_type, Decimal(str(t.amount))) for t in txs] == [("cash", Decimal("6000"))]
    assert [k.payment_type for k in _kms(db, w['wallet'])] == ["cash"]
    db.refresh(w['cust'])
    assert Decimal(str(w['cust'].bonus_balance)) == Decimal("46000")   # 50 000 − 4 000
    assert db.query(SalePayment).count() == 2


# ── 5. bank / visa kassada ───────────────────────────────────────────────────

def test_bank_transfer_visible_in_kassa_balances_and_close(client, db, w):
    create_sale(db, _sale_data(w, 20_000_000, payments=[{"type": "bank", "amount": 20_000_000}],
                               payment_type="bank"), w['admin'])
    km = _kms(db, w['wallet'])
    assert len(km) == 1 and km[0].payment_type == "bank"
    c = client.login(w['admin'])
    r = c.get(f"/api/kassa/{w['wallet'].id}")
    assert r.status_code == 200, r.text
    assert r.json()["balances"]["bank"] == [{"currency": "UZS", "value": 20_000_000.0}]
    assert r.json()["balances"]["total"] == [{"currency": "UZS", "value": 20_000_000.0}]
    x = c.get(f"/api/kassa/{w['wallet'].id}/x-report").json()
    assert x["calculated_balances"]["bank"] == [{"currency": "UZS", "value": 20_000_000.0}]
    # yopish: haqiqiy 19.5 mln → farq 500 000 (kamomad)
    r = c.post(f"/api/kassa/{w['wallet'].id}/close", json={"actual_amounts": {"bank": {"UZS": 19_500_000}}})
    assert r.status_code == 200, r.text
    ses = db.query(KassaSession).filter(KassaSession.wallet_id == w['wallet'].id).one()
    assert ses.status == "closed"
    adj = db.query(KassaMovement).filter(KassaMovement.reference_type == "closing_adjustment").one()
    assert adj.payment_type == "bank" and adj.direction == "out" and Decimal(str(adj.amount)) == Decimal("500000")
    final = r.json()["final_balances"]
    assert final["bank"] == [] and final["total"] == []


def test_visa_visible_in_balances(client, db, w):
    create_sale(db, _sale_data(w, 1000, payments=[{"type": "visa", "amount": 1000}], payment_type="visa"),
                w['admin'])
    r = client.login(w['admin']).get(f"/api/kassa/{w['wallet'].id}")
    assert r.json()["balances"]["visa"] == [{"currency": "UZS", "value": 1000.0}]


def test_payment_type_constants():
    assert "bank" in CASH_PAYMENT_TYPES and "visa" in CASH_PAYMENT_TYPES
    assert set(NON_CASH_PAYMENT_TYPES) == {"debt", "cashback", "mixed"}
    assert not set(CASH_PAYMENT_TYPES) & set(NON_CASH_PAYMENT_TYPES)
    assert "keshbek" in PAYMENT_TYPES and set(CASH_PAYMENT_TYPES) <= set(PAYMENT_TYPES)


def test_kassa_foreign_wallet_404(client, db, w):
    c = client.login(w['admin'])
    assert c.get(f"/api/kassa/{w['wallet_b'].id}").status_code == 404
    assert c.get(f"/api/kassa/{w['wallet_b'].id}/x-report").status_code == 404
    assert c.post(f"/api/kassa/{w['wallet_b'].id}/close", json={"actual_amounts": {}}).status_code == 404


# ── 6. get_kassa_balances: bitta so'rov, eski natija bilan bir xil ───────────

def _legacy_balances(wallet_id, db):
    """T0.29 dan oldingi implementatsiya (N+1) — solishtirish uchun."""
    result = {}
    for ptype in PAYMENT_TYPES:
        movements = db.query(KassaMovement.currency, func.sum(KassaMovement.amount)).filter(
            KassaMovement.wallet_id == wallet_id, KassaMovement.payment_type == ptype
        ).group_by(KassaMovement.currency).all()
        cur = []
        for currency, _ in movements:
            inc = db.query(func.sum(KassaMovement.amount)).filter(
                KassaMovement.wallet_id == wallet_id, KassaMovement.payment_type == ptype,
                KassaMovement.direction == "in", KassaMovement.currency == currency).scalar() or 0
            exp = db.query(func.sum(KassaMovement.amount)).filter(
                KassaMovement.wallet_id == wallet_id, KassaMovement.payment_type == ptype,
                KassaMovement.direction == "out", KassaMovement.currency == currency).scalar() or 0
            bal = float(inc) - float(exp)
            if bal != 0:
                cur.append({"currency": currency, "value": bal})
        result[ptype] = cur
    total = {}
    for ptype in PAYMENT_TYPES:
        for it in result[ptype]:
            total[it["currency"]] = total.get(it["currency"], 0) + it["value"]
    result["total"] = [{"currency": k, "value": v} for k, v in total.items() if v != 0]
    return result


def _seed_movements(db, w, extra_types=()):
    wid, cid = w['wallet'].id, w['ca'].id
    rows = [
        ("cash", "in", 1000, "UZS"), ("cash", "in", 500, "UZS"), ("cash", "out", 200, "UZS"),
        ("cash", "in", 50, "USD"), ("card", "in", 300, "UZS"), ("card", "out", 300, "UZS"),
        ("uzcard", "in", 700, "UZS"), ("click", "in", 40, "UZS"), ("keshbek", "in", 9, "UZS"),
        ("payme", "out", 5, "UZS"), ("humo", "in", 3, "USD"), ("uzum", "in", 11, "UZS"),
    ] + [(t, "in", 77, "UZS") for t in extra_types]
    for pt, d, a, cur in rows:
        db.add(KassaMovement(wallet_id=wid, company_id=cid, direction=d, payment_type=pt,
                             amount=Decimal(a), currency=cur, reference_type="t", description="x"))
    db.flush()


def _norm(res):
    return {k: sorted(v, key=lambda x: x["currency"]) for k, v in res.items()}


def test_get_kassa_balances_equals_legacy(db, w):
    from app.routers.kassa import get_kassa_balances
    _seed_movements(db, w)
    new, old = _norm(get_kassa_balances(w['wallet'].id, db)), _norm(_legacy_balances(w['wallet'].id, db))
    # eski ro'yxatdagi turlar bo'yicha natija bir xil; yangisida bank/visa qo'shimcha (bo'sh)
    for k, v in old.items():
        assert new[k] == v, k
    assert new["bank"] == [] and new["visa"] == []


def test_get_kassa_balances_single_select(db, w):
    from app.routers.kassa import get_kassa_balances
    _seed_movements(db, w)
    counts = {}
    bind = db.get_bind()

    def _count(label):
        stmts = []

        def on(conn, cursor, statement, params, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                stmts.append(statement)
        event.listen(bind, "before_cursor_execute", on)
        try:
            label()
        finally:
            event.remove(bind, "before_cursor_execute", on)
        return len(stmts)

    n1 = _count(lambda: get_kassa_balances(w['wallet'].id, db))
    assert n1 == 1
    _seed_movements(db, w, extra_types=("bank", "visa"))
    counts[2] = _count(lambda: get_kassa_balances(w['wallet'].id, db))
    assert counts[2] == 1        # tur va valyutalar soniga bog'liq emas


def test_unknown_payment_type_not_lost(db, w):
    from app.routers.kassa import get_kassa_balances
    _seed_movements(db, w, extra_types=("bank", "exotic"))
    res = get_kassa_balances(w['wallet'].id, db)
    assert res["bank"] == [{"currency": "UZS", "value": 77.0}]
    assert res["exotic"] == [{"currency": "UZS", "value": 77.0}]
    uzs_total = next(i["value"] for i in res["total"] if i["currency"] == "UZS")
    assert uzs_total == 1000 + 500 - 200 + 700 + 40 + 9 - 5 + 11 + 77 + 77


# ── 7. Mijozdan qarz hisobiga qaytarish ──────────────────────────────────────

def _return_payload(w, **kw):
    p = dict(customer_id=w['cust'].id, warehouse_id=w['wha'].id, payment_type="debt",
             items=[{"product_id": w['prod'].id, "quantity": 2, "unit_price": 1000}])
    p.update(kw)
    return p


def test_return_to_debt_writes_no_transaction_and_revert_restores_debt(client, db, w):
    w['cust'].debt_balance = Decimal("5000")
    w['cust'].debt_balances = {"UZS": 5000.0}
    db.flush()
    c = client.login(w['admin'])
    r = c.post("/api/inventory/return-from-customer", json=_return_payload(w))
    assert r.status_code == 200, r.text
    assert db.query(Transaction).count() == 0 and db.query(KassaMovement).count() == 0
    db.refresh(w['cust'])
    assert Decimal(str(w['cust'].debt_balance)) == Decimal("3000")
    assert w['cust'].debt_balances["UZS"] == 3000.0
    mid = r.json()["movement_ids"][0]
    r = c.delete(f"/api/inventory/movements/{mid}")
    assert r.status_code == 200, r.text
    db.refresh(w['cust'])
    assert Decimal(str(w['cust'].debt_balance)) == Decimal("5000")
    assert w['cust'].debt_balances["UZS"] == 5000.0


def test_return_partly_cash_keeps_transaction_for_revert(client, db, w):
    w['cust'].debt_balance = Decimal("5000")
    w['cust'].debt_balances = {"UZS": 5000.0}
    w['wallet'].balance = Decimal("100000")
    db.flush()
    c = client.login(w['admin'])
    r = c.post("/api/inventory/return-from-customer", json=_return_payload(
        w, payment_type="mixed", wallet_id=w['wallet'].id, paid_cash=500))
    assert r.status_code == 200, r.text
    assert db.query(Transaction).count() == 1       # naqd ulush bor — pul chiqdi
    db.refresh(w['cust'])
    assert Decimal(str(w['cust'].debt_balance)) == Decimal("3500")
    mid = r.json()["movement_ids"][0]
    assert c.delete(f"/api/inventory/movements/{mid}").status_code == 200
    db.refresh(w['cust'])
    assert Decimal(str(w['cust'].debt_balance)) == Decimal("5000")


def test_return_foreign_customer_404(client, db, w):
    cust_b = _customer(db, w['cb'], debt=5000)
    r = client.login(w['admin']).post("/api/inventory/return-from-customer",
                                      json=_return_payload(w, customer_id=cust_b.id))
    assert r.status_code == 404


# ── sale_return / qisman qaytarish ───────────────────────────────────────────

def test_full_return_debt_without_customer_writes_no_expense(db, w):
    from app.services.sale_return import create_return_sale
    data = SaleCreate(items=[{"product_id": w['prod'].id, "quantity": 1, "unit_price": 1000}],
                      payment_type="debt", paid_amount=Decimal("1000"), warehouse_id=w['wha'].id,
                      wallet_id=w['wallet'].id)
    create_return_sale(db, data, w['admin'])
    assert _txs(db, type="expense") == [] and _kms(db, w['wallet']) == []
    db.refresh(w['wallet'])
    assert Decimal(str(w['wallet'].balance)) == Decimal("0")


def test_full_return_cash_writes_expense(db, w):
    from app.services.sale_return import create_return_sale
    data = SaleCreate(items=[{"product_id": w['prod'].id, "quantity": 1, "unit_price": 1000}],
                      payment_type="cash", paid_amount=Decimal("1000"), warehouse_id=w['wha'].id,
                      wallet_id=w['wallet'].id)
    create_return_sale(db, data, w['admin'])
    txs = _txs(db, type="expense")
    assert len(txs) == 1 and txs[0].payment_type == "cash"
    assert [k.direction for k in _kms(db, w['wallet'])] == ["out"]


@pytest.mark.parametrize("ptype", ["mixed", "cashback"])
def test_partial_return_rejects_mixed_and_cashback(client, db, w, ptype):
    sale = create_sale(db, _sale_data(w, 2000, payments=[{"type": "cash", "amount": 2000}],
                                      payment_type="cash"), w['admin'])
    item = db.query(Sale).get(sale.id).items[0]
    r = client.login(w['admin']).post(f"/api/sales/{sale.id}/return-items", json={
        "items": [{"sale_item_id": item.id, "quantity": 1}], "payment_type": ptype})
    assert r.status_code == 400, r.text
    assert "qo'llab-quvvatlanmaydi" in r.json()["detail"]
    db.refresh(item)
    assert Decimal(str(item.returned_quantity or 0)) == Decimal("0")


def test_partial_return_cash_ok(client, db, w):
    sale = create_sale(db, _sale_data(w, 2000, payments=[{"type": "cash", "amount": 2000}],
                                      payment_type="cash"), w['admin'])
    item = db.query(Sale).get(sale.id).items[0]
    r = client.login(w['admin']).post(f"/api/sales/{sale.id}/return-items", json={
        "items": [{"sale_item_id": item.id, "quantity": 1}], "payment_type": "cash"})
    assert r.status_code == 200, r.text


def test_partial_return_foreign_sale_404(client, db, w, mk):
    sale = create_sale(db, _sale_data(w, 2000, payments=[{"type": "cash", "amount": 2000}],
                                      payment_type="cash"), w['admin'])
    item = db.query(Sale).get(sale.id).items[0]
    r = client.login(w['admin_b']).post(f"/api/sales/{sale.id}/return-items", json={
        "items": [{"sale_item_id": item.id, "quantity": 1}], "payment_type": "cash"})
    assert r.status_code == 404


# ── 8. POS: har to'lov turi alohida ──────────────────────────────────────────

def test_pos_payments_list_each_type_separate(db, w):
    sale = create_sale(db, _sale_data(w, 180_000, payments=[
        {"type": "cash", "amount": 100_000}, {"type": "uzcard", "amount": 50_000},
        {"type": "bank", "amount": 30_000}], paid_amount=Decimal("180000")), w['admin'])
    sp = {p.payment_type: Decimal(str(p.amount)) for p in db.query(SalePayment).filter(SalePayment.sale_id == sale.id)}
    assert sp == {"cash": Decimal("100000"), "uzcard": Decimal("50000"), "bank": Decimal("30000")}
    tx = {t.payment_type: Decimal(str(t.amount)) for t in _txs(db)}
    assert tx == sp
    km = {k.payment_type: Decimal(str(k.amount)) for k in _kms(db, w['wallet'])}
    assert km == sp
    db.refresh(w['wallet'])
    assert Decimal(str(w['wallet'].balance)) == Decimal("180000")


def test_pos_change_deducted_from_cash_row(db, w):
    # 200 000 naqd berib 170 000 sotuv: POS cash qatorini 170 000 qilib yuboradi
    create_sale(db, _sale_data(w, 170_000, payments=[{"type": "cash", "amount": 170_000}],
                               payment_type="cash", paid_amount=Decimal("170000")), w['admin'])
    txs = _txs(db)
    assert len(txs) == 1 and Decimal(str(txs[0].amount)) == Decimal("170000")
    db.refresh(w['wallet'])
    assert Decimal(str(w['wallet'].balance)) == Decimal("170000")


def test_legacy_client_paid_card_still_single_card(db, w):
    # Eski POS bundle: payments yo'q, paid_card yuboriladi — bitta 'card' to'lov
    create_sale(db, _sale_data(w, 150_000, payment_type="mixed", paid_amount=Decimal("150000"),
                               paid_cash=Decimal("100000"), paid_card=Decimal("50000")), w['admin'])
    tx = {t.payment_type: Decimal(str(t.amount)) for t in _txs(db)}
    assert tx == {"cash": Decimal("100000"), "card": Decimal("50000")}


# ── 9. pay-debt ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ptype", ["debt", "cashback", "mixed", "nomalum"])
def test_pay_debt_rejects_noncash_type(client, db, w, ptype):
    w['cust'].debt_balance = Decimal("1000")
    w['cust'].debt_balances = {"UZS": 1000.0}
    db.flush()
    r = client.login(w['cashier']).post(f"/api/customers/{w['cust'].id}/pay-debt",
                                        json={"amount": 500, "payment_type": ptype, "reason": "x",
                                              "wallet_id": w['wallet'].id})
    assert r.status_code == 400, r.text
    db.refresh(w['cust'])
    assert w['cust'].debt_balances["UZS"] == 1000.0
    assert db.query(Transaction).count() == 0


def test_pay_debt_bank_ok_and_foreign_customer_404(client, db, w):
    w['cust'].debt_balance = Decimal("1000")
    w['cust'].debt_balances = {"UZS": 1000.0}
    db.flush()
    r = client.login(w['cashier']).post(f"/api/customers/{w['cust'].id}/pay-debt",
                                        json={"amount": 500, "payment_type": "bank", "reason": "x",
                                              "wallet_id": w['wallet'].id})
    assert r.status_code == 200, r.text
    r = client.login(w['admin_b']).post(f"/api/customers/{w['cust'].id}/pay-debt",
                                        json={"amount": 500, "payment_type": "cash", "reason": "x"})
    assert r.status_code == 404


# ── tx_cash_flow_filter birlik testi ─────────────────────────────────────────

def test_tx_cash_flow_filter_unit(db, w):
    from app.utils.report_utils import tx_cash_flow_filter
    for pt in ("cash", "card", "bank", "debt", "cashback", None):
        _tx(db, w['ca'], w['ba'], w['wallet'], 10, pt)
    _tx(db, w['ca'], w['ba'], w['wallet'], 10, "cash", ref="shift")       # ichki — chiqariladi
    got = sorted(str(t.payment_type) for t in db.query(Transaction).filter(tx_cash_flow_filter()))
    assert got == sorted(["cash", "card", "bank", "None"])
