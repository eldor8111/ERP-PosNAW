"""P.1 — Qadoq tuzilmasi va boshlang'ich qoldiq: backend.

Qamrov:
 1. POST/PUT /products: `units` (blister, quti) — saqlash, to'liq almashtirish, `units: []` o'chirish, yuborilmasa tegilmaydi;
    validatsiya (ratio butun > 1, takroriy nom/nisbat, manfiy narx, shtrix-kod to'qnashuvi) -> 400.
 2. `pharma.pack_qty` bo'sh bo'lsa eng katta nisbat bilan to'ldirilishi.
 3. Boshlang'ich qoldiq: dorixonada seriya va muddat majburiy, Batch'ga yoziladi; oddiy korxonada `initial-<id>` va muddatsiz.
 4. GET /products/{id} va ro'yxatda `units` (ratio o'sish tartibida), oddiy korxonada bo'sh.
 5. Excel import: narx hisobi (100000/5/10 -> 20000, 2000; 100000/3 -> yaxlitlash), qoldiqda seriya/muddat majburiy
    (qator raqami bilan), Batch seriya va muddat bilan; oddiy korxonada ustunlar e'tiborsiz.
 6. Ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_P_1.py -q -p no:cacheprovider
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.product_pharma import ProductPharma
from app.models.product_units import ProductUnit
from app.routers.product_import import _divide_price, _parse_date_cell
from app.services.batch_allocator import tashkent_today

# SQLite Integer ustuniga (products.min_stock) Decimal bog'lab bo'lmaydi — faqat test muhiti uchun adapter
sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))

URL = '/api/products/'
IMPORT_URL = '/api/products/bulk-import'
FUTURE = (tashkent_today() + timedelta(days=400)).isoformat()


def _pharmacy_on(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _body(name='Parasetamol', barcode='4780000000001', **kw):
    b = {'name': name, 'barcode': barcode, 'sale_price': 2000, 'cost_price': 1000, 'unit': 'dona',
         'mxik_code': '30049099001000000'}
    b.update(kw)
    return b


def _units():
    return [
        {'name': 'blister', 'ratio': 10, 'sale_price': 20000, 'barcode': None},
        {'name': 'quti', 'ratio': 50, 'sale_price': 100000, 'barcode': '4780000000017'},
    ]


@pytest.fixture
def pharm(db, mk):
    c, b, w, u = mk.tenant()
    _pharmacy_on(db, c)
    return c, b, w, u


def _unit_rows(db, product_id):
    return db.query(ProductUnit).filter(ProductUnit.product_id == product_id).order_by(ProductUnit.ratio).all()


# ───────────────────────── 1. units: yaratish / almashtirish / o'chirish ─────────────────────────

def test_create_with_units_and_get(client, db, pharm):
    c, _, _, u = pharm
    cl = client.login(u)
    r = cl.post(URL, json=_body(units=_units()))
    assert r.status_code == 201, r.text
    out = r.json()
    assert [(x['name'], x['ratio'], x['sale_price'], x['barcode']) for x in out['units']] == [
        ('blister', 10, 20000.0, None), ('quti', 50, 100000.0, '4780000000017')]
    assert all('id' in x for x in out['units'])
    pid = out['id']
    got = cl.get(f'{URL}{pid}').json()
    assert [x['ratio'] for x in got['units']] == [10, 50]
    # ro'yxatda ham (ratio o'sish tartibida)
    lst = cl.get(URL).json()
    row = next(x for x in lst if x['id'] == pid)
    assert [x['name'] for x in row['units']] == ['blister', 'quti']
    # pack_qty eng katta nisbat bilan to'ldirildi
    assert db.query(ProductPharma.pack_qty).filter(ProductPharma.product_id == pid).scalar() == 50


def test_pack_qty_explicit_not_overwritten(client, db, pharm):
    c, _, _, u = pharm
    r = client.login(u).post(URL, json=_body(units=_units(), pharma={'pack_qty': 100}))
    assert r.status_code == 201, r.text
    assert db.query(ProductPharma.pack_qty).filter(ProductPharma.product_id == r.json()['id']).scalar() == 100


def test_put_replaces_units_and_deletes(client, db, pharm):
    c, _, _, u = pharm
    cl = client.login(u)
    pid = cl.post(URL, json=_body(units=_units())).json()['id']
    old_ids = {x.name: x.id for x in _unit_rows(db, pid)}

    # yuborilmasa tegilmaydi
    assert cl.put(f'{URL}{pid}', json={'min_stock': 3}).status_code == 200
    assert len(_unit_rows(db, pid)) == 2

    # to'liq almashtirish: quti yangilanadi (id saqlanadi), blister yo'qoladi, "pachka" qo'shiladi
    new = [{'name': 'Quti', 'ratio': 60, 'sale_price': 120000, 'barcode': '4780000000017'},
           {'name': 'pachka', 'ratio': 12, 'sale_price': None, 'barcode': None}]
    r = cl.put(f'{URL}{pid}', json={'units': new})
    assert r.status_code == 200, r.text
    rows = _unit_rows(db, pid)
    assert [(x.name, int(x.ratio)) for x in rows] == [('pachka', 12), ('Quti', 60)]
    assert next(x for x in rows if x.name == 'Quti').id == old_ids['quti']
    assert [x['name'] for x in r.json()['units']] == ['pachka', 'Quti']

    # units: [] = hammasini o'chirish
    r = cl.put(f'{URL}{pid}', json={'units': []})
    assert r.status_code == 200 and r.json()['units'] == []
    assert _unit_rows(db, pid) == []


def test_put_keeps_own_barcode_on_resave(client, db, pharm):
    c, _, _, u = pharm
    cl = client.login(u)
    pid = cl.post(URL, json=_body(units=_units())).json()['id']
    # shu mahsulotning o'z birligi shtrix-kodi qayta saqlashda to'qnashuv bermaydi
    assert cl.put(f'{URL}{pid}', json={'units': _units()}).status_code == 200
    assert len(_unit_rows(db, pid)) == 2


@pytest.mark.parametrize('bad,msg', [
    ([{'name': 'quti', 'ratio': 1}], 'butun son'),
    ([{'name': 'quti', 'ratio': 0}], 'butun son'),
    ([{'name': 'quti', 'ratio': 2.5}], 'butun son'),
    ([{'name': '  ', 'ratio': 10}], 'bo\'sh'),
    ([{'name': 'quti', 'ratio': 10}, {'name': 'Quti', 'ratio': 20}], 'takrorlangan'),
    ([{'name': 'a', 'ratio': 10}, {'name': 'b', 'ratio': 10}], 'Bir xil nisbatli'),
    ([{'name': 'quti', 'ratio': 10, 'sale_price': -1}], 'manfiy'),
    ([{'name': 'a', 'ratio': 10, 'barcode': '999'}, {'name': 'b', 'ratio': 20, 'barcode': '999'}], 'takrorlangan'),
])
def test_units_validation_errors_400(client, db, pharm, bad, msg):
    c, _, _, u = pharm
    cl = client.login(u)
    r = cl.post(URL, json=_body(units=bad))
    assert r.status_code == 400, r.text
    assert msg in r.json()['detail']
    assert db.query(Product).filter(Product.company_id == c.id).count() == 0


def test_unit_barcode_conflicts(client, db, pharm):
    c, _, _, u = pharm
    cl = client.login(u)
    first = cl.post(URL, json=_body(units=_units()))
    assert first.status_code == 201
    # boshqa mahsulot birligi shtrix-kodi
    r = cl.post(URL, json=_body('Analgin', '4780000000002',
                                units=[{'name': 'quti', 'ratio': 20, 'barcode': '4780000000017'}]))
    assert r.status_code == 400 and 'boshqa birlikda' in r.json()['detail']
    # boshqa mahsulotning asosiy shtrix-kodi
    r = cl.post(URL, json=_body('Analgin', '4780000000002',
                                units=[{'name': 'quti', 'ratio': 20, 'barcode': '4780000000001'}]))
    assert r.status_code == 400 and 'shtrix-kodi' in r.json()['detail']
    # o'z asosiy shtrix-kodi
    r = cl.post(URL, json=_body('Analgin', '4780000000002',
                                units=[{'name': 'quti', 'ratio': 20, 'barcode': '4780000000002'}]))
    assert r.status_code == 400
    # PUT: boshqa mahsulot asosiy shtrix-kodi
    pid = cl.post(URL, json=_body('Analgin', '4780000000002')).json()['id']
    r = cl.put(f'{URL}{pid}', json={'units': [{'name': 'quti', 'ratio': 20, 'barcode': '4780000000001'}]})
    assert r.status_code == 400
    assert _unit_rows(db, pid) == []


# ───────────────────────── 2. boshlang'ich qoldiq ─────────────────────────

def test_initial_stock_requires_lot_and_expiry_in_pharmacy(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    r = cl.post(URL, json=_body(initial_stock=130, initial_warehouse_id=w.id))
    assert r.status_code == 400 and 'seriya' in r.json()['detail']
    r = cl.post(URL, json=_body(initial_stock=130, initial_warehouse_id=w.id, initial_lot_number='L1'))
    assert r.status_code == 400 and 'yaroqlilik muddati' in r.json()['detail']
    past = (tashkent_today() - timedelta(days=1)).isoformat()
    r = cl.post(URL, json=_body(initial_stock=130, initial_warehouse_id=w.id, initial_lot_number='L1',
                                initial_expiry_date=past))
    assert r.status_code == 400 and 'bugundan keyin' in r.json()['detail']
    r = cl.post(URL, json=_body(initial_stock=130, initial_warehouse_id=w.id, initial_lot_number='L1',
                                initial_expiry_date=FUTURE, initial_manufacture_date=FUTURE))
    assert r.status_code == 400
    assert db.query(Product).filter(Product.company_id == c.id).count() == 0
    # qoldiqsiz seriya talab qilinmaydi
    assert cl.post(URL, json=_body()).status_code == 201


def test_initial_stock_writes_batch_with_lot_and_dates(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    r = cl.post(URL, json=_body(units=_units(), initial_stock=130, initial_warehouse_id=w.id,
                                initial_lot_number='LOT2026A', initial_expiry_date=FUTURE,
                                initial_manufacture_date='2025-12-01'))
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    b = db.query(Batch).filter(Batch.product_id == pid).one()
    assert b.lot_number == 'LOT2026A'
    assert b.expiry_date.date().isoformat() == FUTURE
    assert b.manufacture_date.date().isoformat() == '2025-12-01'
    assert Decimal(str(b.quantity)) == 130
    st = db.query(StockLevel).filter(StockLevel.product_id == pid).one()
    assert Decimal(str(st.quantity)) == 130
    assert r.json()['stock_quantity'] is not None


# ───────────────────────── 3. oddiy korxona (regressiya) ─────────────────────────

def test_plain_company_ignores_new_fields(client, db, mk):
    c, _, w, u = mk.tenant()
    cl = client.login(u)
    r = cl.post(URL, json=_body(units=_units(), initial_stock=5, initial_warehouse_id=w.id,
                                initial_lot_number='X', initial_expiry_date=FUTURE))
    assert r.status_code == 201, r.text
    out = r.json()
    assert out['units'] == []
    pid = out['id']
    assert db.query(ProductUnit).filter(ProductUnit.product_id == pid).count() == 0
    b = db.query(Batch).filter(Batch.product_id == pid).one()
    assert b.lot_number == f'initial-{pid}' and b.expiry_date is None and b.manufacture_date is None
    # qoldiq seriyasiz ham o'tadi (dorixonadagi qoida oddiy korxonaga tegmaydi)
    r2 = cl.post(URL, json=_body('Boshqa', '4780000000009', initial_stock=3, initial_warehouse_id=w.id))
    assert r2.status_code == 201, r2.text
    # PUT da units e'tiborsiz
    assert cl.put(f'{URL}{pid}', json={'units': _units()}).status_code == 200
    assert db.query(ProductUnit).filter(ProductUnit.product_id == pid).count() == 0
    assert cl.get(f'{URL}{pid}').json()['units'] == []
    assert all(not x.get('units') for x in cl.get(URL).json())


# ───────────────────────── 4. izolyatsiya ─────────────────────────

def test_two_company_isolation(client, db, mk):
    c1, _, _, u1 = mk.tenant()
    c2, _, _, u2 = mk.tenant()
    _pharmacy_on(db, c1)
    _pharmacy_on(db, c2)
    pid = client.login(u1).post(URL, json=_body(units=_units())).json()['id']
    # B korxona A mahsulotini ko'rmaydi/o'zgartirmaydi
    cl2 = client.login(u2)
    assert cl2.get(f'{URL}{pid}').status_code == 404
    assert cl2.put(f'{URL}{pid}', json={'units': []}).status_code == 404
    assert len(_unit_rows(db, pid)) == 2
    assert all(x['id'] != pid for x in cl2.get(URL).json())
    # B korxona xuddi shu shtrix-kodli birlikni ishlata oladi (korxona ichida noyob) va A birliklari aralashmaydi
    r = cl2.post(URL, json=_body(units=[{'name': 'quti', 'ratio': 50, 'barcode': '4780000000017'}]))
    assert r.status_code == 201, r.text
    assert [x['name'] for x in client.login(u1).get(f'{URL}{pid}').json()['units']] == ['blister', 'quti']


# ───────────────────────── 5. Excel import ─────────────────────────

def _imp_row(name='Amoksitsillin', barcode='4780000001111', **kw):
    row = {'Nomi': name, 'Barkod': barcode, 'Tan narxi': 1000}
    row.update(kw)
    return row


def _import(cl, rows, **params):
    return cl.post(IMPORT_URL, json=rows, params=params)


def _prod(db, c, name):
    return db.query(Product).filter(Product.company_id == c.id, Product.name == name).one()


def test_divide_price_rules():
    assert _divide_price(Decimal(100000), 5, 100) == 20000
    assert _divide_price(Decimal(20000), 10, 100) == 2000
    assert _divide_price(Decimal(100000), 3, 100) == 33400       # 33 333,33 -> yuqoriga 100 qadam
    assert _divide_price(Decimal(100000), 3, 0) == Decimal('33333.34')
    assert _divide_price(Decimal(50), 1, 100) == 50              # aniq bo'linsa yaxlitlanmaydi
    assert _divide_price(Decimal(100000), 3, 1000) == 34000


def test_parse_date_cell():
    assert _parse_date_cell('2027-12-31').isoformat() == '2027-12-31'
    assert _parse_date_cell('31.12.2027').isoformat() == '2027-12-31'
    assert _parse_date_cell('12.2027').isoformat() == '2027-12-31'
    assert _parse_date_cell('02/2028').isoformat() == '2028-02-29'
    assert _parse_date_cell('46387').isoformat() == '2026-12-31'
    with pytest.raises(ValueError):
        _parse_date_cell('abc')


def test_import_price_calc_big_mid_dona(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    row = _imp_row(**{'Katta qadoq nomi': 'quti', 'Katta qadoq narxi': 100000,
                      "Katta qadoqdagi o'rta qadoq soni": 5, "O'rta qadoq nomi": 'pachka',
                      "O'rta qadoqdagi dona soni": 10, 'Qoldiq': 100, 'Seriya': 'LOT7',
                      'Yaroqlilik muddati': FUTURE})
    r = _import(cl, [row], warehouse_id=w.id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['created'] == 1 and body['total_errors'] == 0, body
    p = _prod(db, c, 'Amoksitsillin')
    assert Decimal(str(p.sale_price)) == 2000                   # dona = 20000 / 10
    units = {x.name: x for x in _unit_rows(db, p.id)}
    assert int(units['pachka'].ratio) == 10 and Decimal(str(units['pachka'].sale_price)) == 20000
    assert int(units['quti'].ratio) == 50 and Decimal(str(units['quti'].sale_price)) == 100000
    assert db.query(ProductPharma.pack_qty).filter(ProductPharma.product_id == p.id).scalar() == 50
    b = db.query(Batch).filter(Batch.product_id == p.id).one()
    assert b.lot_number == 'LOT7' and b.expiry_date.date().isoformat() == FUTURE
    assert Decimal(str(b.quantity)) == 100
    # GET javobida ko'rinadi
    assert [x['ratio'] for x in cl.get(f'{URL}{p.id}').json()['units']] == [10, 50]


def test_import_price_calc_no_middle_rounds_up(client, db, pharm):
    c, _, w, u = pharm
    row = _imp_row('Sirop', '4780000001112', **{'Katta qadoq nomi': 'quti', 'Katta qadoq narxi': 100000,
                                                "Katta qadoqdagi o'rta qadoq soni": 3})
    body = _import(client.login(u), [row], warehouse_id=w.id).json()
    assert body['created'] == 1 and body['total_errors'] == 0, body
    p = _prod(db, c, 'Sirop')
    assert Decimal(str(p.sale_price)) == 33400                  # 33 333,33 yuqoriga 100 qadamga
    assert [(x.name, int(x.ratio)) for x in _unit_rows(db, p.id)] == [('quti', 3)]


def test_import_explicit_retail_price_wins(client, db, pharm):
    c, _, w, u = pharm
    row = _imp_row('Qo\'lda', '4780000001113', **{'Chakana narxi': 2500, 'Katta qadoq nomi': 'quti',
                                                  'Katta qadoq narxi': 100000,
                                                  "Katta qadoqdagi o'rta qadoq soni": 50})
    assert _import(client.login(u), [row], warehouse_id=w.id).json()['created'] == 1
    assert Decimal(str(_prod(db, c, "Qo'lda").sale_price)) == 2500


def test_import_stock_requires_lot_and_expiry_with_row_number(client, db, pharm):
    c, _, w, u = pharm
    rows = [
        _imp_row('A1', '4780000002001', Qoldiq=10),
        _imp_row('A2', '4780000002002', Qoldiq=10, Seriya='L'),
        _imp_row('A3', '4780000002003', Qoldiq=10, Seriya='L', **{'Yaroqlilik muddati': '2001-01-01'}),
        _imp_row('A4', '4780000002004', Qoldiq=10, Seriya='L', **{'Yaroqlilik muddati': 'xato'}),
        _imp_row('A5', '4780000002005', Qoldiq=10, Seriya='L5', **{'Yaroqlilik muddati': FUTURE}),
        _imp_row('A6', '4780000002006'),    # qoldiqsiz — seriya shart emas
    ]
    for i, r in enumerate(rows):
        r['__row_index'] = i + 2
    body = _import(client.login(u), rows, warehouse_id=w.id).json()
    assert body['created'] == 2, body
    errs = {e['row']: e['error'] for e in body['errors']}
    assert set(errs) == {2, 3, 4, 5}
    assert 'Seriya' in errs[2] and 'Yaroqlilik' in errs[3] and 'bugundan keyin' in errs[4] and 'sana' in errs[5]
    assert db.query(Product).filter(Product.company_id == c.id, Product.name.in_(['A1', 'A2', 'A3', 'A4'])).count() == 0


def test_import_pack_errors_per_row(client, db, pharm):
    c, _, w, u = pharm
    rows = [
        _imp_row('B1', '4780000003001', **{"O'rta qadoq nomi": 'pachka'}),                       # dona soni yo'q
        _imp_row('B2', '4780000003002', **{'Katta qadoq nomi': 'quti', "Katta qadoqdagi o'rta qadoq soni": 1}),
        _imp_row('B3', '4780000003003', **{'Katta qadoq narxi': 1000}),                          # nom yo'q
        _imp_row('B4', '4780000003004', **{'Katta qadoq nomi': 'quti', 'Katta qadoq narxi': 1000,
                                           "Katta qadoqdagi o'rta qadoq soni": 2, "O'rta qadoqdagi dona soni": 5}),  # o'rta nomi yo'q
        _imp_row('B5', '4780000003005', **{'Katta qadoq nomi': 'quti', 'Katta qadoq narxi': 1000,
                                           "Katta qadoqdagi o'rta qadoq soni": 10}),             # OK
    ]
    for i, r in enumerate(rows):
        r['__row_index'] = i + 2
    body = _import(client.login(u), rows, warehouse_id=w.id).json()
    assert body['created'] == 1, body
    assert {e['row'] for e in body['errors']} == {2, 3, 4, 5}


def test_import_update_syncs_units(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    pid = cl.post(URL, json=_body('Mavjud', '4780000004001', units=[{'name': 'eski', 'ratio': 5}])).json()['id']
    row = {'Nomi': 'Mavjud', 'Katta qadoq nomi': 'quti', 'Katta qadoq narxi': 60000,
           "Katta qadoqdagi o'rta qadoq soni": 3, "O'rta qadoq nomi": 'blister', "O'rta qadoqdagi dona soni": 10}
    body = _import(cl, [row], allow_update=True, warehouse_id=w.id).json()
    assert body['updated'] == 1, body
    rows = _unit_rows(db, pid)
    assert [(x.name, int(x.ratio)) for x in rows] == [('blister', 10), ('quti', 30)]
    assert Decimal(str(rows[0].sale_price)) == 20000
    assert Decimal(str(db.get(Product, pid).sale_price)) == 2000


def test_import_plain_company_ignores_columns(client, db, mk):
    c, _, w, u = mk.tenant()
    row = _imp_row('Oddiy', '4780000005001', Qoldiq=7, **{'Katta qadoq nomi': 'quti', 'Katta qadoq narxi': 100000,
                                                         "Katta qadoqdagi o'rta qadoq soni": 5, 'Seriya': 'Z',
                                                         'Yaroqlilik muddati': 'xato-sana'})
    body = client.login(u).post(IMPORT_URL, json=[row], params={'warehouse_id': w.id}).json()
    assert body['created'] == 1 and body['total_errors'] == 0, body
    p = _prod(db, c, 'Oddiy')
    assert db.query(ProductUnit).filter(ProductUnit.product_id == p.id).count() == 0
    assert Decimal(str(p.sale_price)) == 0
    b = db.query(Batch).filter(Batch.product_id == p.id).one()
    assert b.lot_number == 'manual' and b.expiry_date is None


def test_import_isolation(client, db, mk):
    c1, _, w1, u1 = mk.tenant()
    c2, _, w2, u2 = mk.tenant()
    _pharmacy_on(db, c1)
    _pharmacy_on(db, c2)
    row = _imp_row('Umumiy', '4780000006001', **{'Katta qadoq nomi': 'quti', 'Katta qadoq narxi': 1000,
                                                 "Katta qadoqdagi o'rta qadoq soni": 10})
    assert client.login(u1).post(IMPORT_URL, json=[row], params={'warehouse_id': w1.id}).json()['created'] == 1
    # B korxonada ham yaratiladi; birliklar faqat o'z korxonasida
    assert client.login(u2).post(IMPORT_URL, json=[row], params={'warehouse_id': w2.id}).json()['created'] == 1
    p1, p2 = _prod(db, c1, 'Umumiy'), _prod(db, c2, 'Umumiy')
    assert p1.id != p2.id
    assert {x.company_id for x in _unit_rows(db, p1.id)} == {c1.id}
    assert {x.company_id for x in _unit_rows(db, p2.id)} == {c2.id}
