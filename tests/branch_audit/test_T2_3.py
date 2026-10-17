"""T2.3 — ombor qoldig'i va kam zaxira hisobotlari.

Qamrov: yagona "kam qoldiq" ta'rifi (min_stock=0, jami = min, ombor doirasi, nofaol ombor, product_type='sell',
variantlar yig'indisi); resolve_wh_scope xatolari (404/400/403); /reports/inventory (+summary, X-Total-Count,
tannarx tartibi), /reports/stock-alert, /reports/dashboard (scope, cashier_id, debts.scope), o'lik stok filial
kesimi, /inventory/stock + low-stock + low-stock-count, /products/paginated (variantli mahsulot, 403, filial),
production/alerts, AI hisobot soni, ikki korxona izolyatsiyasi va frontend statik tekshiruvlari.
"""
import itertools
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.batch import Batch
from app.models.inventory import StockLevel, StockMovement, MovementType
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole
from app.services import stock_report
from app.services.stock_report import (
    inventory_rows, inventory_summary, low_stock_count, low_stock_products, resolve_wh_scope,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
OLD = datetime(2020, 1, 1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company, name=None, min_stock=0, cost=Decimal("500"), created_at=None, **kw):
    n = next(_seq)
    p = Product(name=name or f"Tovar {n}", sku=f"T23-{n}", barcode=f"B23-{n}", company_id=company.id,
                cost_price=cost, sale_price=Decimal("1000"), min_stock=min_stock, **kw)
    if created_at is not None:
        p.created_at = created_at
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty, variant=None):
    sl = StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal(qty),
                    variant_id=variant.id if variant else None)
    db.add(sl)
    db.flush()
    return sl


def _variant(db, product, name):
    v = ProductVariant(product_id=product.id, name=name)
    db.add(v)
    db.flush()
    return v


def _batch(db, product, warehouse, company, qty, price):
    b = Batch(product_id=product.id, warehouse_id=warehouse.id if warehouse else None, company_id=company.id,
              quantity=Decimal(qty), initial_quantity=Decimal(qty), purchase_price=Decimal(price))
    db.add(b)
    db.flush()
    return b


def _sale(db, user, company, warehouse, product, qty=1, days_ago=1):
    n = next(_seq)
    when = datetime.now() - timedelta(days=days_ago)
    s = Sale(number=f"ST23-{n}", cashier_id=user.id, company_id=company.id, warehouse_id=warehouse.id,
             total_amount=Decimal(1000), paid_amount=Decimal(1000), payment_type=PaymentType.cash,
             status=SaleStatus.completed, created_at=when)
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal(qty), unit_price=Decimal(1000),
                    cost_price=Decimal(0), subtotal=Decimal(1000), currency_code="UZS", exchange_rate=1,
                    warehouse_id=warehouse.id))
    db.flush()
    return s


@pytest.fixture
def sqlite_dates(monkeypatch):
    """SQLite `CAST(x AS DATE)` sana emas son qaytaradi; dashboard kunlik trendi uchun `date()` bilan almashtiriladi."""
    import app.routers.reports as reports_mod
    from sqlalchemy import func
    monkeypatch.setattr(reports_mod, 'cast', lambda expr, _type: func.date(expr))


@pytest.fixture
def w(db, mk):
    """Korxona A: filial 1 (omborlar w1, w1b), filial 2 (w2); admin, filial-1 menejeri va kassiri.
    Korxona B: bitta tenant."""
    c = mk.company()
    b1, b2 = mk.branch(c, name="Chilonzor"), mk.branch(c, name="Yunusobod")
    w1 = mk.warehouse(c, b1, name="Chilonzor-1")
    w1b = mk.warehouse(c, b1, name="Chilonzor-2")
    w2 = mk.warehouse(c, b2, name="Yunusobod-1")
    admin = mk.user(c, role=UserRole.admin)
    manager = mk.user(c, role=UserRole.manager, branch=b1)
    cashier = mk.user(c, role=UserRole.cashier, branch=b1)
    oc, ob, ow, oadmin = mk.tenant()
    return dict(c=c, b1=b1, b2=b2, w1=w1, w1b=w1b, w2=w2, admin=admin, manager=manager, cashier=cashier,
                oc=oc, ob=ob, ow=ow, oadmin=oadmin)


# ── Yagona "kam qoldiq" ta'rifi ──────────────────────────────────────────────

def test_low_stock_product_counted_once_across_warehouses(db, mk, w):
    """min_stock=20, 4 omborda 5 tadan (jami 20) — 1 ta mahsulot (4 emas)."""
    whs = [w['w1'], w['w1b'], w['w2'], mk.warehouse(w['c'], w['b2'], name="Yunusobod-2")]
    p = _product(db, w['c'], min_stock=20)
    for wh in whs:
        _stock(db, p, wh, 5)
    assert low_stock_count(db, w['c'].id, None) == 1
    rows = low_stock_products(db, w['c'].id, None)
    assert len(rows) == 1 and rows[0]['product_id'] == p.id
    assert rows[0]['current_qty'] == Decimal(20) and rows[0]['shortage'] == Decimal(0)
    assert {x['warehouse_id'] for x in rows[0]['warehouses']} == {x.id for x in whs}


def test_low_stock_same_number_everywhere(client, db, mk, w):
    """reports/dashboard, inventory/low-stock-count, stock-alert, inventory/low-stock va AI bir xil: 1 ta."""
    p = _product(db, w['c'], min_stock=20)
    for wh in (w['w1'], w['w1b'], w['w2']):
        _stock(db, p, wh, 6)                      # jami 18 <= 20
    ok = _product(db, w['c'], min_stock=5)
    _stock(db, ok, w['w1'], 50)                   # yetarli
    admin = w['admin']
    c = client.login(admin)
    d = c.get('/api/reports/dashboard').json()
    assert d['inventory']['low_stock_count'] == 1
    assert [x['product_id'] for x in d['low_stock']] == [p.id]
    assert c.get('/api/inventory/low-stock-count').json() == {'count': 1}
    alert = c.get('/api/reports/stock-alert').json()
    assert len(alert) == 1 and alert[0]['product_id'] == p.id
    assert alert[0]['current_qty'] == '18.000' and alert[0]['shortage'] == '2.000'   # eski kalitlar saqlangan
    assert len(alert[0]['warehouses']) == 3
    lows = c.get('/api/inventory/low-stock').json()
    assert len(lows) == 1 and lows[0]['product_id'] == p.id
    assert stock_report.low_stock_count_for_scope(db, w['c'].id, None) == 1


def test_min_stock_zero_is_never_low(db, w):
    p = _product(db, w['c'], min_stock=0)
    _stock(db, p, w['w1'], 0)
    assert low_stock_count(db, w['c'].id, None) == 0
    assert low_stock_products(db, w['c'].id, None) == []


def test_total_equal_min_is_low_and_above_is_not(db, w):
    eq = _product(db, w['c'], min_stock=10)
    _stock(db, eq, w['w1'], 4)
    _stock(db, eq, w['w2'], 6)
    above = _product(db, w['c'], min_stock=10)
    _stock(db, above, w['w1'], 11)
    ids = {r['product_id'] for r in low_stock_products(db, w['c'].id, None)}
    assert ids == {eq.id}


def test_product_without_stock_rows_is_low_with_zero_qty(db, w):
    p = _product(db, w['c'], min_stock=3)
    rows = low_stock_products(db, w['c'].id, None)
    assert len(rows) == 1 and rows[0]['product_id'] == p.id
    assert rows[0]['current_qty'] == Decimal(0) and rows[0]['warehouses'] == []


def test_scope_by_warehouse_and_branch(db, w):
    p = _product(db, w['c'], min_stock=10)
    _stock(db, p, w['w1'], 8)
    _stock(db, p, w['w2'], 50)
    assert low_stock_count(db, w['c'].id, None) == 0                    # jami 58
    assert low_stock_count(db, w['c'].id, [w['w1'].id]) == 1            # faqat w1: 8
    assert low_stock_count(db, w['c'].id, [w['w2'].id]) == 0
    assert low_stock_count(db, w['c'].id, []) == 0                      # bo'sh doira - hech narsa


def test_inactive_warehouse_excluded(db, mk, w):
    dead = mk.warehouse(w['c'], w['b1'], name="Arxiv", is_active=False)
    p = _product(db, w['c'], min_stock=10)
    _stock(db, p, w['w1'], 4)
    _stock(db, p, dead, 100)                                            # nofaol ombor qoldig'i hisoblanmaydi
    rows = low_stock_products(db, w['c'].id, None)
    assert len(rows) == 1 and rows[0]['current_qty'] == Decimal(4)


def test_sell_type_and_deleted_products_excluded(db, w):
    sell = _product(db, w['c'], min_stock=10, product_type='sell')
    gone = _product(db, w['c'], min_stock=10, is_deleted=True)
    real = _product(db, w['c'], min_stock=10)
    _stock(db, real, w['w1'], 1)
    assert [r['product_id'] for r in low_stock_products(db, w['c'].id, None)] == [real.id]
    assert sell.id and gone.id


def test_variants_summed_at_product_level(db, w):
    p = _product(db, w['c'], min_stock=10)
    for name, q in (("S", 2), ("M", 3), ("L", 5)):
        _stock(db, p, w['w1'], q, variant=_variant(db, p, name))
    rows = low_stock_products(db, w['c'].id, None)
    assert len(rows) == 1 and rows[0]['current_qty'] == Decimal(10)     # 2+3+5 = min_stock
    assert low_stock_count(db, w['c'].id, None) == 1


def test_low_stock_isolated_between_companies(db, w):
    p = _product(db, w['c'], min_stock=10)
    _stock(db, p, w['w1'], 1)
    assert low_stock_count(db, w['oc'].id, None) == 0
    q = _product(db, w['oc'], min_stock=10)
    _stock(db, q, w['ow'], 1)
    assert [r['product_id'] for r in low_stock_products(db, w['oc'].id, None)] == [q.id]
    assert [r['product_id'] for r in low_stock_products(db, w['c'].id, None)] == [p.id]


def test_production_alerts_uses_product_level_definition(client, db, mk, w):
    rm1 = mk.warehouse(w['c'], w['b1'], name="Xom-1")
    rm2 = mk.warehouse(w['c'], w['b1'], name="Xom-2")
    raw = _product(db, w['c'], min_stock=10, product_type='raw_material')
    _stock(db, raw, rm1, 5)
    _stock(db, raw, rm2, 5)                                             # jami 10 <= 10 -> bitta qator
    other = _product(db, w['c'], min_stock=10)                          # xom ashyo emas
    _stock(db, other, w['w1'], 1)
    rows = stock_report.low_stock_products(db, w['c'].id, None, product_types=['raw_material'])
    assert [r['product_id'] for r in rows] == [raw.id]
    r = client.login(w['admin']).get('/api/production/alerts')
    if r.status_code == 200:                                            # ishlab chiqarish moduli yoqilgan bo'lsa
        low = r.json()['low_stock']
        assert [x['product_id'] for x in low] == [raw.id] and low[0]['quantity'] == 10.0


# ── resolve_wh_scope ─────────────────────────────────────────────────────────

def test_scope_foreign_company_warehouse_404(db, w):
    with pytest.raises(HTTPException) as e:
        resolve_wh_scope(db, w['admin'], w['c'].id, None, w['ow'].id)
    assert e.value.status_code == 404


def test_scope_warehouse_not_in_branch_400(db, w):
    with pytest.raises(HTTPException) as e:
        resolve_wh_scope(db, w['admin'], w['c'].id, w['b1'].id, w['w2'].id)
    assert e.value.status_code == 400 and e.value.detail == "Ombor tanlangan filialga tegishli emas"
    assert resolve_wh_scope(db, w['admin'], w['c'].id, w['b2'].id, w['w2'].id) == [w['w2'].id]


def test_scope_foreign_branch_404_and_branch_wh_ids(db, w):
    with pytest.raises(HTTPException) as e:
        resolve_wh_scope(db, w['admin'], w['c'].id, w['ob'].id, None)
    assert e.value.status_code == 404
    assert sorted(resolve_wh_scope(db, w['admin'], w['c'].id, w['b1'].id, None)) == sorted([w['w1'].id, w['w1b'].id])
    assert resolve_wh_scope(db, w['admin'], w['c'].id, None, None) is None


def test_scope_restricted_user(db, w):
    mgr = w['manager']
    # doira doim o'z filiali omborlari
    assert sorted(resolve_wh_scope(db, mgr, w['c'].id, None, None)) == sorted([w['w1'].id, w['w1b'].id])
    # ruxsatsiz ombor / filial -> 403
    for kw in ({'warehouse_id': w['w2'].id}, {'branch_id': w['b2'].id}):
        with pytest.raises(HTTPException) as e:
            resolve_wh_scope(db, mgr, w['c'].id, kw.get('branch_id'), kw.get('warehouse_id'))
        assert e.value.status_code == 403
    assert resolve_wh_scope(db, mgr, w['c'].id, None, w['w1'].id) == [w['w1'].id]


# ── /reports/dashboard ───────────────────────────────────────────────────────

def test_dashboard_scope_errors_and_new_fields(client, db, w):
    c = client.login(w['admin'])
    r = c.get('/api/reports/dashboard', params={'branch_id': w['b1'].id, 'warehouse_id': w['w2'].id})
    assert r.status_code == 400
    assert c.get('/api/reports/dashboard', params={'warehouse_id': w['ow'].id}).status_code == 404
    d = c.get('/api/reports/dashboard', params={'branch_id': w['b1'].id}).json()
    assert d['scope'] == {'branch_id': w['b1'].id, 'warehouse_id': None}
    assert d['debts']['scope'] == 'company'
    assert d['inventory']['product_count_scope'] == 'company'


def test_dashboard_cashier_id_and_branch_scope(client, db, w, sqlite_dates):
    p = _product(db, w['c'], min_stock=10)
    _stock(db, p, w['w1'], 2)
    _stock(db, p, w['w2'], 100)
    _sale(db, w['cashier'], w['c'], w['w1'], p)
    c = client.login(w['admin'])
    d = c.get('/api/reports/dashboard', params={'branch_id': w['b1'].id}).json()
    assert d['inventory']['low_stock_count'] == 1
    assert d['cashier_performance'][0]['cashier_id'] == w['cashier'].id
    assert d['cashier_performance'][0]['totals'] == {'UZS': 1000.0}
    d2 = c.get('/api/reports/dashboard', params={'branch_id': w['b2'].id}).json()
    assert d2['inventory']['low_stock_count'] == 0 and d2['cashier_performance'] == []


def test_dashboard_restricted_manager_cannot_pick_other_branch(client, db, w):
    c = client.login(w['manager'])
    assert c.get('/api/reports/dashboard', params={'warehouse_id': w['w2'].id}).status_code == 403
    assert c.get('/api/reports/dashboard', params={'branch_id': w['b2'].id}).status_code == 403
    assert c.get('/api/reports/dashboard').status_code == 200


def test_dashboard_other_company_isolated(client, db, w):
    p = _product(db, w['c'], min_stock=10)
    _stock(db, p, w['w1'], 1)
    d = client.login(w['oadmin']).get('/api/reports/dashboard').json()
    assert d['inventory']['low_stock_count'] == 0 and d['low_stock'] == []


# ── /reports/inventory va summary ────────────────────────────────────────────

def test_inventory_report_three_rows_with_warehouse_names(client, db, mk, w):
    p = _product(db, w['c'], name="Coca-Cola 1L")
    w3 = mk.warehouse(w['c'], w['b2'], name="Yunusobod-2")
    for wh, q in ((w['w1'], 12), (w['w2'], 0), (w3, 40)):
        _stock(db, p, wh, q)
    r = client.login(w['admin']).get('/api/reports/inventory')
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 3 and r.headers['X-Total-Count'] == '3'
    assert {x['warehouse_name'] for x in rows} == {"Chilonzor-1", "Yunusobod-1", "Yunusobod-2"}
    keys = {(x['product_id'], x['variant_id'] or 0, x['warehouse_id']) for x in rows}
    assert len(keys) == 3                                               # React kaliti takrorlanmaydi
    assert all('branch_name' in x and 'variant_name' in x and 'cost_basis' in x for x in rows)
    assert {x['branch_name'] for x in rows} == {"Chilonzor", "Yunusobod"}


def test_inventory_branch_filter_and_summary_equals_rows(client, db, w):
    p1 = _product(db, w['c'], cost=Decimal("100"))
    p2 = _product(db, w['c'], cost=Decimal("250"))
    _stock(db, p1, w['w1'], 10)
    _stock(db, p1, w['w2'], 7)
    _stock(db, p2, w['w1b'], 4)
    _stock(db, p2, w['w2'], 3)
    c = client.login(w['admin'])
    rows = c.get('/api/reports/inventory', params={'branch_id': w['b1'].id}).json()
    assert {x['warehouse_id'] for x in rows} == {w['w1'].id, w['w1b'].id}
    s = c.get('/api/reports/inventory/summary', params={'branch_id': w['b1'].id}).json()
    assert s['total_value'] == pytest.approx(sum(x['value'] for x in rows)) == pytest.approx(10 * 100 + 4 * 250)
    assert s['total_qty'] == 14 and s['sku_count'] == 2
    assert {x['warehouse_id'] for x in s['by_warehouse']} == {w['w1'].id, w['w1b'].id}
    assert [x['branch_id'] for x in s['by_branch']] == [w['b1'].id]
    full = c.get('/api/reports/inventory/summary').json()
    assert full['total_value'] == pytest.approx(10 * 100 + 7 * 100 + 4 * 250 + 3 * 250)
    assert {x['branch_id'] for x in full['by_branch']} == {w['b1'].id, w['b2'].id}
    one = c.get('/api/reports/inventory', params={'warehouse_id': w['w2'].id}).json()
    assert {x['warehouse_id'] for x in one} == {w['w2'].id}


def test_inventory_errors_pagination_and_isolation(client, db, w):
    p = _product(db, w['c'])
    for wh in (w['w1'], w['w1b'], w['w2']):
        _stock(db, p, wh, 5)
    c = client.login(w['admin'])
    assert c.get('/api/reports/inventory', params={'warehouse_id': w['ow'].id}).status_code == 404
    assert c.get('/api/reports/inventory', params={'branch_id': w['b2'].id, 'warehouse_id': w['w1'].id}).status_code == 400
    r = c.get('/api/reports/inventory', params={'limit': 2, 'skip': 1})
    assert len(r.json()) == 2 and r.headers['X-Total-Count'] == '3'
    # begona korxona foydalanuvchisi A ning qoldig'ini ko'rmaydi
    oc = client.login(w['oadmin'])
    assert oc.get('/api/reports/inventory').json() == []
    assert oc.get('/api/reports/inventory', params={'warehouse_id': w['w1'].id}).status_code == 404
    assert oc.get('/api/reports/inventory/summary').json()['total_value'] == 0


def test_inventory_cost_basis_order_and_is_low(db, mk, w):
    p = _product(db, w['c'], min_stock=100, cost=Decimal("999"))
    _stock(db, p, w['w1'], 10)        # shu ombor partiyasi bor
    _stock(db, p, w['w2'], 10)        # faqat korxona partiyasi bor (boshqa omborda)
    nb = mk.warehouse(w['c'], w['b2'], name="Bo'sh")
    _stock(db, p, nb, 10)             # hech qaysi partiya mos emas -> korxona o'rtachasi
    q = _product(db, w['c'], cost=Decimal("77"))
    _stock(db, q, w['w1'], 1)         # partiyasiz -> Product.cost_price
    _batch(db, p, w['w1'], w['c'], 10, 100)
    _batch(db, p, w['w1b'], w['c'], 10, 300)
    total, rows = inventory_rows(db, w['c'].id, None, 0, 100)
    by = {(r['product'].id, r['warehouse'].id): r for r in rows}
    assert by[(p.id, w['w1'].id)]['cost_basis'] == 'batch_wh' and by[(p.id, w['w1'].id)]['unit_cost'] == 100
    assert by[(p.id, w['w2'].id)]['cost_basis'] == 'batch_company' and by[(p.id, w['w2'].id)]['unit_cost'] == 200
    assert by[(q.id, w['w1'].id)]['cost_basis'] == 'product' and by[(q.id, w['w1'].id)]['unit_cost'] == 77
    assert total == 4
    # is_low — mahsulot darajasida: jami 30 <= 100
    assert all(by[(p.id, wid)]['is_low'] for (pid, wid) in by if pid == p.id)
    assert not by[(q.id, w['w1'].id)]['is_low']


def test_inventory_excludes_inactive_and_variant_rows_distinct(db, mk, w):
    dead = mk.warehouse(w['c'], w['b1'], name="Arxiv", is_active=False)
    p = _product(db, w['c'])
    _stock(db, p, dead, 50)
    _stock(db, p, w['w1'], 2, variant=_variant(db, p, "S"))
    _stock(db, p, w['w1'], 3, variant=_variant(db, p, "M"))
    total, rows = inventory_rows(db, w['c'].id, None, 0, 100)
    assert total == 2 and {r['variant_name'] for r in rows} == {"S", "M"}
    assert inventory_summary(db, w['c'].id, None)['total_qty'] == 5
    assert inventory_rows(db, w['c'].id, [], 0, 10) == (0, [])


def test_inventory_restricted_manager_sees_only_own_branch(client, db, w):
    p = _product(db, w['c'])
    _stock(db, p, w['w1'], 5)
    _stock(db, p, w['w2'], 9)
    c = client.login(w['manager'])
    rows = c.get('/api/reports/inventory').json()
    assert {x['warehouse_id'] for x in rows} == {w['w1'].id}
    assert c.get('/api/reports/inventory', params={'warehouse_id': w['w2'].id}).status_code == 403
    assert c.get('/api/reports/inventory/summary').json()['total_qty'] == 5


# ── O'lik stok ───────────────────────────────────────────────────────────────

def test_dead_stock_branch_scope_ignores_other_branch_sales(client, db, w, sqlite_dates):
    """Boshqa filialda har kuni sotiladigan, tanlangan filialda yotgan tovar — tanlangan filial hisobotida chiqadi."""
    p = _product(db, w['c'], name="Qishki kurtka", created_at=OLD)
    _stock(db, p, w['w1'], 40)                  # Chilonzorda yotibdi
    _stock(db, p, w['w2'], 5)
    _sale(db, w['admin'], w['c'], w['w2'], p, days_ago=1)   # Yunusobodda sotilmoqda
    c = client.login(w['admin'])
    d1 = c.get('/api/reports/dead-stock', params={'branch_id': w['b1'].id, 'months': 6}).json()
    assert [i['product_id'] for i in d1['items']] == [p.id] and d1['items'][0]['quantity'] == 40
    d2 = c.get('/api/reports/dead-stock', params={'branch_id': w['b2'].id, 'months': 6}).json()
    assert d2['items'] == []                                # Yunusobodda sotilgan
    d3 = c.get('/api/reports/dead-stock', params={'months': 6}).json()
    assert d3['items'] == []                                # butun korxona: sotilgan
    # dashboard soni ham shu bo'yicha (SQL count)
    assert c.get('/api/reports/dashboard', params={'branch_id': w['b1'].id}).json()['inventory']['dead_stock_count'] == 1
    assert c.get('/api/reports/dashboard', params={'branch_id': w['b2'].id}).json()['inventory']['dead_stock_count'] == 0


def test_dead_stock_count_matches_rows_and_movement_last_sold(db, w):
    from app.routers.reports import _dead_stock_rows, dead_stock_count
    p = _product(db, w['c'], created_at=OLD)
    q = _product(db, w['c'], created_at=OLD)
    _stock(db, p, w['w1'], 3)
    _stock(db, q, w['w1'], 4)
    new = _product(db, w['c'])                  # yangi mahsulot (oynadan keyin qo'shilgan) kirmaydi
    _stock(db, new, w['w1'], 9)
    assert dead_stock_count(db, w['c'].id, None) == len(_dead_stock_rows(db, w['c'].id, 6, None)) == 2
    # filial doirasida sotuv harakati (StockMovement.warehouse_id) hisobga olinadi
    db.add(StockMovement(product_id=p.id, warehouse_id=w['w1'].id, type=MovementType.OUT, qty_before=Decimal(5),
                         qty_after=Decimal(3), quantity=Decimal(2), reference_type="sale", reference_id=1,
                         created_at=datetime.now() - timedelta(days=2)))
    db.flush()
    assert dead_stock_count(db, w['c'].id, [w['w1'].id]) == 1
    assert dead_stock_count(db, w['c'].id, [w['w2'].id]) == 0     # w2 da qoldiq yo'q


# ── /inventory/stock, low-stock, low-stock-count ─────────────────────────────

def test_inventory_stock_filters_and_product_level_low_flag(client, db, mk, w):
    dead = mk.warehouse(w['c'], w['b1'], name="Arxiv", is_active=False)
    p = _product(db, w['c'], min_stock=10)
    _stock(db, p, w['w1'], 50)                  # bu qator o'zi "kam" emas, lekin ...
    _stock(db, p, w['w2'], 3)                   # ... jami 53 > 10 -> mahsulot kam emas
    _stock(db, p, dead, 1)
    q = _product(db, w['c'], min_stock=10)
    _stock(db, q, w['w1'], 4)
    _stock(db, q, w['w2'], 2)                   # jami 6 <= 10 -> kam
    c = client.login(w['admin'])
    rows = c.get('/api/inventory/stock', params={'limit': 100}).json()
    assert dead.id not in {r['warehouse_id'] for r in rows}
    flags = {(r['product_id'], r['warehouse_id']): r['is_low_stock'] for r in rows}
    assert flags[(p.id, w['w1'].id)] is False and flags[(p.id, w['w2'].id)] is False
    assert flags[(q.id, w['w1'].id)] is True and flags[(q.id, w['w2'].id)] is True
    low_only = c.get('/api/inventory/stock', params={'low_stock_only': True}).json()
    assert {r['product_id'] for r in low_only} == {q.id} and len(low_only) == 2
    one = c.get('/api/inventory/stock', params={'warehouse_id': w['w2'].id}).json()
    assert {r['warehouse_id'] for r in one} == {w['w2'].id}
    # filial tanlanganda mahsulot jami shu filial bo'yicha: Yunusobodda q = 2 <= 10, p = 3 <= 10
    br = c.get('/api/inventory/stock', params={'branch_id': w['b2'].id, 'low_stock_only': True}).json()
    assert {r['product_id'] for r in br} == {p.id, q.id}
    assert c.get('/api/inventory/stock', params={'warehouse_id': w['ow'].id}).status_code == 404


def test_inventory_stock_restricted_and_low_stock_endpoints_scope(client, db, w):
    p = _product(db, w['c'], min_stock=10)
    _stock(db, p, w['w1'], 4)
    _stock(db, p, w['w2'], 100)
    c = client.login(w['manager'])
    assert {r['warehouse_id'] for r in c.get('/api/inventory/stock').json()} == {w['w1'].id}
    assert c.get('/api/inventory/stock', params={'warehouse_id': w['w2'].id}).status_code == 403
    assert c.get('/api/inventory/low-stock-count').json() == {'count': 1}       # faqat o'z filiali: 4 <= 10
    assert c.get('/api/inventory/low-stock-count', params={'branch_id': w['b2'].id}).json() == {'count': 1}  # ruxsatsiz -> e'tiborsiz
    adm = client.login(w['admin'])
    assert adm.get('/api/inventory/low-stock-count').json() == {'count': 0}     # jami 104
    assert adm.get('/api/inventory/low-stock-count', params={'branch_id': w['b1'].id}).json() == {'count': 1}
    assert adm.get('/api/inventory/low-stock', params={'branch_id': w['b2'].id}).json() == []
    assert len(adm.get('/api/inventory/low-stock', params={'warehouse_id': w['w1'].id}).json()) == 1


def test_warehouses_branch_filter(client, db, w):
    adm = client.login(w['admin'])
    for url in ('/api/warehouses', '/api/inventory/warehouses'):
        got = adm.get(url, params={'branch_id': w['b2'].id}).json()
        assert [x['id'] for x in got] == [w['w2'].id]
        assert len(adm.get(url).json()) == 3                                     # parametrsiz xulq o'zgarmaydi
        assert adm.get(url, params={'branch_id': w['ob'].id}).status_code == 404


# ── /products/paginated ──────────────────────────────────────────────────────

def test_paginated_variant_product_sum_and_single_count(client, db, w):
    shirt = _product(db, w['c'], name="Ko'ylak", min_stock=0)
    for name, q in (("S", 2), ("M", 3), ("L", 5)):
        _stock(db, shirt, w['w1'], q, variant=_variant(db, shirt, name))
    r = client.login(w['admin']).get('/api/products/paginated', params={'warehouse_id': w['w1'].id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['total'] == 1 and len(body['items']) == 1
    assert Decimal(str(body['items'][0]['stock_quantity'])) == 10
    assert body['cost_values'] == {'UZS': 10 * 500.0}                            # qiymat 3 marta sanalmaydi


def test_paginated_low_filter_uses_unified_definition(client, db, w):
    zero_min = _product(db, w['c'], min_stock=0)
    low = _product(db, w['c'], min_stock=10)
    fine = _product(db, w['c'], min_stock=10)
    for p, q in ((zero_min, 0), (low, 4), (fine, 40)):
        _stock(db, p, w['w1'], q)
    # low: 3 variantli (har biri 1) - qator 3 ta, mahsulot 1 ta
    c = client.login(w['admin'])
    body = c.get('/api/products/paginated', params={'stock_status': 'kam-qolgan'}).json()
    assert [i['id'] for i in body['items']] == [low.id] and body['total'] == 1
    assert body['out_of_stock'] == 1


def test_paginated_cashier_other_branch_warehouse_403(client, db, w):
    p = _product(db, w['c'])
    _stock(db, p, w['w1'], 7)
    _stock(db, p, w['w2'], 9)
    c = client.login(w['cashier'])
    assert c.get('/api/products/paginated', params={'warehouse_id': w['w2'].id}).status_code == 403
    ok = c.get('/api/products/paginated', params={'warehouse_id': w['w1'].id})
    assert ok.status_code == 200 and Decimal(str(ok.json()['items'][0]['stock_quantity'])) == 7
    assert c.get('/api/products/paginated', params={'warehouse_id': w['ow'].id}).status_code == 404


def test_paginated_branch_param_and_empty_scope(client, db, w):
    p = _product(db, w['c'])
    _stock(db, p, w['w1'], 7)
    _stock(db, p, w['w2'], 9)
    adm = client.login(w['admin'])
    it = adm.get('/api/products/paginated', params={'branch_id': w['b2'].id}).json()['items'][0]
    assert Decimal(str(it['stock_quantity'])) == 9
    assert adm.get('/api/products/paginated', params={'branch_id': w['b1'].id, 'warehouse_id': w['w2'].id}).status_code == 400
    # filialida ombori yo'q xodim: qatorlarda ham, statistikada ham 0 (butun korxona emas)
    from app.models.branch import Branch
    empty_b = Branch(name="Bo'sh filial", company_id=w['c'].id)
    db.add(empty_b)
    db.flush()
    from app.models.user import User
    cash2 = User(name="K2", phone="998900000777", hashed_password="x", role=UserRole.cashier,
                 company_id=w['c'].id, branch_id=empty_b.id)
    db.add(cash2)
    db.flush()
    body = client.login(cash2).get('/api/products/paginated').json()
    assert Decimal(str(body['items'][0]['stock_quantity'])) == 0
    assert body['cost_values'] == {} and body['sale_values'] == {}


def test_get_product_stock_limited_to_own_branch_for_cashier(client, db, w):
    p = _product(db, w['c'])
    _stock(db, p, w['w1'], 7)
    _stock(db, p, w['w2'], 9)
    got = client.login(w['cashier']).get(f"/api/products/{p.id}").json()
    assert Decimal(str(got['stock_quantity'])) == 7
    got = client.login(w['admin']).get(f"/api/products/{p.id}").json()
    assert Decimal(str(got['stock_quantity'])) == 16


def test_products_list_warehouse_filter_variants_sum(client, db, w):
    shirt = _product(db, w['c'], name="Ko'ylak")
    for name, q in (("S", 2), ("M", 3), ("L", 5)):
        _stock(db, shirt, w['w1'], q, variant=_variant(db, shirt, name))
    got = client.login(w['admin']).get('/api/products/', params={'warehouse_id': w['w1'].id}).json()
    assert len(got) == 1 and Decimal(str(got[0]['stock_quantity'])) == 10
    ids = client.login(w['admin']).get('/api/products/ids', params={'warehouse_id': w['w1'].id}).json()
    assert ids == [shirt.id]                                                     # variantlar id'ni takrorlamaydi


# ── Statik tekshiruvlar (frontend) ───────────────────────────────────────────

def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


KEYS_T2_3 = ["warehouse.warehouseCol", "warehouse.branchCol", "warehouse.summaryValue", "warehouse.summaryQty", "warehouse.summarySku", "warehouse.limitNote", "warehouse.loadMore", "alert.byWarehouse", "profile.companyScope"]


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


def test_pending_i18n_keys_consistent_across_languages():
    data = _merged_i18n(KEYS_T2_3)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    for key in ('warehouse.warehouseCol', 'warehouse.branchCol', 'alert.byWarehouse', 'profile.companyScope'):
        assert key in data['uz']
    # {shown}/{total} o'rinbosarlari barcha tillarda bor
    for lang in ('uz', 'ru', 'en'):
        assert '{shown}' in data[lang]['warehouse.limitNote'] and '{total}' in data[lang]['warehouse.limitNote']


def test_frontend_warehouse_and_ombor_columns_and_keys():
    wh = _read('frontend/src/pages/admin/Warehouse.jsx')
    assert "key={`${i.product_id}-${i.variant_id ?? 0}-${i.warehouse_id ?? 0}`}" in wh
    assert "'warehouse.warehouseCol'" in wh and '/reports/inventory/summary' in wh and 'BranchSelect' in wh
    om = _read('frontend/src/pages/admin/Ombor.jsx')
    assert "key={`${it.product_id}-${it.variant_id ?? 0}-${it.warehouse_id ?? 0}`}" in om
    assert 'new Set(items.map(i => i.product_id))' in om and 'skip' in om and "'warehouse.warehouseCol'" in om
    assert 'key={it.product_id}' not in om


def test_frontend_alerts_layout_profile_products():
    al = _read('frontend/src/pages/admin/Alerts.jsx')
    assert "/inventory/low-stock'" in al and 'low_stock_only=true&limit=200' not in al and 'alert.byWarehouse' in al
    lay = _read('frontend/src/components/AdminLayout.jsx')
    assert "link.path === '/admin/warehouse'" not in lay and "link.path === '/admin/alerts'" in lay
    assert 'lowStockCount + expiredCount' in lay
    pr = _read('frontend/src/pages/admin/Profile.jsx')
    assert 'fmtCurrency(c.totals)' in pr and 'fmt(c.total)' not in pr and 'c.cashier_id' in pr
    assert '300_000' in pr and "document.visibilityState !== 'visible'" in pr and 'profile.companyScope' in pr
    prod = _read('frontend/src/pages/admin/Products.jsx')
    assert "params.append('branch_id', filterBranch)" in prod and '<BranchSelect' in prod
