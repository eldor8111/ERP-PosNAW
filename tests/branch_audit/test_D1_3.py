"""D1.3 — Dorixona kirimi: seriya/muddat majburiy, qatorni seriyalarga bo'lish, ustama va narx chegarasi.

Har bir qoida FAQAT dorixona moduli yoqilgan korxonada; oddiy korxona avvalgidek (regressiya).
"""
import itertools
import json
import pathlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.category import Category
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.services.document_numbers import tashkent_today

ROOT = pathlib.Path(__file__).resolve().parents[2]
_seq = itertools.count(1)


# ─── yordamchilar ───

def _enable(db, company, **settings):
    company.pharmacy_enabled = True
    if settings:
        company.pharmacy_settings = settings
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _product(db, company, category=None, **kw):
    n = next(_seq)
    p = Product(name=f'Dori {n}', sku=f'SKU-D13-{n}', barcode=f'BC-D13-{n}', company_id=company.id,
                cost_price=kw.pop('cost_price', 100), sale_price=kw.pop('sale_price', 200),
                category_id=category.id if category else None, **kw)
    db.add(p)
    db.flush()
    return p


def _category(db, company, markup=None, parent=None):
    c = Category(name=f'Kat {next(_seq)}', company_id=company.id, markup_pct=markup,
                 parent_id=parent.id if parent else None)
    db.add(c)
    db.flush()
    return c


def _supplier(db, company):
    s = Supplier(name=f'Taminotchi {company.id}-{next(_seq)}', company_id=company.id, is_active=True,
                 debt_balance=Decimal(0), debt_balances={})
    db.add(s)
    db.flush()
    return s


def _iso(days):
    return (tashkent_today() + timedelta(days=days)).isoformat() + 'T00:00:00'


@pytest.fixture
def world(db, mk):
    a, ab, aw, aadmin = mk.tenant()           # A: oddiy korxona
    ph, pb, pw, padmin = mk.tenant()          # P: dorixona
    other, ob, ow, oadmin = mk.tenant()       # B: boshqa dorixona (izolyatsiya)
    _enable(db, ph)
    _enable(db, other)
    return dict(a=a, aw=aw, aadmin=aadmin, asup=_supplier(db, a),
                ph=ph, pw=pw, padmin=padmin, psup=_supplier(db, ph),
                other=other, oadmin=oadmin)


def _create_po(client, user, wh, sup, product, qty=100, cost=10000, status='sent', **item_extra):
    item = {'product_id': product.id, 'qty_ordered': qty, 'unit_cost': cost}
    item.update(item_extra)
    return client.login(user).post('/api/purchase-orders', json={
        'supplier_id': sup.id, 'warehouse_id': wh.id, 'status': status, 'items': [item]})


def _receive(client, user, po_id, items, **extra):
    return client.login(user).post(f'/api/purchase-orders/{po_id}/receive', json={'items': items, **extra})


def _batches(db, product):
    return db.query(Batch).filter(Batch.product_id == product.id).order_by(Batch.id).all()


# ─── 1. Oddiy korxona: avvalgidek ───

def test_regular_company_receives_without_lot_or_expiry(client, db, world):
    w = world
    p = _product(db, w['a'])
    po = _create_po(client, w['aadmin'], w['aw'], w['asup'], p).json()
    r = _receive(client, w['aadmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 100}])
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'received'
    assert r.json()['warnings'] == []
    b = _batches(db, p)
    assert len(b) == 1 and b[0].lot_number == f"PO-{po['number']}" and b[0].expiry_date is None


def test_regular_company_ignores_markup_and_max_markup(client, db, world):
    w = world
    cat = _category(db, w['a'], markup=50)
    p = _product(db, w['a'], category=cat, sale_price=999999)
    po = _create_po(client, w['aadmin'], w['aw'], w['asup'], p, qty=10, cost=10000).json()
    r = _receive(client, w['aadmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 10}])
    assert r.status_code == 200, r.text
    db.refresh(p)
    assert p.sale_price == 999999          # ustama ham, chegara ham qo'llanmadi
    assert p.cost_price == 10000


def test_regular_company_past_expiry_accepted(client, db, world):
    w = world
    p = _product(db, w['a'])
    po = _create_po(client, w['aadmin'], w['aw'], w['asup'], p).json()
    r = _receive(client, w['aadmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 100,
                                                  'lot_number': 'X1', 'expiry_date': _iso(-5)}])
    assert r.status_code == 200, r.text


def test_regular_company_manual_receive_unchanged(client, db, world):
    w = world
    p = _product(db, w['a'])
    r = client.login(w['aadmin']).post('/api/inventory/receive', json={
        'warehouse_id': w['aw'].id, 'items': [{'product_id': p.id, 'quantity': 5}]})
    assert r.status_code == 200, r.text
    assert 'warnings' not in r.json()


# ─── 2. Dorixona: seriya va muddat (P.15: ikkalasi ham ixtiyoriy) ───

def test_pharmacy_receive_lot_and_expiry_optional(client, db, world):
    # P.5: seriya ixtiyoriy (bo'sh bo'lsa partiya "PO-<raqam>" nomini oladi); P.15: muddati yo'q tovarlar ham bor —
    # muddatsiz qabul muddatsiz partiya bo'lib yoziladi
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p).json()
    iid = po['items'][0]['id']
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': iid, 'qty_received': 60, 'lot_number': 'S1'}])
    assert r.status_code == 200, r.text
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': iid, 'qty_received': 40, 'lot_number': '  ',
                                                  'expiry_date': _iso(300)}])
    assert r.status_code == 200, r.text
    b = _batches(db, p)
    assert [(x.lot_number, x.expiry_date is None) for x in b][0] == ('S1', True)
    assert b[1].lot_number.startswith('PO-') and b[1].expiry_date is not None


def test_pharmacy_past_expiry_is_warning_not_rejected(client, db, world):
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p).json()
    iid = po['items'][0]['id']
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': iid, 'qty_received': 40, 'lot_number': 'S1',
                                                  'expiry_date': _iso(-1)}])
    assert r.status_code == 200, r.text
    assert any("o'tgan" in x for x in r.json()['warnings']), r.json()
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': iid, 'qty_received': 40, 'lot_number': 'S2',
                                                  'expiry_date': _iso(0)}])
    assert r.status_code == 200, r.text
    assert len(_batches(db, p)) == 2


def test_pharmacy_single_lot_format_still_works(client, db, world):
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p).json()
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 100,
                                                  'lot_number': 'S1', 'expiry_date': _iso(400)}])
    assert r.status_code == 200, r.text
    b = _batches(db, p)
    assert len(b) == 1 and b[0].lot_number == 'S1' and b[0].quantity == 100


def test_pharmacy_lot_and_expiry_from_po_item(client, db, world):
    """Xarid qatorida seriya/muddat oldindan berilgan bo'lsa, qabulda qayta kiritish shart emas."""
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p, lot_number='PRE1', expiry_date=_iso(200)).json()
    assert po['items'][0]['lot_number'] == 'PRE1'
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 100}])
    assert r.status_code == 200, r.text
    assert _batches(db, p)[0].lot_number == 'PRE1'


def test_pharmacy_create_received_lot_and_expiry_optional(client, db, world):
    w = world
    p = _product(db, w['ph'])
    r = _create_po(client, w['padmin'], w['pw'], w['psup'], p, status='received')        # P.15: muddatsiz ham
    assert r.status_code == 200, r.text
    r = _create_po(client, w['padmin'], w['pw'], w['psup'], p, status='received',
                   lot_number='Q1', expiry_date=_iso(100))
    assert r.status_code == 200, r.text
    b = _batches(db, p)
    assert len(b) == 2 and b[0].expiry_date is None and b[1].lot_number == 'Q1'


# ─── 3. Qatorni seriyalarga bo'lish ───

def test_pharmacy_split_lots_60_40_creates_two_batches(client, db, world):
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p).json()
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'lots': [
        {'lot_number': 'A1', 'expiry_date': _iso(300), 'qty': 60},
        {'lot_number': 'B2', 'expiry_date': _iso(500), 'manufacture_date': _iso(-30), 'qty': 40},
    ]}])
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'received'
    b = _batches(db, p)
    assert [(x.lot_number, x.quantity) for x in b] == [('A1', 60), ('B2', 40)]
    assert b[1].manufacture_date is not None
    assert all(x.po_id == po['id'] for x in b)
    st = db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id == w['pw'].id).one()
    assert st.quantity == 100
    assert r.json()['items'][0]['qty_received'] in (100, '100', '100.000', 100.0)


def test_split_lots_validation_names_the_lot(client, db, world):
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p).json()
    iid = po['items'][0]['id']
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': iid, 'lots': [
        {'lot_number': 'A1', 'expiry_date': _iso(300), 'qty': 60},
        {'lot_number': 'B2', 'expiry_date': _iso(300), 'manufacture_date': _iso(400), 'qty': 40}]}])
    assert r.status_code == 400 and '2-seriya' in r.json()['detail']        # ishlab chiqarilgan sana muddatdan keyin
    assert _batches(db, p) == []
    # yig'indi qabul miqdoriga teng emas
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': iid, 'qty_received': 90, 'lots': [
        {'lot_number': 'A1', 'expiry_date': _iso(300), 'qty': 60}, {'lot_number': 'B2', 'expiry_date': _iso(300), 'qty': 40}]}])
    assert r.status_code == 400 and 'yig' in r.json()['detail']
    # buyurtma qoldig'idan ko'p
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': iid, 'lots': [
        {'lot_number': 'A1', 'expiry_date': _iso(300), 'qty': 70}, {'lot_number': 'B2', 'expiry_date': _iso(300), 'qty': 40}]}])
    assert r.status_code == 400 and "ko'p" in r.json()['detail']
    assert _batches(db, p) == []


def test_regular_company_can_also_split_lots(client, db, world):
    w = world
    p = _product(db, w['a'])
    po = _create_po(client, w['aadmin'], w['aw'], w['asup'], p).json()
    r = _receive(client, w['aadmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'lots': [
        {'lot_number': 'A1', 'qty': 30}, {'lot_number': 'B2', 'qty': 70}]}])
    assert r.status_code == 200, r.text
    assert len(_batches(db, p)) == 2


# ─── 4. Qolgan yaroqlilik muddati ogohlantirishi ───

def test_min_shelf_life_warning_does_not_reject(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, min_shelf_life_pct=50)
    sup = _supplier(db, c)
    p = _product(db, c)
    po = _create_po(client, admin, w, sup, p).json()
    iid = po['items'][0]['id']
    # 300 kun oldin ishlab chiqarilgan, 30 kundan keyin tugaydi: qolgan ~9%
    r = _receive(client, admin, po['id'], [{'po_item_id': iid, 'qty_received': 50, 'lot_number': 'S1',
                                            'manufacture_date': _iso(-300), 'expiry_date': _iso(30)}])
    assert r.status_code == 200, r.text
    assert len(r.json()['warnings']) == 1 and '9%' in r.json()['warnings'][0]
    # ishlab chiqarilgan sana berilmasa — ogohlantirish hisoblanmaydi
    r = _receive(client, admin, po['id'], [{'po_item_id': iid, 'qty_received': 50, 'lot_number': 'S2',
                                            'expiry_date': _iso(30)}])
    assert r.status_code == 200 and r.json()['warnings'] == []


def test_min_shelf_life_off_by_default_and_ok_when_enough(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c)                                   # min_shelf_life_pct = 0
    sup = _supplier(db, c)
    p = _product(db, c)
    po = _create_po(client, admin, w, sup, p, qty=20).json()
    iid = po['items'][0]['id']
    r = _receive(client, admin, po['id'], [{'po_item_id': iid, 'qty_received': 10, 'lot_number': 'S1',
                                            'manufacture_date': _iso(-300), 'expiry_date': _iso(30)}])
    assert r.status_code == 200 and r.json()['warnings'] == []
    c.pharmacy_settings = {'min_shelf_life_pct': 50}
    db.flush()
    r = _receive(client, admin, po['id'], [{'po_item_id': iid, 'qty_received': 10, 'lot_number': 'S2',
                                            'manufacture_date': _iso(-10), 'expiry_date': _iso(300)}])
    assert r.status_code == 200 and r.json()['warnings'] == []


def test_manufacture_after_expiry_rejected(client, db, world):
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p).json()
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 10,
                                                  'lot_number': 'S1', 'manufacture_date': _iso(100),
                                                  'expiry_date': _iso(50)}])
    assert r.status_code == 400


# ─── 5. Ustama va yaxlitlash ───

def _recv_one(client, user, po, lot='S1', qty=None, **extra):
    return _receive(client, user, po['id'], [{'po_item_id': po['items'][0]['id'],
                                              'qty_received': qty or po['items'][0]['qty_ordered'],
                                              'lot_number': lot, 'expiry_date': _iso(300), **extra}])


def test_markup_10000_25pct_round_100_is_12500(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, markup_pct=25, price_round=100)
    sup = _supplier(db, c)
    p = _product(db, c, sale_price=1)
    po = _create_po(client, admin, w, sup, p, qty=10, cost=10000).json()
    r = _recv_one(client, admin, po)
    assert r.status_code == 200, r.text
    db.refresh(p)
    assert p.sale_price == 12500 and p.cost_price == 10000
    assert Decimal(str(r.json()['items'][0]['new_sale_price'])) == Decimal('12500')


def test_markup_rounds_up(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, markup_pct=25, price_round=100)
    sup = _supplier(db, c)
    p = _product(db, c)
    po = _create_po(client, admin, w, sup, p, qty=5, cost=10333).json()   # 12916.25 -> 13000
    assert _recv_one(client, admin, po).status_code == 200
    db.refresh(p)
    assert p.sale_price == 13000


def test_category_markup_overrides_settings_and_inherits_from_parent(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, markup_pct=10, price_round=100)
    sup = _supplier(db, c)
    parent = _category(db, c, markup=40)
    child = _category(db, c, markup=None, parent=parent)
    own = _category(db, c, markup=20)
    p_child = _product(db, c, category=child)
    p_own = _product(db, c, category=own)
    p_none = _product(db, c)
    for prod, expected in ((p_child, 14000), (p_own, 12000), (p_none, 11000)):
        po = _create_po(client, admin, w, sup, prod, qty=1, cost=10000).json()
        assert _recv_one(client, admin, po).status_code == 200
        db.refresh(prod)
        assert prod.sale_price == expected, prod.name


def test_manual_sale_price_wins_over_markup(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, markup_pct=25, price_round=100)
    sup = _supplier(db, c)
    p = _product(db, c)
    po = _create_po(client, admin, w, sup, p, qty=1, cost=10000, new_sale_price=11000).json()
    assert _recv_one(client, admin, po).status_code == 200
    db.refresh(p)
    assert p.sale_price == 11000


def test_no_markup_configured_keeps_price(client, db, world):
    w = world
    p = _product(db, w['ph'], sale_price=777)
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p, qty=1, cost=10000).json()
    assert _recv_one(client, w['padmin'], po).status_code == 200
    db.refresh(p)
    assert p.sale_price == 777


# ─── 6. Narx chegarasi ───

def test_max_markup_blocks_high_sale_price(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, max_markup_pct=30)
    sup = _supplier(db, c)
    p = _product(db, c, sale_price=1)
    po = _create_po(client, admin, w, sup, p, qty=10, cost=10000, new_sale_price=13500).json()
    r = _recv_one(client, admin, po)
    assert r.status_code == 400 and "ustama" in r.json()['detail']
    assert _batches(db, p) == []
    po2 = _create_po(client, admin, w, sup, p, qty=10, cost=10000, new_sale_price=13000).json()
    assert _recv_one(client, admin, po2).status_code == 200
    db.refresh(p)
    assert p.sale_price == 13000


def test_max_markup_caps_auto_markup(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, markup_pct=50, max_markup_pct=30, price_round=100)
    sup = _supplier(db, c)
    p = _product(db, c, sale_price=1)
    po = _create_po(client, admin, w, sup, p, qty=1, cost=10000).json()
    assert _recv_one(client, admin, po).status_code == 200
    db.refresh(p)
    assert p.sale_price == 13000


def test_max_markup_checks_existing_price_and_off_for_regular(client, db, world, mk):
    w = world
    _enable(db, w['ph'], max_markup_pct=30)
    p = _product(db, w['ph'], sale_price=50000)          # kirim narxiga nisbatan juda yuqori
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p, qty=1, cost=10000).json()
    assert _recv_one(client, w['padmin'], po).status_code == 400
    # oddiy korxona: shu holat bloklanmaydi
    w['a'].pharmacy_settings = {'max_markup_pct': 30}      # modul o'chiq — e'tiborga olinmaydi
    p2 = _product(db, w['a'], sale_price=50000)
    po2 = _create_po(client, w['aadmin'], w['aw'], w['asup'], p2, qty=1, cost=10000).json()
    r = _receive(client, w['aadmin'], po2['id'], [{'po_item_id': po2['items'][0]['id'], 'qty_received': 1}])
    assert r.status_code == 200, r.text


# ─── 7. Yuk xati ───

def test_supplier_invoice_saved_on_create_update_and_receive(client, db, world):
    w = world
    p = _product(db, w['ph'])
    r = client.login(w['padmin']).post('/api/purchase-orders', json={
        'supplier_id': w['psup'].id, 'warehouse_id': w['pw'].id, 'status': 'sent',
        'supplier_invoice_number': 'YX-77', 'supplier_invoice_date': '2026-05-01',
        'items': [{'product_id': p.id, 'qty_ordered': 5, 'unit_cost': 1000}]})
    assert r.status_code == 200, r.text
    po = r.json()
    assert po['supplier_invoice_number'] == 'YX-77' and po['supplier_invoice_date'] == '2026-05-01'
    r = client.login(w['padmin']).patch(f"/api/purchase-orders/{po['id']}", json={'supplier_invoice_number': 'YX-78'})
    assert r.status_code == 200 and r.json()['supplier_invoice_number'] == 'YX-78'
    r = _receive(client, w['padmin'], po['id'], [{
        'po_item_id': po['items'][0]['id'], 'qty_received': 5, 'lot_number': 'S1', 'expiry_date': _iso(300)}],
        supplier_invoice_number='YX-79', supplier_invoice_date='2026-06-02')
    assert r.status_code == 200, r.text
    assert r.json()['supplier_invoice_number'] == 'YX-79' and r.json()['supplier_invoice_date'] == '2026-06-02'


def test_regular_company_po_has_null_invoice_fields(client, db, world):
    w = world
    p = _product(db, w['a'])
    po = _create_po(client, w['aadmin'], w['aw'], w['asup'], p).json()
    assert po['supplier_invoice_number'] is None and po['supplier_invoice_date'] is None
    assert po['warnings'] == []


# ─── 8. Izolyatsiya ───

def test_other_company_cannot_receive_my_po(client, db, world):
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p).json()
    r = _receive(client, w['oadmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 100,
                                                  'lot_number': 'S1', 'expiry_date': _iso(300)}])
    assert r.status_code == 404
    assert _batches(db, p) == []
    # o'z xaridi ishlaydi
    assert _recv_one(client, w['padmin'], po).status_code == 200
    assert client.login(w['oadmin']).get(f"/api/purchase-orders/{po['id']}").status_code == 404


# ─── 9. Qo'lda kirim (/inventory/receive) ───

def test_manual_receive_pharmacy_lot_and_expiry_optional(client, db, world):
    """P.15: muddati yo'q tovarlar ham bor — qo'lda kirim muddatsiz ham; muddati o'tgani — ogohlantirish."""
    w = world
    p0 = _product(db, w['ph'])
    p = _product(db, w['ph'])
    cl = client.login(w['padmin'])
    base = {'warehouse_id': w['pw'].id}
    r = cl.post('/api/inventory/receive', json={**base, 'items': [{'product_id': p0.id, 'quantity': 5}]})
    assert r.status_code == 200 and r.json()['warnings'] == [], r.text
    r = cl.post('/api/inventory/receive', json={**base, 'items': [
        {'product_id': p0.id, 'quantity': 5, 'lot_number': 'M0', 'expiry_date': _iso(-3)[:10]}]})
    assert r.status_code == 200 and any("o'tgan" in x for x in r.json()['warnings']), r.text
    assert [b.expiry_date is None for b in _batches(db, p0)] == [True, False]
    r = cl.post('/api/inventory/receive', json={**base, 'items': [
        {'product_id': p.id, 'quantity': 5, 'lot_number': 'M1', 'expiry_date': _iso(200)[:10]},
        {'product_id': p.id, 'quantity': 7, 'lot_number': 'M2', 'expiry_date': _iso(400)[:10]}]})
    assert r.status_code == 200, r.text
    assert r.json()['warnings'] == []
    assert [(b.lot_number, b.quantity) for b in _batches(db, p)] == [('M1', 5), ('M2', 7)]
    # P.5: seriya ixtiyoriy — bo'sh bo'lsa partiya "manual" nomini oladi
    r = cl.post('/api/inventory/receive', json={**base, 'items': [
        {'product_id': p.id, 'quantity': 3, 'expiry_date': _iso(300)[:10]}]})
    assert r.status_code == 200, r.text
    assert [b.lot_number for b in _batches(db, p)][-1].startswith('manual')


def test_manual_receive_second_row_error_names_row(client, db, world):
    w = world
    p1 = _product(db, w['ph'])
    p2 = _product(db, w['ph'])
    r = client.login(w['padmin']).post('/api/inventory/receive', json={'warehouse_id': w['pw'].id, 'items': [
        {'product_id': p1.id, 'quantity': 1, 'lot_number': 'M1', 'expiry_date': _iso(100)[:10]},
        {'product_id': p2.id, 'quantity': 1, 'expiry_date': _iso(100)[:10], 'manufacture_date': _iso(200)[:10]}]})
    assert r.status_code == 400 and '2-qator' in r.json()['detail'] and p2.name in r.json()['detail']
    assert _batches(db, p1) == []


def test_manual_receive_other_company_product_404(client, db, world):
    w = world
    p = _product(db, w['other'])
    r = client.login(w['padmin']).post('/api/inventory/receive', json={'warehouse_id': w['pw'].id, 'items': [
        {'product_id': p.id, 'quantity': 1, 'lot_number': 'M1', 'expiry_date': _iso(100)[:10]}]})
    assert r.status_code == 404


# ─── 10. Kategoriya ustamasi (API) ───

def test_category_markup_api(client, db, world):
    w = world
    cl = client.login(w['padmin'])
    r = cl.post('/api/categories/', json={'name': 'Antibiotiklar', 'markup_pct': 25})
    assert r.status_code == 201, r.text
    cid = r.json()['id']
    assert r.json()['markup_pct'] == 25
    r = cl.put(f'/api/categories/{cid}', json={'name': 'Antibiotiklar 2'})
    assert r.json()['markup_pct'] == 25                   # boshqa maydon o'zgarsa ustama saqlanadi
    r = cl.put(f'/api/categories/{cid}', json={'markup_pct': 30})
    assert r.json()['markup_pct'] == 30
    r = cl.put(f'/api/categories/{cid}', json={'markup_pct': None})
    assert r.status_code == 200 and r.json()['markup_pct'] is None
    assert cl.put(f'/api/categories/{cid}', json={'markup_pct': 5000}).status_code == 422
    # boshqa korxona kategoriyasini o'zgartira olmaydi
    r = client.login(w['oadmin']).put(f'/api/categories/{cid}', json={'markup_pct': 1})
    assert r.status_code == 404
    # oddiy kategoriya ustamasiz yaratiladi
    r = cl.post('/api/categories/', json={'name': 'Oddiy'})
    assert r.status_code == 201 and r.json()['markup_pct'] is None


# ─── 11. Migratsiya va i18n ───

def test_migration_is_additive_and_matches_models():
    src = (ROOT / 'alembic' / 'versions' / 'd1_3_purchase_pharmacy.py').read_text(encoding='utf-8')
    assert "revision: str = 'd1_3'" in src
    for col in ('supplier_invoice_number', 'supplier_invoice_date', 'lot_number', 'manufacture_date', 'markup_pct'):
        assert f'ADD COLUMN IF NOT EXISTS {col}' in src
    assert 'NOT NULL' not in src.split('def downgrade')[0]
    assert hasattr(PurchaseOrder, 'supplier_invoice_number') and hasattr(Category, 'markup_pct')


def test_frontend_i18n_keys_in_pending_file():
    path = pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D1.3.json"
    data = json.loads(path.read_text(encoding='utf-8'))
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and data['uz']
    jsx = (ROOT / 'frontend' / 'src' / 'pages' / 'admin' / 'Purchases.jsx').read_text(encoding='utf-8')
    for key in data['uz']:
        # P.5: seriya, P.15: yaroqlilik muddati ixtiyoriy — bu kalitlar endi ishlatilmaydi
        if key in ('purchase.phLotRequired', 'purchase.phExpiryRequired', 'purchase.phExpiryPast'):
            continue
        assert key in jsx, key


# ─── 12. Qabul oynasi uchun hisoblangan narx ───

def test_get_po_suggests_sale_price_only_in_pharmacy(client, db, mk):
    c, _, w, admin = mk.tenant()
    _enable(db, c, markup_pct=25, price_round=100)
    p = _product(db, c)
    po = _create_po(client, admin, w, _supplier(db, c), p, qty=3, cost=10000).json()
    got = client.login(admin).get(f"/api/purchase-orders/{po['id']}").json()
    assert Decimal(str(got['items'][0]['suggested_sale_price'])) == Decimal('12500')
    # oddiy korxona: maydon null
    a, _, aw, aadmin = mk.tenant()
    pa = _product(db, a)
    po2 = _create_po(client, aadmin, aw, _supplier(db, a), pa, qty=3, cost=10000).json()
    got2 = client.login(aadmin).get(f"/api/purchase-orders/{po2['id']}").json()
    assert got2['items'][0]['suggested_sale_price'] is None
