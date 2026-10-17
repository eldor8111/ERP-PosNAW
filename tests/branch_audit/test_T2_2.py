"""T2.2 — yagona filial P&L qoidasi va P&L'larni birlashtirish.

Qamrov: uch endpoint (/finance/profit-loss, /reports/profit-loss, /reports/pnl-compare) bir xil net_profit;
bir xil nomli kategoriyalar; other_income oq ro'yxati va valyuta; filialsiz guruh (-1) va
sigma(filiallar) + filialsiz = butun korxona; resolve_money_branch_id tartibi; kategoriya 409/404 holatlari;
xarajat filiali kassadan; Transaction.company_id; ikki korxona izolyatsiyasi; statik tekshiruvlar.
"""
import itertools
import json
import os
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.currency import Currency
from app.models.moliya import Expense, ExpenseCategory, Transaction, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole
from app.services.branch_attribution import resolve_money_branch_id
from app.services.pnl_service import (
    OTHER_INCOME_REFS, UNASSIGNED_BRANCH, compute_pnl, compute_pnl_by_branch,
)
from app.utils.report_utils import _date_range

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
PERIOD = {'date_from': '2020-01-01', 'date_to': '2099-12-31'}
CMP = {'p1_from': '2020-01-01', 'p1_to': '2099-12-31', 'p2_from': '2020-01-01', 'p2_to': '2099-12-31'}


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _range():
    return _date_range(date(2020, 1, 1), date(2099, 12, 31))


def _product(db, company):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T22-{n}", barcode=f"B22-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _sale(db, user, company, product, warehouse, amount=1000, cost=400, branch_id='auto', refund=False):
    """Sotuv (yoki qaytarish hujjati) to'g'ridan-to'g'ri: Sale + bitta SaleItem."""
    n = next(_seq)
    kw = {}
    if branch_id != 'auto':
        kw['branch_id'] = branch_id
    s = Sale(number=f"{'R' if refund else 'S'}T22-{n}", cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None, total_amount=Decimal(amount),
             paid_amount=Decimal(amount), payment_type=PaymentType.cash,
             status=SaleStatus.refunded if refund else SaleStatus.completed, **kw)
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal(1), unit_price=Decimal(amount),
                    cost_price=Decimal(cost), subtotal=Decimal(amount), currency_code="UZS", exchange_rate=1))
    db.flush()
    return s


def _cat(db, company, name="Ijara"):
    c = ExpenseCategory(name=name, company_id=company.id if company else None)
    db.add(c)
    db.flush()
    return c


def _expense(db, company, branch_id, cat, amount, wallet=None, user=None):
    e = Expense(company_id=company.id, branch_id=branch_id, category_id=cat.id, amount=Decimal(amount),
                wallet_id=wallet.id if wallet else None, approved_by=user.id if user else None)
    db.add(e)
    db.flush()
    return e


def _tx(db, company, branch_id, amount, ref=None, tx_type="income", currency="UZS", voided=False, payment_type="cash"):
    from datetime import datetime
    t = Transaction(company_id=company.id, branch_id=branch_id, type=tx_type, amount=Decimal(amount),
                    reference_type=ref, currency_code=currency, payment_type=payment_type,
                    voided_at=datetime.utcnow() if voided else None)
    db.add(t)
    db.flush()
    return t


def _wallet(db, company, branch, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal(1000000),
               company_id=company.id, branch_id=branch.id if branch else None, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    return w


@pytest.fixture
def w(db, mk):
    """A korxona: a1 (wh1), a2 (wh2), filialsiz ombor (whn). B korxona: alohida tenant."""
    ca, a1, wh1, admin = mk.tenant(UserRole.admin)
    a2 = mk.branch(ca, "Yunusobod")
    wh2 = mk.warehouse(ca, a2, name="Ombor Yunusobod")
    whn = mk.warehouse(ca, None, name="Filialsiz ombor")
    acc = mk.user(ca, role=UserRole.accountant, branch=a1)
    prod = _product(db, ca)
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    prod_b = _product(db, cb)
    return dict(ca=ca, a1=a1, a2=a2, wh1=wh1, wh2=wh2, whn=whn, admin=admin, acc=acc, prod=prod,
                cb=cb, b1=b1, whb=whb, admin_b=admin_b, prod_b=prod_b)


def _seed(db, w):
    """Har filial va filialsiz guruhga tushum, xarajat va boshqa kirim yozadi."""
    ca, admin, prod = w['ca'], w['admin'], w['prod']
    _sale(db, admin, ca, prod, w['wh1'], 10000, 4000)
    _sale(db, admin, ca, prod, w['wh2'], 6000, 2000)
    _sale(db, admin, ca, prod, w['whn'], 3000, 1000)                       # filialsiz ombor
    _sale(db, admin, ca, prod, w['wh1'], 1000, 400, refund=True)           # qaytarish (a1)
    cat = _cat(db, ca, "Ijara")
    _expense(db, ca, w['a1'].id, cat, 2000)
    _expense(db, ca, w['a2'].id, cat, 500)
    _expense(db, ca, w['b1'].id, cat, 700)                                 # begona korxona filiali -> filialsiz
    _tx(db, ca, w['a1'].id, 300, ref="delivery_fee")
    _tx(db, ca, w['a2'].id, 200, ref=None)
    _tx(db, ca, None, 100, ref="other_income")                             # filialsiz kirim
    _tx(db, ca, w['a1'].id, 9999, ref="shift")                             # chiqarib tashlanadi


# ── 1. Uch endpoint bir xil net_profit ───────────────────────────────────────

@pytest.mark.parametrize("branch", ["a1", "a2", None, "unassigned"])
def test_three_endpoints_same_net_profit(client, db, w, branch):
    _seed(db, w)
    bid = {"a1": w['a1'].id, "a2": w['a2'].id, None: None, "unassigned": UNASSIGNED_BRANCH}[branch]
    q = dict(PERIOD)
    cq = dict(CMP)
    if bid is not None:
        q['branch_id'] = bid
        cq['branch_id'] = bid
    c = client.login(w['admin'])
    r1 = c.get('/api/finance/profit-loss', params=q)
    r2 = c.get('/api/reports/profit-loss', params=q)
    r3 = c.get('/api/reports/pnl-compare', params=cq)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r3.status_code == 200, r3.text
    n1, n2 = r1.json()['net_profit'], r2.json()['net_profit']
    n3p1, n3p2 = r3.json()['rows']['net_profit']['p1'], r3.json()['rows']['net_profit']['p2']
    assert n1 == n2 == n3p1 == n3p2
    # javob kalitlari saqlangan + yangi other_income
    for k in ("period", "gross_revenue", "returns", "revenue", "cogs", "gross_profit", "gross_margin_pct",
              "expenses", "net_profit", "net_margin_pct", "other_income"):
        assert k in r1.json() and k in r2.json()
    assert r1.json()['other_income'] == r2.json()['other_income'] == r3.json()['rows']['other_income']['p1']


def test_a1_numbers(client, db, w):
    """a1: tushum 10000-1000, tannarx 4000-400, boshqa kirim 300 (shift chiqarib tashlangan), xarajat 2000."""
    _seed(db, w)
    r = client.login(w['admin']).get('/api/reports/profit-loss', params={**PERIOD, 'branch_id': w['a1'].id})
    j = r.json()
    assert j['gross_revenue'] == 10000 and j['returns'] == 1000 and j['revenue'] == 9000
    assert j['cogs'] == 3600 and j['gross_profit'] == 5400
    assert j['other_income'] == 300 and j['expenses']['total'] == 2000
    assert j['net_profit'] == 5400 + 300 - 2000


# ── 2. Bir xil nomli kategoriyalar ───────────────────────────────────────────

def test_same_name_categories_summed_everywhere(client, db, w):
    ca = w['ca']
    c1, c2 = _cat(db, ca, "Ijara"), _cat(db, ca, "Ijara")
    _expense(db, ca, w['a1'].id, c1, 3000000)
    _expense(db, ca, w['a1'].id, c2, 2000000)
    c = client.login(w['admin'])
    r1 = c.get('/api/finance/profit-loss', params=PERIOD).json()
    r2 = c.get('/api/reports/profit-loss', params=PERIOD).json()
    r3 = c.get('/api/reports/pnl-compare', params=CMP).json()
    assert r1['expenses']['total'] == r2['expenses']['total'] == 5000000
    assert r1['expenses']['by_category'] == [{"name": "Ijara", "total": 5000000.0}]
    assert r2['expenses']['by_category'] == r1['expenses']['by_category']
    assert r3['rows']['total_indirect_expenses']['p1'] == 5000000
    ijara = [x for x in r3['expense_categories'] if x['name'] == "Ijara"]
    assert len(ijara) == 1 and ijara[0]['p1'] == ijara[0]['p2'] == 5000000


def test_uncategorized_name_group_by_sql(db, w):
    """Kategoriya nomi bo'yicha SQL guruhlash: 'Boshqa xarajatlar' nomli kategoriya bilan to'qnashmaydi."""
    ca = w['ca']
    _expense(db, ca, w['a1'].id, _cat(db, ca, "Boshqa xarajatlar"), 100)
    _expense(db, ca, w['a1'].id, _cat(db, ca, "Boshqa xarajatlar"), 50)
    p = compute_pnl(db, ca.id, *_range(), None)
    assert p['expenses']['total'] == 150
    assert p['expenses']['by_category'] == [{"name": "Boshqa xarajatlar", "total": 150.0}]


# ── 3. other_income oq ro'yxati ──────────────────────────────────────────────

def test_other_income_whitelist(db, w):
    ca, b = w['ca'], w['a1'].id
    _tx(db, ca, b, 100, ref=None)
    _tx(db, ca, b, 200, ref="delivery_fee")
    _tx(db, ca, b, 400, ref="other_income")
    for i, ref in enumerate(("shift", "return_to_supplier", "customer_payment", "sale", "sale_refund",
                             "supplier_payment", "opening", "invest"), start=1):
        _tx(db, ca, b, 10 ** (i + 3), ref=ref)                  # hech biri kirmasligi kerak
    _tx(db, ca, b, 5000, ref=None, voided=True)                  # bekor qilingan
    _tx(db, ca, b, 6000, ref=None, tx_type="expense")            # chiqim
    _tx(db, ca, b, 7000, ref=None, payment_type="debt")          # naqd bo'lmagan
    assert set(OTHER_INCOME_REFS) >= {"delivery_fee"}
    p = compute_pnl(db, ca.id, *_range(), None)
    assert p['other_income'] == 700
    assert p['net_profit'] == 700


def test_other_income_currency_converted(db, w):
    ca, b = w['ca'], w['a1'].id
    db.add(Currency(name="US Dollar", code="USD", rate=Decimal(12000), company_id=ca.id))
    db.flush()
    _tx(db, ca, b, 100, ref=None)
    _tx(db, ca, b, 2, ref="other_income", currency="USD")
    p = compute_pnl(db, ca.id, *_range(), None)
    assert p['other_income'] == 100 + 2 * 12000
    assert p['other_income_note']
    p2 = compute_pnl(db, w['cb'].id, *_range(), None)
    assert p2['other_income'] == 0 and p2['other_income_note'] is None


def test_shift_and_supplier_return_excluded_in_pnl_compare(client, db, w):
    ca, b = w['ca'], w['a1'].id
    _tx(db, ca, b, 4000, ref="shift")
    _tx(db, ca, b, 2000, ref="return_to_supplier")
    _tx(db, ca, b, 300, ref="delivery_fee")
    r = client.login(w['admin']).get('/api/reports/pnl-compare', params=CMP).json()
    assert r['rows']['other_income']['p1'] == 300


# ── 4. Filialsiz guruh (-1) ──────────────────────────────────────────────────

def test_unassigned_group_sums_to_company_total(db, w):
    _seed(db, w)
    ca = w['ca']
    total = compute_pnl(db, ca.id, *_range(), None)
    parts = compute_pnl_by_branch(db, ca.id, *_range())
    assert [x['branch_id'] for x in parts] == sorted(
        [w['a1'].id, w['a2'].id]) + [UNASSIGNED_BRANCH]
    unassigned = parts[-1]
    assert unassigned['gross_revenue'] == 3000                       # Warehouse.branch_id IS NULL sotuvi
    assert unassigned['expenses']['total'] == 700                    # begona filialga yozilgan xarajat
    assert unassigned['other_income'] == 100
    for key in ("gross_revenue", "returns", "cogs", "net_profit", "other_income"):
        assert round(sum(x[key] for x in parts), 2) == total[key], key
    assert round(sum(x['expenses']['total'] for x in parts), 2) == total['expenses']['total']


def test_unassigned_filter_via_api_and_reports(client, db, w):
    _seed(db, w)
    c = client.login(w['admin'])
    r = c.get('/api/reports/profit-loss', params={**PERIOD, 'branch_id': -1})
    assert r.status_code == 200 and r.json()['gross_revenue'] == 3000
    r = c.get('/api/reports/expenses', params={**PERIOD, 'branch_id': -1})
    assert r.status_code == 200 and r.json()['total'] == 700
    r = c.get('/api/reports/sales', params={**PERIOD, 'branch_id': -1})
    assert r.status_code == 200, r.text


def test_branch_warehouse_ids_unassigned(db, w):
    from app.utils.report_utils import branch_warehouse_ids
    assert branch_warehouse_ids(db, w['ca'].id, UNASSIGNED_BRANCH) == [w['whn'].id]
    assert branch_warehouse_ids(db, w['ca'].id, w['a1'].id) == [w['wh1'].id]
    assert branch_warehouse_ids(db, w['ca'].id, None) is None


def test_legacy_sale_without_snapshot_uses_warehouse_branch(db, w):
    """Snapshot'i bo'sh eski sotuv (branch_id NULL): ombor filialiga yoziladi, filialsiz ombor -> -1."""
    ca = w['ca']
    s1 = _sale(db, w['admin'], ca, w['prod'], w['wh2'], 500)
    s2 = _sale(db, w['admin'], ca, w['prod'], w['whn'], 300)
    db.query(Sale).filter(Sale.id.in_([s1.id, s2.id])).update({Sale.branch_id: None}, synchronize_session=False)
    db.flush()
    assert compute_pnl(db, ca.id, *_range(), w['a2'].id)['gross_revenue'] == 500
    assert compute_pnl(db, ca.id, *_range(), UNASSIGNED_BRANCH)['gross_revenue'] == 300


# ── 5. resolve_money_branch_id tartibi ───────────────────────────────────────

def test_resolve_money_branch_order(db, mk):
    c = mk.company()
    main = mk.branch(c, "Asosiy", is_main=True)
    other = mk.branch(c, "Boshqa")
    b_user, b_wallet, b_wh, b_explicit = (mk.branch(c, n) for n in ("U", "W", "H", "E"))
    wh = mk.warehouse(c, b_wh)
    wallet = _wallet(db, c, b_wallet)
    user = mk.user(c, role=UserRole.admin, branch=b_user)
    nb_user = mk.user(c, role=UserRole.admin, branch=None)

    assert resolve_money_branch_id(db, user, explicit_branch_id=b_explicit.id, wallet=wallet,
                                   warehouse_id=wh.id) == b_explicit.id
    assert resolve_money_branch_id(db, user, wallet=wallet, warehouse_id=wh.id) == b_wh.id     # sotuv: ombor
    assert resolve_money_branch_id(db, user, wallet=wallet) == b_wallet.id                      # pul: kassa
    assert resolve_money_branch_id(db, user) == b_user.id                                       # xodim
    assert resolve_money_branch_id(db, nb_user) == main.id                                      # asosiy filial
    # kassa/ombor filialsiz bo'lsa xodim filialiga tushadi
    assert resolve_money_branch_id(db, user, wallet=_wallet(db, c, None)) == b_user.id
    assert other.id != main.id


def test_resolve_money_branch_main_then_lowest_active(db, mk):
    c = mk.company()
    dead = mk.branch(c, "Arxiv", is_active=False)
    b2 = mk.branch(c, "B2")
    b3 = mk.branch(c, "B3")
    u = mk.user(c, role=UserRole.admin, branch=None)
    got = resolve_money_branch_id(db, u)
    assert got == b2.id and got not in (dead.id, b3.id)         # ORDER BY id, faqat faol


def test_resolve_money_branch_400_never_zero(db, mk):
    c = mk.company()
    u = mk.user(c, role=UserRole.admin, branch=None)
    with pytest.raises(HTTPException) as e:
        resolve_money_branch_id(db, u)
    assert e.value.status_code == 400 and e.value.detail == "Korxonada filial yo'q"
    mk.branch(c, "Arxiv", is_active=False)
    with pytest.raises(HTTPException) as e:
        resolve_money_branch_id(db, u)
    assert e.value.status_code == 400


def test_resolve_money_branch_foreign_explicit_400(db, w):
    with pytest.raises(HTTPException) as e:
        resolve_money_branch_id(db, w['admin'], explicit_branch_id=w['b1'].id)
    assert e.value.status_code == 400
    # begona korxona kassasi/ombori e'tiborga olinmaydi
    wb = _wallet(db, w['cb'], w['b1'])
    assert resolve_money_branch_id(db, w['admin'], wallet=wb, warehouse_id=w['whb'].id) == w['a1'].id


def test_thin_wrappers_keep_behaviour(db, w):
    from app.services.sale_helpers import resolve_branch_id
    from app.services.supplier_ledger import resolve_branch
    assert resolve_branch_id(db, w['admin'], w['wh2'].id) == w['a2'].id            # ombor birinchi
    assert resolve_branch_id(db, w['admin'], None) == w['a1'].id
    assert resolve_branch(db, w['admin'], w['wh2'].id) == w['a1'].id               # standart: xodim birinchi
    assert resolve_branch(db, w['admin'], w['wh2'].id, prefer_warehouse=True) == w['a2'].id


# ── 6. Xarajat yaratish: filial, company_id, kategoriya ──────────────────────

def test_kassa_expense_branch_from_wallet(client, db, w):
    """Buxgalter/admin Asosiy filialda, Yunusobod kassasi orqali xarajat kiritadi -> Yunusobod."""
    cat = _cat(db, w['ca'])
    wl = _wallet(db, w['ca'], w['a2'])
    r = client.login(w['admin']).post('/api/kassa/do-expense', json={
        "wallet_id": wl.id, "category_id": cat.id, "amount": 2000000, "payment_type": "cash"})
    assert r.status_code == 200, r.text
    e = db.get(Expense, r.json()['expense_id'])
    t = db.query(Transaction).filter(Transaction.reference_type == "expense", Transaction.reference_id == e.id).one()
    assert e.branch_id == w['a2'].id and t.branch_id == w['a2'].id and t.company_id == w['ca'].id


def test_finance_expense_branch_wallet_and_cash_balance(client, db, w):
    cat = _cat(db, w['ca'])
    wl = _wallet(db, w['ca'], w['a2'])
    c = client.login(w['acc'])                                   # buxgalter, filiali a1
    r = c.post('/api/finance/expenses', json={"category_id": cat.id, "amount": 2000000, "wallet_id": wl.id})
    assert r.status_code == 201, r.text
    e = db.get(Expense, r.json()['id'])
    t = db.query(Transaction).filter(Transaction.reference_type == "expense").one()
    assert e.branch_id == w['a2'].id == t.branch_id
    assert t.company_id == w['ca'].id and t.reference_id == e.id
    # branch_id yubormasdan ham ishlaydi (eski klientlar), cash-balance da ko'rinadi
    r = c.get('/api/finance/cash-balance')
    assert r.json()['total_expense'] == 2000000
    assert c.get('/api/finance/cash-balance', params={'branch_id': w['a2'].id}).json()['total_expense'] == 2000000
    assert c.get('/api/finance/cash-balance', params={'branch_id': w['a1'].id}).json()['total_expense'] == 0
    # P&L: xarajat Yunusobodda
    pl = c.get('/api/finance/profit-loss', params={**PERIOD, 'branch_id': w['a2'].id}).json()
    assert pl['expenses']['total'] == 2000000
    assert c.get('/api/finance/profit-loss', params={**PERIOD, 'branch_id': w['a1'].id}).json()['expenses']['total'] == 0


def test_expense_foreign_category_rejected(client, db, w):
    cat_b = _cat(db, w['cb'])
    c = client.login(w['admin'])
    assert c.post('/api/finance/expenses', json={"category_id": cat_b.id, "amount": 10}).status_code == 404
    wl = _wallet(db, w['ca'], w['a1'])
    r = c.post('/api/kassa/do-expense', json={"wallet_id": wl.id, "category_id": cat_b.id, "amount": 10})
    assert r.status_code == 404
    assert db.query(Expense).count() == 0
    # o'z kategoriyasi bilan ishlaydi
    cat_a = _cat(db, w['ca'])
    assert c.post('/api/finance/expenses', json={"category_id": cat_a.id, "amount": 10}).status_code == 201


def test_expense_lists_have_branch_name(client, db, w):
    cat = _cat(db, w['ca'])
    wl = _wallet(db, w['ca'], w['a2'])
    e = _expense(db, w['ca'], w['a2'].id, cat, 500, wallet=wl)
    c = client.login(w['admin'])
    row = c.get('/api/finance/expenses').json()[0]
    assert row['id'] == e.id and row['branch_id'] == w['a2'].id and row['branch_name'] == "Yunusobod"
    row = c.get('/api/reports/expenses', params=PERIOD).json()['items'][0]
    assert row['branch_id'] == w['a2'].id and row['branch_name'] == "Yunusobod" and row['wallet_id'] == wl.id


# ── 7. Kategoriyalar: 409 / 404 ──────────────────────────────────────────────

def test_category_create_duplicate_409(client, db, w):
    c = client.login(w['admin'])
    assert c.post('/api/finance/expense-categories', json={"name": "Ijara"}).status_code == 201
    assert c.post('/api/finance/expense-categories', json={"name": "  ijara "}).status_code == 409
    assert c.post('/api/kassa/categories', json={"name": "IJARA"}).status_code == 409
    assert c.post('/api/kassa/categories', json={"name": "Elektr"}).status_code == 200
    # boshqa korxonada bir xil nom mumkin
    assert client.login(w['admin_b']).post('/api/finance/expense-categories', json={"name": "Ijara"}).status_code == 201
    # bo'sh nom
    assert c.post('/api/finance/expense-categories', json={"name": "   "}).status_code == 400


def test_category_rename(client, db, w):
    a, b = _cat(db, w['ca'], "Ijara"), _cat(db, w['ca'], "Svet")
    c = client.login(w['admin'])
    r = c.put(f'/api/finance/expense-categories/{a.id}', json={"name": "Arenda"})
    assert r.status_code == 200 and r.json()['name'] == "Arenda"
    assert c.put(f'/api/finance/expense-categories/{b.id}', json={"name": " arenda"}).status_code == 409
    assert c.put(f'/api/finance/expense-categories/{b.id}', json={"name": "Svet"}).status_code == 200   # o'ziga o'zi
    # begona korxona kategoriyasi
    cat_b = _cat(db, w['cb'], "Boshqa")
    assert c.put(f'/api/finance/expense-categories/{cat_b.id}', json={"name": "X"}).status_code == 404
    assert c.put('/api/finance/expense-categories/999999', json={"name": "X"}).status_code == 404


def test_category_delete_used_409_unused_204(client, db, w):
    used, free = _cat(db, w['ca'], "Ishlatilgan"), _cat(db, w['ca'], "Bo'sh")
    _expense(db, w['ca'], w['a1'].id, used, 100)
    c = client.login(w['admin'])
    r = c.delete(f'/api/finance/expense-categories/{used.id}')
    assert r.status_code == 409 and r.json()['detail'] == "Kategoriyada xarajatlar bor"
    assert c.delete(f'/api/finance/expense-categories/{free.id}').status_code == 204
    cat_b = _cat(db, w['cb'], "Begona")
    assert c.delete(f'/api/finance/expense-categories/{cat_b.id}').status_code == 404


def test_category_roles(client, db, w, mk):
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['a1'])
    c = client.login(cashier)
    assert c.post('/api/finance/expense-categories', json={"name": "Yo'q"}).status_code == 403
    assert c.put('/api/finance/expense-categories/1', json={"name": "Yo'q"}).status_code == 403
    assert c.delete('/api/finance/expense-categories/1').status_code == 403


def test_kassa_categories_list_only_company(client, db, w):
    own = _cat(db, w['ca'], "O'zimniki")
    _cat(db, None, "Umumiy")
    _cat(db, w['cb'], "Begona")
    c = client.login(w['admin'])
    kassa = c.get('/api/kassa/categories').json()
    fin = c.get('/api/finance/expense-categories').json()
    assert [x['id'] for x in kassa] == [own.id] == [x['id'] for x in fin]


# ── 8. Izolyatsiya (ikki korxona) ────────────────────────────────────────────

def test_pnl_company_isolation(client, db, w):
    _seed(db, w)
    _sale(db, w['admin_b'], w['cb'], w['prod_b'], w['whb'], 77777, 1)
    cat_b = _cat(db, w['cb'], "B-xarajat")
    _expense(db, w['cb'], w['b1'].id, cat_b, 555)
    ca_total = client.login(w['admin']).get('/api/finance/profit-loss', params=PERIOD).json()
    cb_total = client.login(w['admin_b']).get('/api/finance/profit-loss', params=PERIOD).json()
    assert cb_total['gross_revenue'] == 77777 and cb_total['expenses']['total'] == 555
    assert ca_total['gross_revenue'] == 10000 + 6000 + 3000 and 77777 not in (ca_total['gross_revenue'],)
    assert [c['name'] for c in cb_total['expenses']['by_category']] == ["B-xarajat"]
    # begona filial -> 404, o'ziniki ishlaydi
    c = client.login(w['admin'])
    assert c.get('/api/finance/profit-loss', params={**PERIOD, 'branch_id': w['b1'].id}).status_code == 404
    assert c.get('/api/finance/profit-loss', params={**PERIOD, 'branch_id': w['a1'].id}).status_code == 200


def test_super_admin_needs_company(client, db, w, mk):
    _seed(db, w)
    sa = mk.user(None, role=UserRole.super_admin)
    c = client.login(sa)
    assert c.get('/api/finance/profit-loss', params=PERIOD).status_code == 400
    r = c.get('/api/finance/profit-loss', params={**PERIOD, 'company_id': w['ca'].id})
    assert r.status_code == 200 and r.json()['gross_revenue'] == 19000
    # oddiy foydalanuvchi company_id yubora olmaydi (e'tiborga olinmaydi)
    r = client.login(w['admin_b']).get('/api/finance/profit-loss', params={**PERIOD, 'company_id': w['ca'].id})
    assert r.json()['gross_revenue'] == 0


def test_bad_date_400(client, w):
    r = client.login(w['admin']).get('/api/finance/profit-loss', params={'date_from': 'xx'})
    assert r.status_code == 400


# ── 9. Statik tekshiruvlar ───────────────────────────────────────────────────

def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def test_no_hardcoded_branch_one_in_finance_jsx():
    assert 'branch_id: 1' not in _read('frontend/src/pages/admin/Finance.jsx')


@pytest.mark.parametrize("rel", ["app/routers/finance.py", "app/routers/kassa.py", "app/services/ai_tools_registry.py"])
def test_no_zero_branch_fallback(rel):
    src = _read(rel)
    assert 'branch_id or 0' not in src and 'tx_branch_id or 0' not in src


def test_calc_pnl_data_removed():
    assert '_calc_pnl_data' not in _read('app/routers/finance_report.py')


KEYS_T2_2 = ["reports.pl.otherIncome", "reports.unassignedBranch", "finance.branchColumn", "finance.allBranches"]


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


def test_pending_i18n_keys_in_all_languages():
    data = _merged_i18n(KEYS_T2_2)
    assert set(data) == {"uz", "ru", "en"}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    for key in ("reports.pl.otherIncome", "reports.unassignedBranch", "finance.branchColumn"):
        assert key in data['uz'] and all(data[l][key] for l in data)
    src = _read('frontend/src/pages/admin/Finance.jsx') + _read('frontend/src/pages/admin/Reports.jsx')
    for key in data['uz']:
        assert key in src, key


def test_migration_file():
    rel = 'alembic/versions/t2_2_pnl_unify_expense_categories_and_indexes.py'
    src = _read(rel)
    assert "revision: str = 't2_2'" in src and "down_revision: Union[str, None] = 't1_19'" in src   # zanjirga ulangan
    for token in ("uq_expense_cat_company_name", "uq_expense_cat_global_name", "expense_category_merge_log",
                  "expense_branch_fix_log", "ix_expenses_company_branch_created",
                  "ix_transactions_company_type_created", "IF NOT EXISTS"):
        assert token in src
    import py_compile
    py_compile.compile(os.path.join(ROOT, rel), doraise=True)


# ── 9. Valyutali xarajat: P&L amount_uzs bilan (T2.7) ────────────────────────

def test_usd_expense_uses_amount_uzs_in_all_endpoints(client, db, w):
    ca = w['ca']
    cat = _cat(db, ca, "Dollar xarajat")
    e = _expense(db, ca, w['a1'].id, cat, 200)
    e.currency = "USD"
    e.exchange_rate = Decimal("12700")
    e.amount_uzs = Decimal("2540000")
    _expense(db, ca, w['a1'].id, cat, 1000)   # eski yozuv: amount_uzs NULL -> amount
    db.flush()
    c = client.login(w['admin'])
    q = dict(PERIOD, branch_id=w['a1'].id)
    r1 = c.get('/api/finance/profit-loss', params=q).json()
    r2 = c.get('/api/reports/profit-loss', params=q).json()
    r3 = c.get('/api/reports/pnl-compare', params=dict(CMP, branch_id=w['a1'].id)).json()
    assert r1['expenses']['total'] == r2['expenses']['total'] == 2541000
    cats = {x['name']: x['total'] for x in r1['expenses']['by_category']}
    assert cats["Dollar xarajat"] == 2541000
    assert r1['net_profit'] == r2['net_profit'] == -2541000
    assert r3['rows']['net_profit']['p1'] == r3['rows']['net_profit']['p2'] == -2541000
    rep = c.get('/api/reports/expenses', params=q).json()
    assert rep['total'] == 2541000
    assert sorted(i['amount'] for i in rep['items']) == [1000, 2540000]
