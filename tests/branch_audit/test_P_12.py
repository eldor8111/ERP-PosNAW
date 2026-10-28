"""P.12 — bitta dori/mahsulotda bir nechta shtrix-kod va bir nechta partiya (seriya, muddat, ishlab chiqarilgan sana):
eksport va import.

Qamrov:
 1. Shtrix-kodlar (barcha korxonalar): katakdagi "A, B" — asosiy A, qo'shimcha B; mavjud mahsulot qo'shimcha kod
    bo'yicha ham topiladi; yangilashda kodlar qo'shiladi (o'chirilmaydi); boshqa mahsulot kodi qo'shilmaydi.
 2. Dorixona: bir xil nomli qatorlar — bitta dori, har qator alohida partiya (o'z ombori, seriyasi, sanalari bilan).
    Qayta import: o'zgarmagan fayl hech narsani o'zgartirmaydi; ko'paygan partiya o'zi oshadi; yangi qator — yangi
    partiya; kamaygani — ogohlantirish; muddatsiz (avval sanasiz kiritilgan) qoldiqqa sana yoziladi / bo'linadi.
 3. GET /products/paginated?with_batches — barcha partiyalar (eksport uchun); frontend eksport va bo'laklash.
"""
import json
import re
from datetime import timedelta
from decimal import Decimal

from app.models.batch import Batch
from app.models.inventory import StockLevel
from app.models.product import Product
from app.routers.product_import import _box_to_units, _group_lot_rows, _split_barcodes
from app.services.batch_allocator import tashkent_today
from tests.branch_audit.test_P_4 import FUTURE, _import, _prod, _read, pharm   # noqa: F401

PRODUCTS_JSX = 'frontend/src/pages/admin/Products.jsx'
PHARM_IMPORT_JS = 'frontend/src/pages/admin/products/pharmacyImport.js'
LATER = (tashkent_today() + timedelta(days=700)).isoformat()


def _batches(db, pid):
    db.expire_all()
    return sorted(((str(b.expiry_date)[:10] if b.expiry_date else None, b.lot_number, Decimal(str(b.quantity)), b.warehouse_id)
                   for b in db.query(Batch).filter(Batch.product_id == pid).all()), key=lambda x: (x[0] or '', x[1] or ''))


def _level(db, pid, wid):
    db.expire_all()
    sl = db.query(StockLevel).filter(StockLevel.product_id == pid, StockLevel.warehouse_id == wid).first()
    return Decimal(str(sl.quantity)) if sl else Decimal('0')


def _lots_file(name='Nurofen 200 mg', box_a='2', box_b='1'):
    """Eksport ko'rinishi: birinchi qatorda dori ma'lumotlari, keyingisida faqat nomi va partiya."""
    return [
        {'Nomi': name, 'Barkod': '4780000019001, 4780000019002', 'Katta qadoq narxi': '30000',
         "O'rta qadoqdagi dona soni": '10', 'Qoldiq (katta qadoq)': box_a, 'Seriya': 'A1', 'Yaroqlilik muddati': FUTURE,
         'Ishlab chiqarilgan sana': '2026-01-10'},
        {'Nomi': name, 'Qoldiq (katta qadoq)': box_b, 'Seriya': 'B2', 'Yaroqlilik muddati': LATER},
    ]


# ───────────────────────── 1. Shtrix-kodlar ─────────────────────────

def test_split_barcodes_rules():
    assert _split_barcodes('4780012345678, 4780012345685') == ['4780012345678', '4780012345685']
    assert _split_barcodes('A; B\nA ,  C') == ['A', 'B', 'C']
    assert _split_barcodes('') == [] and _split_barcodes(None) == []
    assert _split_barcodes('4780012345678') == ['4780012345678']


def test_plain_company_import_several_barcodes_and_update_by_extra_code(client, db, mk):
    c, _, w, u = mk.tenant()
    cl = client.login(u)
    body = _import(cl, [{'Nomi': 'Shampun', 'Barkod': '4780000018001, 4780000018002', 'Chakana narxi': '9000'}],
                   warehouse_id=w.id)
    assert body['created'] == 1, body
    p = _prod(db, c, 'Shampun')
    assert p.barcode == '4780000018001' and json.loads(p.extra_barcodes) == ['4780000018002']
    # boshqa nom bilan, faqat qo'shimcha kod orqali topiladi; yangi kod qo'shiladi, borlari o'chirilmaydi
    body = _import(cl, [{'Nomi': 'Shampun 2', 'Barkod': '4780000018002, 4780000018003', 'Chakana narxi': '9500'}],
                   allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['created'] == 0, body
    db.expire_all()
    p = db.get(Product, p.id)
    assert p.name == 'Shampun 2' and Decimal(str(p.sale_price)) == 9500
    assert p.barcode == '4780000018002'                                        # birinchi kod asosiy (avvalgidek)
    assert json.loads(p.extra_barcodes) == ['4780000018003']


def test_update_keeps_main_code_and_skips_code_of_other_product(client, db, mk):
    c, _, w, u = mk.tenant()
    cl = client.login(u)
    _import(cl, [{'Nomi': 'Krem', 'Barkod': '4780000018101'}, {'Nomi': 'Sovun', 'Barkod': '4780000018102'}],
            warehouse_id=w.id)
    body = _import(cl, [{'Nomi': 'Krem', 'Barkod': '4780000018101, 4780000018102, 4780000018103'}],
                   allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1, body
    assert any('4780000018102' in x['warning'] for x in body['warnings']), body
    db.expire_all()
    krem = _prod(db, c, 'Krem')
    assert krem.barcode == '4780000018101' and json.loads(krem.extra_barcodes) == ['4780000018103']
    assert _prod(db, c, 'Sovun').barcode == '4780000018102'


def test_new_product_extra_code_taken_by_other_product_is_skipped(client, db, mk):
    c, _, w, u = mk.tenant()
    cl = client.login(u)
    _import(cl, [{'Nomi': 'Birinchi', 'Barkod': '4780000018201'}], warehouse_id=w.id)
    body = _import(cl, [{'Nomi': 'Ikkinchi', 'Barkod': '4780000018202, 4780000018201'}], warehouse_id=w.id)
    assert body['created'] == 1 and any('4780000018201' in x['warning'] for x in body['warnings']), body
    p = _prod(db, c, 'Ikkinchi')
    assert p.barcode == '4780000018202' and p.extra_barcodes is None


# ───────────────────────── 2. Dorixona: bir nechta partiya ─────────────────────────

def test_group_rows_merges_product_columns_and_collects_lots():
    rows = _group_lot_rows([
        {'Nomi': 'X', 'Barkod': 'A', 'Katta qadoq narxi': '1000', 'Seriya': 'S1', '__row_index': 2},
        {'Nomi': 'Y', 'Barkod': 'Q', '__row_index': 3},
        {'Nomi': 'X', 'Barkod': 'B', 'MXIK': '03004001001000012', 'Seriya': 'S2', 'Qoldiq (katta qadoq)': '1',
         '__row_index': 4},
    ])
    assert [r['Nomi'] for r in rows] == ['X', 'Y']
    x = rows[0]
    assert x['Barkod'] == 'A, B' and x['Katta qadoq narxi'] == '1000' and x['MXIK'] == '03004001001000012'
    assert 'Seriya' not in x and [lt['Seriya'] for lt in x['__lots']] == ['S1', 'S2']
    assert [lt['__row_index'] for lt in x['__lots']] == [2, 4]
    assert '__lots' not in rows[1]                                             # bitta qator — o'zgarishsiz


def test_import_several_lots_creates_one_drug_with_batches(client, db, pharm):
    c, _, w, u = pharm
    body = _import(client.login(u), _lots_file(), warehouse_id=w.id)
    assert body['created'] == 1 and body['errors'] == [], body
    p = _prod(db, c, 'Nurofen 200 mg')
    assert p.barcode == '4780000019001' and json.loads(p.extra_barcodes) == ['4780000019002']
    assert _batches(db, p.id) == [(FUTURE, 'A1', Decimal(20), w.id), (LATER, 'B2', Decimal(10), w.id)]
    assert _level(db, p.id, w.id) == 30
    a1 = db.query(Batch).filter(Batch.product_id == p.id, Batch.lot_number == 'A1').one()
    assert a1.manufacture_date.date().isoformat() == '2026-01-10'


def test_lots_go_to_their_own_warehouse(client, db, mk, pharm):
    c, b, w, u = pharm
    w2 = mk.warehouse(c, b, name='Ikkinchi dorixona')
    rows = _lots_file()
    rows[1]['Ombor'] = 'Ikkinchi dorixona'
    body = _import(client.login(u), rows, warehouse_id=w.id)
    assert body['created'] == 1, body
    p = _prod(db, c, 'Nurofen 200 mg')
    assert _level(db, p.id, w.id) == 20 and _level(db, p.id, w2.id) == 10


def test_lot_without_expiry_rejects_whole_new_drug(client, db, pharm):
    c, _, w, u = pharm
    rows = _lots_file()
    rows[1].pop('Yaroqlilik muddati')
    body = _import(client.login(u), rows, warehouse_id=w.id)
    assert body['created'] == 0 and '3-qator' in body['errors'][0]['error'], body
    assert db.query(Product).filter(Product.company_id == c.id, Product.name == 'Nurofen 200 mg').first() is None


def test_reimport_same_file_changes_nothing_and_increase_goes_to_same_batch(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    _import(cl, _lots_file(), warehouse_id=w.id)
    p = _prod(db, c, 'Nurofen 200 mg')
    before = _batches(db, p.id)
    body = _import(cl, _lots_file(), allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['warnings'] == [], body
    assert _batches(db, p.id) == before and _level(db, p.id, w.id) == 30
    # B2: 1 quti -> 3 quti — o'sha partiya oshadi (yangi partiya ochilmaydi)
    body = _import(cl, _lots_file(box_b='3'), allow_update='true', warehouse_id=w.id)
    assert body['warnings'] == [], body
    assert _batches(db, p.id) == [(FUTURE, 'A1', Decimal(20), w.id), (LATER, 'B2', Decimal(30), w.id)]
    assert _level(db, p.id, w.id) == 50


def test_reimport_new_lot_row_adds_batch_and_decrease_only_warns(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    _import(cl, _lots_file(), warehouse_id=w.id)
    p = _prod(db, c, 'Nurofen 200 mg')
    third = (tashkent_today() + timedelta(days=900)).isoformat()
    rows = _lots_file(box_a='1')                                               # A1: 2 -> 1 quti (kamaytirish)
    rows.append({'Nomi': 'Nurofen 200 mg', 'Qoldiq (katta qadoq)': '4', 'Seriya': 'C3', 'Yaroqlilik muddati': third})
    body = _import(cl, rows, allow_update='true', warehouse_id=w.id)
    assert any('Inventarizatsiya' in x['warning'] for x in body['warnings']), body
    assert _batches(db, p.id) == [(FUTURE, 'A1', Decimal(20), w.id), (LATER, 'B2', Decimal(10), w.id),
                                  (third, 'C3', Decimal(40), w.id)]
    assert _level(db, p.id, w.id) == 70


def test_undated_stock_gets_dates_from_lot_rows_without_stock_change(client, db, pharm):
    """Avval sanasiz kiritilgan 40 dona: fayldagi 2 + 1 quti (20 + 10) — sana yoziladi / bo'linadi, qoldiq o'zgarmaydi."""
    c, _, w, u = pharm
    p = Product(name='Nurofen 200 mg', barcode='4780000019001', sku='SKU-P9-1', company_id=c.id,
                cost_price=Decimal('2000'), sale_price=Decimal('3000'))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=w.id, quantity=Decimal('40')))
    db.add(Batch(product_id=p.id, warehouse_id=w.id, quantity=Decimal('40'), initial_quantity=Decimal('40'),
                 purchase_price=Decimal('2000'), company_id=c.id, lot_number='manual'))
    db.flush()
    body = _import(client.login(u), _lots_file(), allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['warnings'] == [], body
    assert _level(db, p.id, w.id) == 40
    assert _batches(db, p.id) == [(None, 'manual', Decimal(10), w.id), (FUTURE, 'A1', Decimal(20), w.id),
                                  (LATER, 'B2', Decimal(10), w.id)]


def test_reimport_with_rounded_box_counts_from_export_changes_nothing(client, db, pharm):
    """Eksportda 20 dona / 30 = 0.667 quti, 10 / 30 = 0.333 — qayta import 0.01 dona kirim qilmaydi."""
    c, _, w, u = pharm
    cl = client.login(u)
    rows = _lots_file()
    for r in rows:
        r["Katta qadoqdagi o'rta qadoq soni"] = '3'                          # 1 quti = 3 blister = 30 dona
    _import(cl, rows, warehouse_id=w.id)
    p = _prod(db, c, 'Nurofen 200 mg')
    assert _level(db, p.id, w.id) == 90
    before = _batches(db, p.id)
    rows = _lots_file(box_a='2', box_b='1')
    rows[0]["Katta qadoqdagi o'rta qadoq soni"] = '3'
    rows.append({'Nomi': 'Nurofen 200 mg', 'Qoldiq (katta qadoq)': '0.333', 'Seriya': 'A1', 'Yaroqlilik muddati': FUTURE})
    rows[0]['Qoldiq (katta qadoq)'] = '1.667'                                  # A1: 1.667 + 0.333 = 2 quti (60 dona)
    body = _import(cl, rows, allow_update='true', warehouse_id=w.id)
    assert body['warnings'] == [], body
    assert _batches(db, p.id) == before and _level(db, p.id, w.id) == 90


def test_bulk_check_counts_lot_rows_as_one_drug(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    r = cl.post('/api/products/bulk-check', json=_lots_file(), params={'warehouse_id': w.id})
    assert r.status_code == 200 and r.json()['new_count'] == 1, r.text
    _import(cl, _lots_file(), warehouse_id=w.id)
    r = cl.post('/api/products/bulk-check', json=_lots_file(), params={'warehouse_id': w.id})
    assert r.json()['found_count'] == 1 and r.json()['new_count'] == 0, r.text


def test_box_count_rounding_from_export_is_not_new_stock():
    assert _box_to_units(Decimal('0.767'), 30) == 23                          # 23 / 30 eksportda 0.767
    assert _box_to_units(Decimal('0.333'), 30) == 10
    assert _box_to_units(Decimal('2.5'), 1) == Decimal('2.5')
    assert _box_to_units(Decimal('1.5'), 10) == 15


def test_plain_company_same_name_rows_are_not_grouped(client, db, mk):
    c, _, w, u = mk.tenant()
    body = _import(client.login(u), [{'Nomi': 'Oddiy', 'Barkod': '4780000018301', 'Qoldiq': '2'},
                                     {'Nomi': 'Oddiy', 'Barkod': '4780000018302', 'Qoldiq': '3'}], warehouse_id=w.id)
    assert body['created'] == 1 and body['skipped'] == 1, body               # avvalgidek: ikkinchisi takror


# ───────────────────────── 3. Eksport ─────────────────────────

def test_paginated_with_batches_lists_every_lot(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    _import(cl, _lots_file(), warehouse_id=w.id)
    items = cl.get('/api/products/paginated', params={'limit': 100, 'with_batches': 'true'}).json()['items']
    it = next(x for x in items if x['name'] == 'Nurofen 200 mg')
    assert [(b['lot_number'], b['expiry_date'], b['quantity'], b['warehouse']) for b in it['batches']] == [
        ('A1', FUTURE, 20.0, w.name), ('B2', LATER, 10.0, w.name)]
    assert it['batches'][0]['manufacture_date'] == '2026-01-10'
    plain = cl.get('/api/products/paginated', params={'limit': 100}).json()['items']
    assert 'batches' not in next(x for x in plain if x['name'] == 'Nurofen 200 mg')


def test_frontend_export_rows_per_lot_and_grouped_chunks():
    js = _read(PHARM_IMPORT_JS)
    assert 'export const pharmaExportLines = (p) =>' in js and 'p.batches.length > 1' in js
    assert "const head = (row) => (lotOnly ? ['', '', '', '', row[4]] : row);" in js
    assert 'export const pharmaChunks = (rows, size) =>' in js and 'export const pharmaRowKey = (r) =>' in js
    assert "'barcha barkodlar'" in js and "'все штрих-коды'" in js
    s = _read(PRODUCTS_JSX)
    assert "if (pharmacyOn) params.append('with_batches', 'true');" in s
    assert 'const chunks = pharmacyOn ? pharmaChunks(payload, CHUNK_SIZE) : [];' in s
    assert "ws['!ref'] = `A1:${lastCol}${lines.length + 2}`;" in s
    assert 'const vals = lotOnly ? cols.map((_, j) => (j === 1 ? p.name : \'\')) : [' in s
    assert "tf('pharmacyImport.lotRow'" in s and "tf('pharmacyImport.hint5'" in s
    # server va frontend guruh kaliti bir xil: nomi, nomsiz bo'lsa birinchi shtrix-kod
    assert re.search(r"if \(name\) return `n:\$\{name\}`;", js)
