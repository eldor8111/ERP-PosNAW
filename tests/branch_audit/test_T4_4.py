"""T4.4 — filial (ombor) bo'yicha min/max qoldiq va to'ldirish tavsiyasi.

Qamrov: effective_min/effective_max coalesce'i, ombor sozlamasi bo'yicha kam qoldiq (`/inventory/stock`,
`/low-stock-count`, `/low-stock`, dashboard), DELETE dan keyin korxona chegarasiga qaytish, sozlama yo'q bo'lsa
avvalgi (T2.3) natija, CRUD/bulk va 400/403/404 holatlari, replenishment hisobi (manba minimumi,
purchase_needed), transfer qoralamasi (pending, qoldiq o'zgarmaydi), AI xarid qoralamasi (warehouse_id),
ikki korxona izolyatsiyasi, migratsiya va i18n kalitlari.
"""
import importlib.util
import itertools
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.transfer import StockTransfer, TransferStatus
from app.models.user import UserRole
from app.models.warehouse_stock_setting import WarehouseStockSetting as WSS
from app.services import stock_report
from app.utils import stock_utils

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company, name=None, min_stock=0, max_stock=None, **kw):
    n = next(_seq)
    p = Product(name=name or f"Tovar {n}", sku=f"T44-{n}", barcode=f"B44-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"), min_stock=min_stock,
                max_stock=max_stock, **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal(str(qty)))
    db.add(sl)
    db.flush()
    return sl


def _qty(db, product, warehouse):
    v = db.query(func.coalesce(func.sum(StockLevel.quantity), 0)).filter(
        StockLevel.product_id == product.id, StockLevel.warehouse_id == warehouse.id).scalar()
    return float(v)


def _setting(db, company, warehouse, product, **kw):
    s = WSS(company_id=company.id, warehouse_id=warehouse.id, product_id=product.id, **kw)
    db.add(s)
    db.flush()
    return s


def _sale(db, user, company, warehouse, product, qty, days_ago=1):
    n = next(_seq)
    s = Sale(number=f"ST44-{n}", cashier_id=user.id, company_id=company.id, warehouse_id=warehouse.id,
             total_amount=Decimal(1000), paid_amount=Decimal(1000), payment_type=PaymentType.cash,
             status=SaleStatus.completed, created_at=datetime.now() - timedelta(days=days_ago))
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal(qty), unit_price=Decimal(1000),
                    cost_price=Decimal(0), subtotal=Decimal(1000), currency_code="UZS", exchange_rate=1,
                    warehouse_id=warehouse.id))
    db.flush()


@pytest.fixture
def w(db, mk):
    """Korxona A: Markaz filiali (ombor `center`), Yunusobod filiali (ombor `yun`), Chilonzor filiali (`chil`);
    admin, Yunusobod menejeri, Chilonzor menejeri, ombor xodimi. Korxona B: bitta tenant."""
    c = mk.company()
    b_c, b_y, b_ch = mk.branch(c, name="Markaz"), mk.branch(c, name="Yunusobod"), mk.branch(c, name="Chilonzor")
    center = mk.warehouse(c, b_c, name="Markaziy ombor")
    yun = mk.warehouse(c, b_y, name="Yunusobod ombori")
    chil = mk.warehouse(c, b_ch, name="Chilonzor ombori")
    admin = mk.user(c, role=UserRole.admin)
    mgr_y = mk.user(c, role=UserRole.manager, branch=b_y)
    mgr_ch = mk.user(c, role=UserRole.manager, branch=b_ch)
    wh_user = mk.user(c, role=UserRole.warehouse, branch=b_y)
    oc, ob, ow, ou = mk.tenant()
    return dict(c=c, b_c=b_c, b_y=b_y, b_ch=b_ch, center=center, yun=yun, chil=chil, admin=admin, mgr_y=mgr_y,
                mgr_ch=mgr_ch, wh_user=wh_user, oc=oc, ow=ow, ou=ou)


def _rows(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── effective_min / effective_max ────────────────────────────────────────────

def test_effective_min_max_coalesce(db, w):
    c = w['c']
    p1 = _product(db, c, min_stock=5, max_stock=40)
    p2 = _product(db, c, min_stock=7, max_stock=None)
    _setting(db, c, w['yun'], p1, min_qty=Decimal('50'), max_qty=Decimal('200'))
    _setting(db, c, w['yun'], p2, reorder_qty=Decimal('9'))   # min/max NULL -> mahsulot chegarasi
    q = (db.query(Product.id, stock_utils.effective_min(), stock_utils.effective_max())
         .outerjoin(WSS, (WSS.product_id == Product.id) & (WSS.warehouse_id == w['yun'].id))
         .filter(Product.id.in_([p1.id, p2.id])).order_by(Product.id))
    got = {pid: (float(mn), None if mx is None else float(mx)) for pid, mn, mx in q.all()}
    assert got[p1.id] == (50.0, 200.0)
    assert got[p2.id] == (7.0, None)


# ── Kam qoldiq (acceptance 1, 2, 3, 9) ───────────────────────────────────────

def _scenario(db, w):
    """Coca-Cola: Product.min_stock=5. Yunusobodda 3 dona (min_qty=50), Chilonzorda 10 dona (sozlama yo'q)."""
    c = w['c']
    cola = _product(db, c, name="Coca-Cola 1.5L", min_stock=5)
    _stock(db, cola, w['yun'], 3)
    _stock(db, cola, w['chil'], 10)
    _stock(db, cola, w['center'], 2000)
    _setting(db, c, w['yun'], cola, min_qty=Decimal('50'))
    return cola


def test_low_stock_only_uses_warehouse_min(client, db, w):
    cola = _scenario(db, w)
    c = client.login(w['admin'])
    data = _rows(c.get('/api/inventory/stock', params={'low_stock_only': 'true'}))
    assert [(r['warehouse_id'], r['product_id']) for r in data] == [(w['yun'].id, cola.id)]
    assert data[0]['min_stock'] == 50 and data[0]['is_low_stock'] is True

    full = {r['warehouse_id']: r for r in _rows(c.get('/api/inventory/stock'))}
    assert full[w['yun'].id]['is_low_stock'] is True and full[w['yun'].id]['min_stock'] == 50
    # Boshqa omborlarda: min_qty yo'q, Product.min_stock=5, 10 va 2000 dona -> kam emas
    assert full[w['chil'].id]['is_low_stock'] is False and full[w['chil'].id]['min_stock'] == 5
    assert full[w['center'].id]['is_low_stock'] is False
    assert full[w['chil'].id]['max_stock'] is None


def test_delete_setting_returns_to_product_min(client, db, w):
    cola = _scenario(db, w)
    c = client.login(w['admin'])
    assert _rows(c.get('/api/inventory/low-stock-count'))['count'] == 1
    r = c.delete(f"/api/inventory/stock-settings/{w['yun'].id}/{cola.id}")
    assert r.status_code == 200 and r.json() == {'deleted': True}
    assert db.query(WSS).count() == 0
    # Product.min_stock=5, jami 2013 dona -> kam emas
    assert _rows(c.get('/api/inventory/low-stock-count'))['count'] == 0
    assert _rows(c.get('/api/inventory/stock', params={'low_stock_only': 'true'})) == []
    # Yunusobod ombori doirasida ham: 3 dona <= 5 -> kam (korxona chegarasi)
    low = _rows(c.get('/api/inventory/stock', params={'low_stock_only': 'true', 'warehouse_id': w['yun'].id}))
    assert len(low) == 1 and low[0]['min_stock'] == 5


def test_counts_consistent_inventory_dashboard_lowlist(client, db, w):
    cola = _scenario(db, w)
    c = client.login(w['admin'])
    n_inv = _rows(c.get('/api/inventory/low-stock-count'))['count']
    n_util = stock_utils.low_stock_count(db, w['c'].id, None)
    d = c.get('/api/dashboard/summary')
    assert d.status_code == 200, d.text
    assert n_inv == n_util == d.json()['low_stock_count'] == 1
    lst = _rows(c.get('/api/inventory/low-stock'))
    assert len(lst) == 1 and lst[0]['product_id'] == cola.id and lst[0]['scope'] == 'warehouse'
    assert lst[0]['warehouse_id'] == w['yun'].id and float(lst[0]['min_stock']) == 50
    # filial doirasi: Chilonzor sozlamasiz -> 0, Yunusobod -> 1
    assert _rows(c.get('/api/inventory/low-stock-count', params={'branch_id': w['b_ch'].id}))['count'] == 0
    assert _rows(c.get('/api/inventory/low-stock-count', params={'branch_id': w['b_y'].id}))['count'] == 1


def test_no_settings_equals_t23_result(db, w):
    """Sozlama jadvali bo'sh -> stock_report (T2.3) bilan bir xil natija (acceptance 9)."""
    c = w['c']
    a = _product(db, c, min_stock=10)
    b = _product(db, c, min_stock=4)
    d = _product(db, c, min_stock=0)
    _stock(db, a, w['yun'], 3)
    _stock(db, a, w['chil'], 6)      # jami 9 <= 10 -> kam
    _stock(db, b, w['yun'], 9)       # 9 > 4
    _stock(db, d, w['yun'], 0)       # min=0 -> hisobga olinmaydi
    for scope in (None, [w['yun'].id], [w['chil'].id], [w['yun'].id, w['chil'].id], []):
        assert stock_utils.low_stock_count(db, c.id, scope) == stock_report.low_stock_count(db, c.id, scope)
        mine = sorted(r['product_id'] for r in stock_utils.low_stock_products(db, c.id, scope))
        ref = sorted(r['product_id'] for r in stock_report.low_stock_products(db, c.id, scope))
        assert mine == ref
    assert stock_utils.low_stock_count(db, c.id, None) == 1


def test_override_zero_min_disables_alert_and_remainder_grouping(db, w):
    """min_qty=0 — shu ombor ogohlantirishdan chiqadi va yig'indiga kirmaydi; qolganlari yig'iladi."""
    c = w['c']
    p = _product(db, c, min_stock=10)
    _stock(db, p, w['yun'], 1)
    _stock(db, p, w['chil'], 8)
    assert stock_utils.low_stock_count(db, c.id, None) == 1          # 9 <= 10
    _setting(db, c, w['yun'], p, min_qty=Decimal('0'))
    assert stock_utils.low_stock_count(db, c.id, None) == 1          # Yunusobod chiqdi; qolgan 8 <= 10 (center ham bor)
    _stock(db, p, w['center'], 5)
    assert stock_utils.low_stock_count(db, c.id, None) == 0          # 8+5 = 13 > 10
    assert stock_utils.low_stock_count(db, c.id, [w['yun'].id]) == 0  # doirada faqat sozlamali ombor


def test_override_without_stock_row_is_low(db, w):
    c = w['c']
    p = _product(db, c, min_stock=0)
    _setting(db, c, w['yun'], p, min_qty=Decimal('5'))
    assert stock_utils.low_stock_count(db, c.id, None) == 1
    assert stock_utils.low_stock_count(db, c.id, [w['chil'].id]) == 0


# ── CRUD, validatsiya, ruxsatlar (acceptance 6, 7) ───────────────────────────

def test_put_get_settings_and_audit_values(client, db, w):
    p = _product(db, w['c'], name="Pepsi", min_stock=5, max_stock=30)
    _stock(db, p, w['yun'], 4)
    c = client.login(w['admin'])
    r = c.put(f"/api/inventory/stock-settings/{w['yun'].id}/{p.id}",
              json={'min_qty': 20, 'max_qty': 100, 'reorder_qty': 50, 'source_warehouse_id': w['center'].id})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b['min_qty'], b['max_qty'], b['reorder_qty'], b['source_warehouse_id']) == (20, 100, 50, w['center'].id)
    assert b['company_min_stock'] == 5 and b['company_max_stock'] == 30 and b['current_qty'] == 4
    # qisman yangilash: faqat min o'zgaradi, qolganlari saqlanadi
    r = c.put(f"/api/inventory/stock-settings/{w['yun'].id}/{p.id}", json={'min_qty': 10})
    assert r.status_code == 200 and r.json()['max_qty'] == 100 and r.json()['min_qty'] == 10
    lst = _rows(c.get('/api/inventory/stock-settings', params={'warehouse_id': w['yun'].id, 'search': 'Pepsi'}))
    assert len(lst) == 1 and lst[0]['min_qty'] == 10 and lst[0]['source_warehouse_id'] == w['center'].id
    # barcha maydon null -> qator o'chadi
    r = c.put(f"/api/inventory/stock-settings/{w['yun'].id}/{p.id}",
              json={'min_qty': None, 'max_qty': None, 'reorder_qty': None, 'source_warehouse_id': None})
    assert r.status_code == 200 and r.json()['min_qty'] is None
    assert db.query(WSS).count() == 0
    only = _rows(c.get('/api/inventory/stock-settings', params={'warehouse_id': w['yun'].id, 'only_configured': 'true'}))
    assert only == []


def test_validation_errors_400(client, db, w):
    p = _product(db, w['c'])
    c = client.login(w['admin'])
    url = f"/api/inventory/stock-settings/{w['yun'].id}/{p.id}"
    assert c.put(url, json={'min_qty': 10, 'max_qty': 5}).status_code == 400
    assert c.put(url, json={'min_qty': -1}).status_code == 400
    assert c.put(url, json={'max_qty': -5}).status_code == 400
    assert c.put(url, json={'source_warehouse_id': w['yun'].id}).status_code == 400
    # max faqat berilsa, mavjud min bilan solishtiriladi
    assert c.put(url, json={'min_qty': 10}).status_code == 200
    assert c.put(url, json={'max_qty': 3}).status_code == 400
    assert db.query(WSS).filter(WSS.max_qty.isnot(None)).count() == 0


def test_cross_company_404(client, db, w):
    p_own = _product(db, w['c'])
    p_other = _product(db, w['oc'])
    c = client.login(w['admin'])
    assert c.put(f"/api/inventory/stock-settings/{w['ow'].id}/{p_own.id}", json={'min_qty': 1}).status_code == 404
    assert c.put(f"/api/inventory/stock-settings/{w['yun'].id}/{p_other.id}", json={'min_qty': 1}).status_code == 404
    assert c.put(f"/api/inventory/stock-settings/{w['yun'].id}/{p_own.id}",
                 json={'min_qty': 1, 'source_warehouse_id': w['ow'].id}).status_code == 404
    assert c.delete(f"/api/inventory/stock-settings/{w['ow'].id}/{p_own.id}").status_code == 404
    assert c.get('/api/inventory/stock-settings', params={'warehouse_id': w['ow'].id}).status_code == 404
    assert c.get('/api/inventory/replenishment', params={'warehouse_id': w['ow'].id}).status_code == 404
    assert c.get('/api/inventory/replenishment', params={'source_warehouse_id': w['ow'].id}).status_code == 404
    # B korxona xodimi A korxona omboriga yoza olmaydi
    assert client.login(w['ou']).put(f"/api/inventory/stock-settings/{w['yun'].id}/{p_own.id}",
                                      json={'min_qty': 1}).status_code == 404
    assert db.query(WSS).count() == 0


def test_branch_and_role_restrictions_403(client, db, w):
    p = _product(db, w['c'])
    url_ch = f"/api/inventory/stock-settings/{w['chil'].id}/{p.id}"
    url_y = f"/api/inventory/stock-settings/{w['yun'].id}/{p.id}"
    # Yunusobod menejeri Chilonzor omboriga yoza olmaydi, o'z omboriga yoza oladi
    c = client.login(w['mgr_y'])
    assert c.put(url_ch, json={'min_qty': 5}).status_code == 403
    assert c.delete(url_ch).status_code == 403
    assert c.put(url_y, json={'min_qty': 5}).status_code == 200
    assert c.get('/api/inventory/stock-settings', params={'warehouse_id': w['chil'].id}).status_code == 403
    r = c.put('/api/inventory/stock-settings/bulk', json={'warehouse_id': w['chil'].id, 'items': []})
    assert r.status_code == 403
    # ombor xodimi faqat o'qiydi
    cw = client.login(w['wh_user'])
    assert cw.put(url_y, json={'min_qty': 9}).status_code == 403
    assert cw.delete(url_y).status_code == 403
    assert cw.get('/api/inventory/stock-settings', params={'warehouse_id': w['yun'].id}).status_code == 200
    assert float(db.query(WSS).one().min_qty) == 5


def test_bulk_save_with_errors(client, db, w):
    p1, p2, p3 = (_product(db, w['c']) for _ in range(3))
    other = _product(db, w['oc'])
    c = client.login(w['admin'])
    r = c.put('/api/inventory/stock-settings/bulk', json={'warehouse_id': w['yun'].id, 'items': [
        {'product_id': p1.id, 'min_qty': 10, 'max_qty': 50},
        {'product_id': p2.id, 'min_qty': 30, 'max_qty': 10},      # 400
        {'product_id': other.id, 'min_qty': 1},                   # 404
        {'product_id': p3.id, 'min_qty': 2, 'source_warehouse_id': w['center'].id},
    ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['saved'] == 2
    assert {(e['product_id'], e['status']) for e in body['errors']} == {(p2.id, 400), (other.id, 404)}
    assert db.query(WSS).count() == 2
    assert client.login(w['admin']).put('/api/inventory/stock-settings/bulk', json={
        'warehouse_id': w['yun'].id, 'items': [{'product_id': p1.id}] * 1001}).status_code == 422


def test_db_check_constraints(db, w):
    p = _product(db, w['c'])
    for kw in ({'min_qty': Decimal('-1')}, {'min_qty': Decimal('10'), 'max_qty': Decimal('5')},
               {'source_warehouse_id': w['yun'].id}):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                _setting(db, w['c'], w['yun'], p, **kw)
    _setting(db, w['c'], w['yun'], p, min_qty=Decimal('1'))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _setting(db, w['c'], w['yun'], p, min_qty=Decimal('2'))   # UNIQUE (warehouse, product)


# ── To'ldirish tavsiyasi (acceptance 4) ──────────────────────────────────────

def _repl_scenario(db, w):
    c = w['c']
    cola = _product(db, c, name="Coca-Cola 1.5L", min_stock=0)
    _stock(db, cola, w['center'], 2000)
    _stock(db, cola, w['yun'], 3)
    _setting(db, c, w['yun'], cola, min_qty=Decimal('50'), max_qty=Decimal('200'),
             source_warehouse_id=w['center'].id)
    return cola


def test_replenishment_basic_197(client, db, w):
    cola = _repl_scenario(db, w)
    c = client.login(w['admin'])
    items = _rows(c.get('/api/inventory/replenishment'))
    assert len(items) == 1
    it = items[0]
    assert (it['warehouse_id'], it['product_id']) == (w['yun'].id, cola.id)
    assert it['current_qty'] == 3 and it['min'] == 50 and it['max'] == 200 and it['shortage'] == 47
    assert it['need_qty'] == 197 and it['transfer_qty'] == 197 and it['purchase_needed'] == 0
    assert it['source_warehouse_id'] == w['center'].id and it['source_qty'] == 2000
    assert _rows(c.get('/api/inventory/replenishment', params={'branch_id': w['b_ch'].id})) == []
    assert len(_rows(c.get('/api/inventory/replenishment', params={'warehouse_id': w['yun'].id}))) == 1


def test_replenishment_source_keeps_own_minimum_and_purchase_needed(client, db, w):
    c_ = w['c']
    p = _product(db, c_, name="Sut", min_stock=0)
    _stock(db, p, w['center'], 120)
    _stock(db, p, w['yun'], 3)
    _setting(db, c_, w['center'], p, min_qty=Decimal('50'))
    _setting(db, c_, w['yun'], p, min_qty=Decimal('50'), max_qty=Decimal('200'))
    c = client.login(w['admin'])
    # manba qatorda yo'q -> so'rovdagi source_warehouse_id ishlatiladi
    it = _rows(c.get('/api/inventory/replenishment', params={
        'warehouse_id': w['yun'].id, 'source_warehouse_id': w['center'].id}))[0]
    assert it['need_qty'] == 197
    assert it['transfer_qty'] == 70            # 120 - 50 (manba o'z minimumidan pastga tushmaydi)
    assert it['purchase_needed'] == 127
    assert it['source_min'] == 50
    # manba ko'rsatilmasa — hammasi xaridga
    it = _rows(c.get('/api/inventory/replenishment', params={'warehouse_id': w['yun'].id}))[0]
    assert it['source_warehouse_id'] is None and it['transfer_qty'] == 0 and it['purchase_needed'] == 197


def test_replenishment_source_shared_between_destinations(client, db, w):
    c_ = w['c']
    p = _product(db, c_, name="Un", min_stock=0)
    _stock(db, p, w['center'], 100)
    _stock(db, p, w['yun'], 0)
    _stock(db, p, w['chil'], 10)
    _setting(db, c_, w['yun'], p, min_qty=Decimal('10'), max_qty=Decimal('70'), source_warehouse_id=w['center'].id)
    _setting(db, c_, w['chil'], p, min_qty=Decimal('20'), max_qty=Decimal('60'), source_warehouse_id=w['center'].id)
    items = _rows(client.login(w['admin']).get('/api/inventory/replenishment'))
    by = {i['warehouse_id']: i for i in items}
    # eng katta yetishmovchilik (Yunusobod: 10 - 0) birinchi emas — farq: yun=10, chil=10 -> tartib barqaror
    assert by[w['yun'].id]['need_qty'] == 70 and by[w['chil'].id]['need_qty'] == 50
    assert round(sum(i['transfer_qty'] for i in items), 3) == 100      # manba qoldig'idan ortiq berilmaydi
    assert round(sum(i['purchase_needed'] for i in items), 3) == 20


def test_replenishment_max_fallbacks(client, db, w):
    c_ = w['c']
    p_reorder = _product(db, c_, name="A", min_stock=0)
    p_min = _product(db, c_, name="B", min_stock=0)
    p_pmax = _product(db, c_, name="C", min_stock=0, max_stock=500)
    for p in (p_reorder, p_min, p_pmax):
        _stock(db, p, w['center'], 1000)
        _stock(db, p, w['yun'], 4)
    _setting(db, c_, w['yun'], p_reorder, min_qty=Decimal('10'), reorder_qty=Decimal('25'))
    _setting(db, c_, w['yun'], p_min, min_qty=Decimal('10'))
    _setting(db, c_, w['yun'], p_pmax, min_qty=Decimal('10'))
    c = client.login(w['admin'])
    q = {'source_warehouse_id': w['center'].id}
    by = {i['product_id']: i for i in _rows(c.get('/api/inventory/replenishment', params=q))}
    assert by[p_reorder.id]['need_qty'] == 25          # max yo'q -> reorder_qty
    assert by[p_min.id]['need_qty'] == 6               # max, reorder yo'q -> min - qoldiq
    assert by[p_pmax.id]['need_qty'] == 6              # Product.max_stock faqat use_product_max bilan
    q['use_product_max'] = 'true'
    by = {i['product_id']: i for i in _rows(c.get('/api/inventory/replenishment', params=q))}
    assert by[p_pmax.id]['need_qty'] == 496 and by[p_pmax.id]['max'] == 500


def test_replenishment_branch_scope_and_isolation(client, db, w):
    _repl_scenario(db, w)
    # begona korxona ma'lumoti ko'rinmaydi
    op = _product(db, w['oc'])
    _stock(db, op, w['ow'], 1)
    _setting(db, w['oc'], w['ow'], op, min_qty=Decimal('9'))
    own = _rows(client.login(w['mgr_y']).get('/api/inventory/replenishment'))
    assert [i['warehouse_id'] for i in own] == [w['yun'].id]
    assert _rows(client.login(w['mgr_ch']).get('/api/inventory/replenishment')) == []
    assert client.login(w['mgr_ch']).get('/api/inventory/replenishment',
                                         params={'warehouse_id': w['yun'].id}).status_code == 403
    other = _rows(client.login(w['ou']).get('/api/inventory/replenishment'))
    assert [i['warehouse_id'] for i in other] == [w['ow'].id]


# ── Transfer qoralamasi (acceptance 5) ───────────────────────────────────────

def test_replenishment_transfer_draft_pending_stock_unchanged(client, db, w):
    cola = _repl_scenario(db, w)
    c = client.login(w['admin'])
    r = c.post('/api/inventory/replenishment/transfers', json={
        'source_warehouse_id': w['center'].id, 'destination_warehouse_id': w['yun'].id,
        'items': [{'product_id': cola.id, 'qty': 197}]})
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'pending'
    t = db.get(StockTransfer, r.json()['id'])
    assert t.status == TransferStatus.pending and len(t.items) == 1 and float(t.items[0].quantity) == 197
    assert _qty(db, cola, w['center']) == 2000 and _qty(db, cola, w['yun']) == 3
    # transfer ro'yxatida ko'rinadi
    lst = c.get('/api/transfers')
    assert lst.status_code == 200 and any(x['id'] == t.id for x in lst.json())


def test_replenishment_transfer_errors(client, db, w):
    cola = _repl_scenario(db, w)
    p_other = _product(db, w['oc'])
    c = client.login(w['admin'])
    base = {'source_warehouse_id': w['center'].id, 'destination_warehouse_id': w['yun'].id}
    assert c.post('/api/inventory/replenishment/transfers', json={
        'source_warehouse_id': w['yun'].id, 'destination_warehouse_id': w['yun'].id,
        'items': [{'product_id': cola.id, 'qty': 1}]}).status_code == 400
    assert c.post('/api/inventory/replenishment/transfers', json={
        **base, 'destination_warehouse_id': w['ow'].id, 'items': [{'product_id': cola.id, 'qty': 1}]}).status_code == 404
    assert c.post('/api/inventory/replenishment/transfers', json={
        **base, 'items': [{'product_id': p_other.id, 'qty': 1}]}).status_code == 404
    assert c.post('/api/inventory/replenishment/transfers', json={
        **base, 'items': [{'product_id': cola.id, 'qty': 0}]}).status_code == 400
    # manba boshqa filial (Markaz) — Yunusobod menejeri uchun 403
    assert client.login(w['mgr_y']).post('/api/inventory/replenishment/transfers', json={
        **base, 'items': [{'product_id': cola.id, 'qty': 1}]}).status_code == 403
    assert client.login(w['wh_user']).post('/api/inventory/replenishment/transfers', json={
        **base, 'items': [{'product_id': cola.id, 'qty': 1}]}).status_code == 403
    assert db.query(StockTransfer).count() == 0


# ── AI xarid qoralamasi (acceptance 8) ───────────────────────────────────────

def test_ai_draft_po_with_warehouse_id(db, w):
    from app.services.ai_tools_actions import DraftPurchaseOrderTool
    c_ = w['c']
    p = _product(db, c_, name="Suv", min_stock=0)
    _stock(db, p, w['yun'], 3)
    _stock(db, p, w['chil'], 500)
    _setting(db, c_, w['yun'], p, min_qty=Decimal('50'), max_qty=Decimal('200'))
    _sale(db, w['admin'], c_, w['yun'], p, 14, days_ago=2)       # 1 dona/kun -> 14 kunlik ehtiyoj 14
    _sale(db, w['admin'], c_, w['chil'], p, 14, days_ago=2)
    tool = DraftPurchaseOrderTool()

    # warehouse_id berilmagan: eski xatti-harakat (ombor kesimida tezlik/qoldiq, chegara hisobga olinmaydi)
    old = tool.execute(db, c_.id, w['admin'])
    wh_old = {i['warehouse_id']: i for i in old['action']['items']}
    assert w['chil'].id not in wh_old                        # 500 dona yetarli
    assert wh_old[w['yun'].id]['suggested_qty'] == 11        # 14 - 3
    assert old['action']['warehouse_id'] is None

    res = tool.execute(db, c_.id, w['admin'], warehouse_id=w['yun'].id)
    items = res['action']['items']
    assert res['action']['warehouse_id'] == w['yun'].id
    assert [i['warehouse_id'] for i in items] == [w['yun'].id]
    assert items[0]['current_stock'] == 3
    assert items[0]['suggested_qty'] == 197                  # max_qty 200 - 3 (ombor chegarasi)

    # sotuvi yo'q, lekin min dan past mahsulot ham tushadi; boshqa ombor mahsuloti tushmaydi
    q = _product(db, c_, name="Choy", min_stock=0)
    _stock(db, q, w['yun'], 1)
    _setting(db, c_, w['yun'], q, min_qty=Decimal('8'))
    res = tool.execute(db, c_.id, w['admin'], warehouse_id=w['yun'].id)
    by = {i['product_id']: i for i in res['action']['items']}
    assert by[q.id]['suggested_qty'] == 7 and by[p.id]['suggested_qty'] == 197

    # begona korxona ombori
    bad = tool.execute(db, c_.id, w['admin'], warehouse_id=w['ow'].id)
    assert 'action' not in bad


# ── Migratsiya, model va i18n ────────────────────────────────────────────────

def test_migration_file():
    path = os.path.join(ROOT, 'alembic', 'versions', 't4_4_warehouse_stock_settings.py')
    spec = importlib.util.spec_from_file_location('t4_4_mig', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == 't4_4' and mod.down_revision == 't4_3'
    src = open(path, encoding='utf-8').read()
    for needle in ('warehouse_stock_settings', 'uq_wss_warehouse_product', 'ck_wss_max_ge_min',
                   'ck_wss_source_not_self', 'ix_wss_product', 'DROP TABLE'):
        assert needle in src


def test_i18n_pending_keys():
    path = os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T4.4.json')
    data = json.load(open(path, encoding='utf-8'))
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and data['uz']
    for lang in data.values():
        assert all(isinstance(v, str) and v for v in lang.values())
    # frontendda ishlatilgan har bir yangi kalit pending faylda bor
    import re
    src = open(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'Operations.jsx'), encoding='utf-8').read()
    used = set(re.findall(r"tf?\(\s*'(replen\.[a-zA-Z0-9_.]+)'", src))
    assert used and used <= set(data['uz'])
