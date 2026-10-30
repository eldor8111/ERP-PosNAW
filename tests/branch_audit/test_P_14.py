"""P.14 — dorixona: Excel'ga eksport qilingan faylni qayta import qilish (shu korxonaga yoki yangi bazaga).

Qamrov:
 1. Tarif limiti: mavjud tovarning shtrix-kodlari yangi deb hisoblanmaydi (qayta import limitga urilmaydi).
 2. Dorixona: "Ombor" ustunidagi nom korxonada yo'q bo'lsa — qoldiq tanlangan omborga, ogohlantirish (oddiy korxonada
    avvalgidek xato); muddatsiz / muddati o'tgan qoldiq rad etilmaydi (ogohlantirish); muddatsiz partiya qatorlari
    mavjud muddatsiz partiyalar bilan moslanadi; manfiy qoldiq: mavjud doriga taqqoslanadi, yangisiga yozilmaydi.
 3. GET /products/paginated: dorixonada min_stock (eksport uchun); ruscha holat nomlari.
 4. Frontend: eksportning 2-sarlavha qatori tovar emas, kategoriyasiz tovarda bo'sh katak, dori kartochkasi ustunlari,
    o'z eksport fayli ustunlari tartib bo'yicha (interfeys tili qanday bo'lsa ham), minus belgisi saqlanadi.
"""
import re
from datetime import timedelta
from decimal import Decimal

from app.models.batch import Batch
from app.models.inventory import StockLevel
from app.models.product import Product
from app.services.batch_allocator import tashkent_today
from tests.branch_audit.test_P_4 import FUTURE, _import, _prod, _read, pharm   # noqa: F401
from tests.branch_audit.test_T3_9 import _tariff

PRODUCTS_JSX = 'frontend/src/pages/admin/Products.jsx'
PHARM_IMPORT_JS = 'frontend/src/pages/admin/products/pharmacyImport.js'
PAST = (tashkent_today() - timedelta(days=5)).isoformat()


def _batches(db, pid):
    db.expire_all()
    return sorted(((str(b.expiry_date)[:10] if b.expiry_date else None, b.lot_number, Decimal(str(b.quantity)), b.warehouse_id)
                   for b in db.query(Batch).filter(Batch.product_id == pid).all()), key=lambda x: (x[0] or '', x[1] or ''))


def _level(db, pid, wid):
    db.expire_all()
    sl = db.query(StockLevel).filter(StockLevel.product_id == pid, StockLevel.warehouse_id == wid).first()
    return Decimal(str(sl.quantity)) if sl else Decimal('0')


def _warns(body):
    return [w['warning'] for w in body['warnings']]


# ───────────────────────── 1. Tarif limiti ─────────────────────────

def test_reimport_existing_codes_do_not_count_against_barcode_limit(client, db, mk):
    c, _, w, u = mk.tenant()
    _tariff(db, c, max_products=2)
    cl = client.login(u)
    rows = [{'Nomi': 'Choy', 'Barkod': '4780000014001', 'Chakana narxi': '9000'},
            {'Nomi': 'Shakar', 'Barkod': '4780000014002', 'Chakana narxi': '12000'}]
    assert _import(cl, [dict(r) for r in rows], warehouse_id=w.id)['created'] == 2
    # limit to'lgan: o'sha fayl qayta import (yangilash) — rad etilmaydi
    body = _import(cl, [dict(r, **{'Chakana narxi': '9500'}) if i == 0 else dict(r) for i, r in enumerate(rows)],
                   allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 2 and not body['errors'], body
    # yangi kod — limitdan oshadi
    r = cl.post('/api/products/bulk-import', json=[{'Nomi': 'Tuz', 'Barkod': '4780000014003', 'Chakana narxi': '3000',
                                                    '__row_index': 2}], params={'warehouse_id': w.id})
    assert r.status_code == 400 and 'limiti' in r.json()['detail']


# ───────────────────────── 2. Dorixona: ombor, muddat, manfiy qoldiq ─────────────────────────

def test_unknown_warehouse_name_goes_to_selected_warehouse_in_pharmacy(client, db, mk, pharm):
    c, _, w, u = pharm
    w2 = mk.warehouse(c, name='Filial')
    body = _import(client.login(u), [
        {'Nomi': 'Dori A', 'Katta qadoq narxi': '1000', 'Qoldiq': '4', 'Yaroqlilik muddati': FUTURE,
         'Ombor': 'Boshqa bazadagi ombor'},
        {'Nomi': 'Dori B', 'Katta qadoq narxi': '1000', 'Qoldiq': '3', 'Seriya': 'B1', 'Yaroqlilik muddati': FUTURE,
         'Ombor': 'Eski ombor'},
        {'Nomi': 'Dori B', 'Qoldiq': '2', 'Seriya': 'B2', 'Yaroqlilik muddati': FUTURE, 'Ombor': 'Filial'},
        {'Nomi': 'Dori B', 'Qoldiq': '1', 'Seriya': 'B3', 'Yaroqlilik muddati': FUTURE, 'Ombor': 'Eski ombor'},
    ], warehouse_id=w.id)
    assert body['created'] == 2 and body['errors'] == [], body
    assert _level(db, _prod(db, c, 'Dori A').id, w.id) == 4
    b = _prod(db, c, 'Dori B')
    assert _level(db, b.id, w.id) == 4 and _level(db, b.id, w2.id) == 2
    msgs = _warns(body)
    assert sum('Ombor topilmadi: Eski ombor' in m for m in msgs) == 1                 # bitta dori uchun bir marta
    assert any('Ombor topilmadi: Boshqa bazadagi ombor' in m for m in msgs)


def test_unknown_warehouse_name_is_still_error_in_plain_company(client, db, mk):
    c, _, w, u = mk.tenant()
    body = _import(client.login(u), [{'Nomi': 'Choy', 'Chakana narxi': '9000', 'Qoldiq': '4', 'Ombor': "Yo'q ombor"}],
                   warehouse_id=w.id)
    assert body['created'] == 0 and "Ombor topilmadi" in body['errors'][0]['error']


def test_new_drug_with_undated_and_expired_stock_is_imported(client, db, pharm):
    """Muddati yo'q tovarlar ham bor: muddatsiz qoldiq xatosiz va ogohlantirishsiz; muddati o'tgani — ogohlantirish."""
    c, _, w, u = pharm
    body = _import(client.login(u), [
        {'Nomi': 'Muddatsiz', 'Katta qadoq narxi': '1000', 'Qoldiq': '6'},
        {'Nomi': "Muddati o'tgan", 'Katta qadoq narxi': '1000', 'Qoldiq': '2', 'Yaroqlilik muddati': PAST},
        {'Nomi': 'Partiyali', 'Katta qadoq narxi': '1000', 'Qoldiq': '3', 'Seriya': 'P1', 'Yaroqlilik muddati': FUTURE},
        {'Nomi': 'Partiyali', 'Qoldiq': '5', 'Seriya': 'P0', 'Yaroqlilik muddati': PAST},
        {'Nomi': 'Partiyali', 'Qoldiq': '4'},
    ], warehouse_id=w.id)
    assert body['created'] == 3 and body['errors'] == [], body
    assert _batches(db, _prod(db, c, 'Muddatsiz').id) == [(None, 'manual', Decimal(6), w.id)]
    assert _batches(db, _prod(db, c, "Muddati o'tgan").id)[0][0] == PAST
    p = _prod(db, c, 'Partiyali')
    assert [(x[0], x[2]) for x in _batches(db, p.id)] == [(None, Decimal(4)), (PAST, Decimal(5)), (FUTURE, Decimal(3))]
    assert _level(db, p.id, w.id) == 12
    msgs = _warns(body)
    assert sum("Muddati o'tgan partiya" in m for m in msgs) == 2
    assert [m for m in msgs if 'MXIK' not in m and "Muddati o'tgan" not in m] == [], msgs     # muddatsiz — oddiy holat


def test_existing_undated_and_expired_lots_reimport_unchanged_and_increase_is_received(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    rows = [{'Nomi': 'Aralash', 'Katta qadoq narxi': '1000', 'Qoldiq': '3', 'Seriya': 'P1', 'Yaroqlilik muddati': FUTURE},
            {'Nomi': 'Aralash', 'Qoldiq': '5', 'Seriya': 'P0', 'Yaroqlilik muddati': PAST},
            {'Nomi': 'Aralash', 'Qoldiq': '4'}]
    assert _import(cl, [dict(r) for r in rows], warehouse_id=w.id)['created'] == 1
    p = _prod(db, c, 'Aralash')
    snap = _batches(db, p.id)
    body = _import(cl, [dict(r) for r in rows], allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['errors'] == [] and body['warnings'] == [], body     # o'zgarishsiz fayl
    assert _batches(db, p.id) == snap and _level(db, p.id, w.id) == 12
    body = _import(cl, [dict(r, Qoldiq='7') if i == 2 else dict(r) for i, r in enumerate(rows)],
                   allow_update='true', warehouse_id=w.id)
    assert body['errors'] == [] and body['warnings'] == [], body
    assert _level(db, p.id, w.id) == 15
    assert sum(x[2] for x in _batches(db, p.id) if x[0] is None) == 7


def test_existing_single_row_undated_increase_is_received(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    assert _import(cl, [{'Nomi': 'Eski', 'Katta qadoq narxi': '1000', 'Qoldiq': '5'}], warehouse_id=w.id)['created'] == 1
    p = _prod(db, c, 'Eski')
    body = _import(cl, [{'Nomi': 'Eski', 'Qoldiq': '8'}], allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['errors'] == [] and body['warnings'] == [], body
    assert _level(db, p.id, w.id) == 8


def test_negative_stock_in_file(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    p = Product(name='Minusda', barcode='4780000014010', sku='SKU-P14-1', company_id=c.id,
                cost_price=Decimal('500'), sale_price=Decimal('1000'))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=w.id, quantity=Decimal('-3')))
    db.flush()
    body = _import(cl, [{'Nomi': 'Minusda', 'Katta qadoq narxi': '1000', 'Qoldiq (katta qadoq)': '-3'}],
                   allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['errors'] == [] and body['warnings'] == [], body
    assert _level(db, p.id, w.id) == -3
    body = _import(cl, [{'Nomi': 'Yangi minus', 'Katta qadoq narxi': '1000', 'Qoldiq (katta qadoq)': '-2'}],
                   warehouse_id=w.id)
    assert body['created'] == 1 and any('Minus qoldiq' in m for m in _warns(body)), body
    assert _level(db, _prod(db, c, 'Yangi minus').id, w.id) == 0


def test_ru_status_names(client, db, pharm):
    c, _, w, u = pharm
    body = _import(client.login(u), [{'Nomi': 'Nofaol dori', 'Katta qadoq narxi': '1000', 'Holat': 'Неактивный'}],
                   warehouse_id=w.id)
    assert body['created'] == 1, body
    assert _prod(db, c, 'Nofaol dori').status.value == 'inactive'


# ───────────────────────── 3. Ro'yxat: min_stock ─────────────────────────

def test_paginated_min_stock_only_in_pharmacy(client, db, mk, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    _import(cl, [{'Nomi': 'Minli', 'Katta qadoq narxi': '1000', 'Min. qoldiq': '15'}], warehouse_id=w.id)
    it = next(x for x in cl.get('/api/products/paginated', params={'limit': 50}).json()['items'] if x['name'] == 'Minli')
    assert it['min_stock'] == 15
    c2, _, w2, u2 = mk.tenant()
    cl2 = client.login(u2)
    _import(cl2, [{'Nomi': 'Oddiy', 'Chakana narxi': '1000', 'Min. qoldiq': '15'}], warehouse_id=w2.id)
    it = next(x for x in cl2.get('/api/products/paginated', params={'limit': 50}).json()['items'] if x['name'] == 'Oddiy')
    assert 'min_stock' not in it                                                  # oddiy korxona javobi o'zgarmadi


# ───────────────────────── 4. Frontend ─────────────────────────

def test_frontend_skips_export_subheader_row_and_writes_plain_category():
    s = _read(PRODUCTS_JSX)
    assert "if (rows.length && String(rows[0]['№'] ?? '').trim() === '№') rows.shift();" in s
    blk = s[s.index("params.append('with_batches', 'true')"):s.index("ws['!ref'] = `A1:${lastCol}")]
    assert 'catName(' not in blk                                               # JSX -> "[object Object]" bo'lardi
    assert "categories.find(c => Number(c.id) === Number(p.category_id))?.name || ''" in blk


def test_frontend_export_has_drug_card_columns():
    js = _read(PHARM_IMPORT_JS)
    blk = js[js.index('export const PHARMA_EXPORT_HEADERS = ['):js.index('];', js.index('export const PHARMA_EXPORT_HEADERS'))]
    blk = re.sub(r'//.*', '', blk)                                              # izohlar ("yo'qolmasin")
    heads = re.findall(r"'([^']*)'|\"([^\"]*)\"", blk)
    heads = [a or b for a, b in heads]
    assert heads[10:] == ["Ta'sir etuvchi modda", 'Doza', 'Ishlab chiqaruvchi', "Retseptli (ha/yo'q)", 'Nazorat toifasi',
                          'Mamlakat', "Ro'yxat raqami", 'ATX kodi', 'Katta qadoq nomi', "O'rta qadoq nomi"]
    assert 'const pharmaCardCells = (p, names) =>' in js and "ph.is_rx ? 'ha' : \"yo'q\"" in js
    s = _read(PRODUCTS_JSX)
    assert "lastCol = 'AO';" in s and "'AF', 'AG', 'AH', 'AI', 'AJ', 'AK', 'AL', 'AM', 'AN', 'AO'" in s


def test_frontend_own_export_columns_mapped_by_position():
    js = _read(PHARM_IMPORT_JS)
    assert 'export const pharmaExportColMap = (cols, fields) =>' in js
    assert "if (cols[0] !== '№' || normHeader(cols[21]) !== normHeader(PHARMA_EXPORT_HEADERS[0])) return null;" in js
    assert "1: 'Nomi', 4: 'Chakana narxi', 7: 'Ulgurji narxi', 10: 'Tan narxi', 14: 'Kategoriya', 15: 'Barkod'" in js
    s = _read(PRODUCTS_JSX)
    am = s[s.index('const autoMap = (rows) => {'):s.index('const parseExcel = async')]
    assert am.index('pharmaExportColMap(cols, IMPORT_FIELDS)') < am.index('pharmaMapHeader(col, IMPORT_FIELDS)')
    assert "'название товара', 'product name'" in js and "'Holat': ['holat', 'статус', 'status']" in js


def test_frontend_preview_does_not_require_expiry_or_mxik():
    js = _read(PHARM_IMPORT_JS)
    assert "warnings.push('lot')" not in js and "? ['lot'] : []" not in js and "warnings.push('mxik')" not in js


def test_mxik_is_optional_in_import(client, db, pharm):
    """MXIK majburiy emas: bo'sh — ogohlantirishsiz; Excel buzgan qiymat (3.0049E+16) — tovar saqlanadi, MXIK'siz."""
    c, _, w, u = pharm
    cl = client.login(u)
    body = _import(cl, [{'Nomi': 'MXIKsiz', 'Katta qadoq narxi': '1000', 'Qoldiq': '2'},
                        {'Nomi': 'Buzilgan', 'Katta qadoq narxi': '1000', 'MXIK': '3.0049E+16'}], warehouse_id=w.id)
    assert body['created'] == 2 and body['errors'] == [], body
    assert [x['name'] for x in body['warnings']] == ['Buzilgan'] and 'MXIK' in body['warnings'][0]['warning']
    # mavjud tovarda buzilgan MXIK eskisini o'chirmaydi
    p = _prod(db, c, 'MXIKsiz')
    p.mxik_code = '03004001001000001'
    db.flush()
    body = _import(cl, [{'Nomi': 'MXIKsiz', 'MXIK': 'abc'}], allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['errors'] == [], body
    db.expire_all()
    assert _prod(db, c, 'MXIKsiz').mxik_code == '03004001001000001'


def test_frontend_clean_number_keeps_minus():
    js = _read(PHARM_IMPORT_JS)
    assert "const neg = /^[-−]\\d/.test(s);" in js and "return (neg ? '-' : '') + s.replace(/[^0-9.]/g, '');" in js
