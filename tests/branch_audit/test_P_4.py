"""P.4 — Excel import dorixonaga moslashtirildi (faqat dorixona yoqilganda).

Qamrov:
 1. Backend (product_import.py, faqat pharmacy_on): MXIK ustuni (bo'sh bo'lsa mahalliy katalogdan, topilmasa ogohlantirish,
    noto'g'ri bo'lsa qator xatosi); "Katta qadoq tan narxi" va "Qoldiq (katta qadoq)" donaga o'tkaziladi; qadoq nomlari
    sukut bo'yicha quti/blister; faqat narx — qadoqsiz (1 dona); yangilashda faqat narx berilsa mavjud tuzilma bo'yicha
    qayta hisob; ATX kodi. Oddiy korxonada yangi ustunlar e'tiborsiz.
 2. Shablon -> import (uchidan-uchiga): pharmacyImport.js dagi sarlavhalar taxalluslar orqali tanilib, server to'g'ri saqlaydi.
 3. Frontend: alohida ro'yxat/shablon/ustun tanish/sana/hisob ustuni faqat pharmacyOn da; oddiy import avvalgidek.
 4. i18n (i18n_pending/P.4.json).
"""
import json
import os
import re
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
from app.services.batch_allocator import tashkent_today

sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PRODUCTS_JSX = 'frontend/src/pages/admin/Products.jsx'
PHARM_IMPORT_JS = 'frontend/src/pages/admin/products/pharmacyImport.js'
PENDING = 'tests/branch_audit/i18n_pending/P.4.json'
URL = '/api/products/'
IMPORT_URL = '/api/products/bulk-import'
FUTURE = (tashkent_today() + timedelta(days=400)).isoformat()


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _pharmacy_on(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code='pharmacy', is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


@pytest.fixture
def pharm(db, mk):
    c, b, w, u = mk.tenant()
    _pharmacy_on(db, c)
    return c, b, w, u


def _prod(db, c, name):
    return db.query(Product).filter(Product.company_id == c.id, Product.name == name).one()


def _units(db, pid):
    return [(x.name, int(x.ratio), Decimal(str(x.sale_price)) if x.sale_price is not None else None)
            for x in db.query(ProductUnit).filter(ProductUnit.product_id == pid).order_by(ProductUnit.ratio).all()]


def _import(cl, rows, **params):
    for i, r in enumerate(rows):
        r.setdefault('__row_index', i + 2)
    r = cl.post(IMPORT_URL, json=rows, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# ── JS dagi taxalluslar va shablon sarlavhalari (Python nusxasi: normHeader bilan bir xil) ──

def _norm(h):
    s = re.sub(r"[ʻʼ`’‘]", "'", str(h).lower())
    s = re.sub(r"[*:]+$", '', s)
    return re.sub(r'\s+', ' ', s).strip()


def _alias_index():
    s = _read(PHARM_IMPORT_JS)
    block = s[s.index('const ALIASES = {'):s.index('\n};', s.index('const ALIASES = {'))]
    idx = {}
    for k1, k2, body in re.findall(r"(?:'((?:[^'\\]|\\.)*)'|\"([^\"]*)\")\s*:\s*\[(.*?)\]", block, re.S):
        key = (k1 or k2).replace("\\'", "'")
        for a1, a2 in re.findall(r"'((?:[^'\\]|\\.)*)'|\"([^\"]*)\"", body):
            idx.setdefault(_norm((a1 or a2).replace("\\'", "'")), key)
    return idx


def _template_headers():
    s = _read(PHARM_IMPORT_JS)
    block = s[s.index('export const PHARMA_TEMPLATE_HEADERS = ['):s.index('];', s.index('export const PHARMA_TEMPLATE_HEADERS'))]
    return [(a1 or a2).replace("\\'", "'") for a1, a2 in re.findall(r"'((?:[^'\\]|\\.)*)'|\"([^\"]*)\"", block)]


def test_template_headers_all_recognized_and_aliases_point_to_known_columns():
    from app.routers.product_import import (FIELD_MAP, LOT_COLUMNS, PACK_COLUMNS, PHARMA_COLUMNS,
                                            PHARMA_EXTRA_COLUMNS)
    idx = _alias_index()
    headers = _template_headers()
    assert len(headers) == 20
    mapped = [idx.get(_norm(h)) for h in headers]
    assert None not in mapped, [h for h, m in zip(headers, mapped) if m is None]
    assert len(set(mapped)) == len(mapped)                       # ikki sarlavha bitta ustunga tushmaydi
    known = set(FIELD_MAP) | set(PHARMA_COLUMNS) | set(PACK_COLUMNS) | set(LOT_COLUMNS) | set(PHARMA_EXTRA_COLUMNS)
    assert set(idx.values()) <= known, sorted(set(idx.values()) - known)
    # ruscha sarlavhalar
    for ru, key in (('Наименование', 'Nomi'), ('Штрихкод', 'Barkod'), ('ИКПУ', 'MXIK'), ('Серия', 'Seriya'),
                    ('Срок годности', 'Yaroqlilik muddati'), ('Производитель', 'Ishlab chiqaruvchi'),
                    ('Цена', 'Katta qadoq narxi'), ('Количество', 'Qoldiq (katta qadoq)')):
        assert idx.get(_norm(ru)) == key, ru


def _template_rows():
    """Shablondagi ikkita namuna (muddat — kelajakdagi sana), sarlavhalar taxalluslar orqali kalitlarga."""
    idx = _alias_index()
    headers = _template_headers()
    values = [
        # P.6: "Ko'p mahsulot qo'shish" tartibi — quti narxi, blister soni, dona soni, quti soni, seriya, muddat, shakl, sana
        ['Paratsetamol 500 mg', '4780012345678', '', '100 000', '5', '10', '3', 'LOT2026A', FUTURE, 'tabletka', '01.12.2025',
         '70000', 'Paratsetamol', '500 mg', 'Nika Pharm', "yo'q", 'Dorilar', "O'zbekiston", '', 'N02BE01'],
        ['Ambroksol sirop 100 ml', '4780012345685', '', '25000', '', '', '10', '', FUTURE, 'sirop', '',
         '18000', 'Ambroksol', '15 mg/5 ml', '', "yo'q", 'Dorilar', '', '', ''],
    ]
    return [{idx[_norm(h)]: v for h, v in zip(headers, vals) if v != ''} for vals in values]


def test_template_rows_import_end_to_end(client, db, pharm):
    c, _, w, u = pharm
    rows = _template_rows()
    rows[0]['Katta qadoq narxi'] = '100000'      # frontend tozalab yuboradi (cleanPharmaNum)
    body = _import(client.login(u), rows, warehouse_id=w.id)
    assert body['created'] == 2 and body['total_errors'] == 0, body
    # MXIK yo'q, katalog bo'sh — ikkala qatorga ogohlantirish
    assert len([x for x in body['warnings'] if 'MXIK' in x['warning']]) == 2

    p = _prod(db, c, 'Paratsetamol 500 mg')
    assert _units(db, p.id) == [('blister', 10, Decimal(20000)), ('quti', 50, Decimal(100000))]
    assert Decimal(str(p.sale_price)) == 2000 and Decimal(str(p.cost_price)) == 1400       # 70 000 / 50
    b = db.query(Batch).filter(Batch.product_id == p.id).one()
    assert Decimal(str(b.quantity)) == 150 and b.lot_number == 'LOT2026A'                  # 3 quti
    assert b.manufacture_date.date().isoformat() == '2025-12-01'                             # P.5: ixtiyoriy sana
    ph = db.query(ProductPharma).filter(ProductPharma.product_id == p.id).one()
    assert ph.dosage_form == 'tablet' and ph.strength == '500 mg' and ph.atc_code == 'N02BE01'
    assert ph.manufacturer == 'Nika Pharm' and ph.is_rx is False and ph.pack_qty == 50

    s = _prod(db, c, 'Ambroksol sirop 100 ml')                                              # qadoqsiz
    assert _units(db, s.id) == []
    assert Decimal(str(s.sale_price)) == 25000 and Decimal(str(s.cost_price)) == 18000
    sb = db.query(Batch).filter(Batch.product_id == s.id).one()
    assert Decimal(str(sb.quantity)) == 10 and sb.manufacture_date is None and sb.lot_number    # seriyasiz — avto nom


def test_import_manufacture_date_validation(client, db, pharm):
    c, _, w, u = pharm
    rows = [
        {'Nomi': 'F1', 'Barkod': '4780000009401', 'Katta qadoq narxi': '5000', 'Qoldiq (katta qadoq)': '1',
         'Yaroqlilik muddati': FUTURE, 'Ishlab chiqarilgan sana': 'xato'},
        {'Nomi': 'F2', 'Barkod': '4780000009402', 'Katta qadoq narxi': '5000', 'Qoldiq (katta qadoq)': '1',
         'Yaroqlilik muddati': FUTURE, 'Ishlab chiqarilgan sana': FUTURE},                     # muddatdan oldin emas
        {'Nomi': 'F3', 'Barkod': '4780000009403', 'Katta qadoq narxi': '5000', 'Qoldiq (katta qadoq)': '1',
         'Yaroqlilik muddati': FUTURE, 'Ishlab chiqarilgan sana': '15.01.2026', 'Seriya': 'L-F3'},
    ]
    body = _import(client.login(u), rows, warehouse_id=w.id)
    assert body['created'] == 1, body
    errs = {e['row']: e['error'] for e in body['errors']}
    assert set(errs) == {2, 3} and "noto'g'ri" in errs[2] and 'oldin' in errs[3]
    b = db.query(Batch).filter(Batch.product_id == _prod(db, c, 'F3').id).one()
    assert b.lot_number == 'L-F3' and b.manufacture_date.date().isoformat() == '2026-01-15'


def test_mxik_column_catalog_lookup_and_invalid(client, db, pharm):
    from app.models.tovarlar_catalog import TovarlarCatalog
    c, _, w, u = pharm
    db.add(TovarlarCatalog(barcode='4780000009002', mxik_code='03004001001000002', mxik_name='Katalog dori'))
    db.flush()
    rows = [
        {'Nomi': 'M1', 'Barkod': '4780000009001', 'MXIK': '03004 001 001 000 001', 'Katta qadoq narxi': '1000'},
        {'Nomi': 'M2', 'Barkod': '4780000009002', 'Katta qadoq narxi': '1000'},                    # katalogdan
        {'Nomi': 'M3', 'Barkod': '4780000009003', 'MXIK': '3.0049E+16', 'Katta qadoq narxi': '1000'},
    ]
    body = _import(client.login(u), rows, warehouse_id=w.id)
    assert body['created'] == 2, body
    assert [e['row'] for e in body['errors']] == [4] and 'MXIK' in body['errors'][0]['error']
    assert _prod(db, c, 'M1').mxik_code == '03004001001000001'
    assert _prod(db, c, 'M2').mxik_code == '03004001001000002'
    assert not [x for x in body['warnings'] if 'MXIK' in x['warning']]


def test_update_price_only_reprices_existing_structure_and_box_stock(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    created = cl.post(URL, json={
        'name': 'Ibuprofen 200', 'barcode': '4780000009101', 'sku': 'SKU-P4U', 'unit': 'dona', 'product_type': 'stock',
        'cost_price': 1000, 'sale_price': 2000, 'mxik_code': '03004001001000003',
        'units': [{'name': 'blister', 'ratio': 10, 'sale_price': 20000}, {'name': 'quti', 'ratio': 50, 'sale_price': 100000}],
    })
    assert created.status_code == 201, created.text
    pid = created.json()['id']
    row = {'Nomi': 'Ibuprofen 200', 'Katta qadoq narxi': '120000', 'Katta qadoq tan narxi': '60000',
           'Qoldiq (katta qadoq)': '2', 'MXIK': '03004001001000009',
           'Yaroqlilik muddati': FUTURE}   # P.6: dorixonada qoldiq oshishi — muddatli yangi partiya
    body = _import(cl, [row], allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1, body
    p = db.get(Product, pid)
    db.refresh(p)
    assert _units(db, pid) == [('blister', 10, Decimal(24000)), ('quti', 50, Decimal(120000))]
    assert Decimal(str(p.sale_price)) == 2400 and Decimal(str(p.cost_price)) == 1200
    assert p.mxik_code == '03004001001000009'
    lvl = db.query(StockLevel).filter(StockLevel.product_id == pid, StockLevel.warehouse_id == w.id).one()
    assert Decimal(str(lvl.quantity)) == 100                                                # 2 quti x 50


def test_plain_company_ignores_new_pharmacy_columns(client, db, mk):
    c, _, w, u = mk.tenant()                    # dorixona yoqilmagan
    row = {'Nomi': 'Shampun', 'Barkod': '4780000009201', 'MXIK': 'xato', 'Katta qadoq tan narxi': '5000',
           'Qoldiq (katta qadoq)': '4', 'ATX kodi': 'Z'}
    body = _import(client.login(u), [row], warehouse_id=w.id)
    assert body['created'] == 1 and body['total_errors'] == 0 and body['warnings'] == [], body
    p = _prod(db, c, 'Shampun')
    assert p.mxik_code is None and Decimal(str(p.cost_price)) == 0
    assert db.query(Batch).filter(Batch.product_id == p.id).count() == 0
    assert db.query(ProductPharma).filter(ProductPharma.product_id == p.id).count() == 0


def test_box_stock_requires_lot_and_negative_rejected(client, db, pharm):
    c, _, w, u = pharm
    rows = [
        {'Nomi': 'S1', 'Barkod': '4780000009301', 'Katta qadoq narxi': '5000', "O'rta qadoqdagi dona soni": '10',
         'Qoldiq (katta qadoq)': '2'},                                                          # seriya yo'q
        {'Nomi': 'S2', 'Barkod': '4780000009302', 'Katta qadoq narxi': '5000', 'Qoldiq (katta qadoq)': '-1'},
        {'Nomi': 'S3', 'Barkod': '4780000009303', 'Katta qadoq narxi': '5000', "O'rta qadoqdagi dona soni": '10',
         'Qoldiq (katta qadoq)': '2', 'Seriya': 'L3', 'Yaroqlilik muddati': FUTURE},
    ]
    rows.append({'Nomi': 'S4', 'Barkod': '4780000009304', 'Katta qadoq narxi': '5000', 'Qoldiq (katta qadoq)': '1',
                 'Yaroqlilik muddati': FUTURE})                                               # P.5: seriyasiz — OK
    body = _import(client.login(u), rows, warehouse_id=w.id)
    assert body['created'] == 2, body
    errs = {e['row']: e['error'] for e in body['errors']}
    assert set(errs) == {2, 3} and 'Yaroqlilik' in errs[2] and 'manfiy' in errs[3]
    s3 = _prod(db, c, 'S3')
    assert _units(db, s3.id) == [('quti', 10, Decimal(5000))] and Decimal(str(s3.sale_price)) == 500
    assert Decimal(str(db.query(Batch).filter(Batch.product_id == s3.id).one().quantity)) == 20


# ───────────────────────── 3. Frontend ─────────────────────────

def test_frontend_pharmacy_import_only_in_pharmacy_mode():
    s = _read(PRODUCTS_JSX)
    assert "} from './products/pharmacyImport';" in s
    # ro'yxat, ustun tanish, sana, sonlarni tozalash, shablon — faqat pharmacyOn
    assert 'const IMPORT_FIELDS = pharmacyOn ? [' in s
    assert 'const key = pharmaMapHeader(col, IMPORT_FIELDS);' in s
    assert "const dateOpt = pharmacyOn ? { dateNF: 'yyyy-mm-dd' } : {};" in s
    assert 'if (pharmacyOn && PHARMA_NUM_KEYS.includes(fieldKey)) {' in s
    assert 'if (pharmacyOn) { downloadPharmacyTemplate(XLSX, saveAs); return; }' in s
    # oddiy korxona: avvalgi ustun tanish va narx tozalash saqlangan
    assert "const found = IMPORT_FIELDS.find(f => f.label.toLowerCase().includes(lc) || f.key.toLowerCase() === lc" in s
    assert "val = String(val || \"\").replace(/\\s/g, '').replace(',', '.').replace(/[^0-9.]/g, '');" in s
    # oyna: sarlavha, yo'riqnoma, hisob ustuni, tugma
    assert "pharmacyOn ? tf('pharmacyImport.title'" in s and "{pharmacyOn && (\n                <div className=\"mt-3 px-4 py-3 bg-emerald-50" in s
    assert s.count('pharmaImportPreview(') == 1 and "tf('pharmacyImport.previewCol'" in s
    assert "pharmacyOn ? tf('pharmacyImport.button', 'Dori import') : t('product.import')" in s


def _clean_num(v):
    """cleanPharmaNum ning Python nusxasi."""
    s = re.sub(r'[\s ]', '', str(v))
    if ',' in s and '.' in s:
        s = s.replace(',', '')
    elif re.fullmatch(r'\d{1,3}(,\d{3})+', s):
        s = s.replace(',', '')
    else:
        s = s.replace(',', '.', 1)
    return re.sub(r'[^0-9.]', '', s)


def test_clean_number_rules():
    assert _clean_num('100 000') == '100000'
    assert _clean_num('100,000') == '100000'
    assert _clean_num('100,000.50') == '100000.50'
    assert _clean_num('12,5') == '12.5'
    assert _clean_num("25 000 so'm") == '25000'
    js = _read(PHARM_IMPORT_JS)
    for token in ("if (s.includes(',') && s.includes('.')) s = s.replace(/,/g, '');",
                  r"else if (/^\d{1,3}(,\d{3})+$/.test(s)) s = s.replace(/,/g, '');",
                  "else s = s.replace(',', '.');"):
        assert token in js, token


# ───────────────────────── 4. i18n ─────────────────────────

def test_i18n_p4_complete_and_merged_once():
    with open(os.path.join(ROOT, PENDING), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    assert all(v.strip() for lang in data.values() for v in lang.values())
    used = set(re.findall(r"'(pharmacyImport\.[A-Za-z0-9_.]+)'", _read(PRODUCTS_JSX) + _read(PHARM_IMPORT_JS)))
    assert used and used <= set(data['uz']), sorted(used - set(data['uz']))
    for lang in ('uz', 'ru', 'en'):
        txt = _read(f'frontend/src/i18n/{lang}.js')
        for k in data[lang]:
            n = len(re.findall(r"^\s*['\"]" + re.escape(k) + r"['\"]\s*:", txt, re.M))
            assert n == 1, f'{k} {lang}.js da {n} marta'

# ───────────────────────── P.6: sanalar va mavjud dori qoldig'i ─────────────────────────

def test_date_cell_formats():
    from app.routers.product_import import _parse_date_cell
    for raw in ('2027-12-31', '2027/12/31', '2027.12.31', '31.12.2027', '31/12/2027', '31.12.27', '12/31/2027',
                '31.12.2027 00:00:00', '2027-12', '12.2027'):
        assert _parse_date_cell(raw).isoformat() == '2027-12-31', raw
    assert _parse_date_cell('05/06/2027').isoformat() == '2027-06-05'      # ikkalasi <= 12 — kun.oy (O'zbekiston tartibi)
    with pytest.raises(ValueError):
        _parse_date_cell('31.13.2027')


def test_update_existing_drug_stock_goes_through_batches(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    created = cl.post(URL, json={
        'name': 'Sitramon', 'barcode': '4780000009501', 'sku': 'SKU-P6U', 'unit': 'dona', 'product_type': 'stock',
        'cost_price': 500, 'sale_price': 1000, 'mxik_code': '03004001001000012',
        'initial_stock': 20, 'initial_warehouse_id': w.id, 'initial_expiry_date': FUTURE,
    })
    assert created.status_code == 201, created.text
    pid = created.json()['id']

    def level():
        db.expire_all()
        return Decimal(str(db.query(StockLevel).filter(StockLevel.product_id == pid, StockLevel.warehouse_id == w.id).one().quantity))

    # oshirish muddatsiz — qoldiq o'zgarmaydi, ogohlantirish
    body = _import(cl, [{'Nomi': 'Sitramon', 'Qoldiq': '30'}], allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and any('muddati' in x['warning'] for x in body['warnings']), body
    assert level() == 20
    # oshirish muddat, seriya va ishlab chiqarilgan sana bilan — farq (10) yangi partiya bo'lib kiradi
    body = _import(cl, [{'Nomi': 'Sitramon', 'Qoldiq': '30', 'Yaroqlilik muddati': FUTURE, 'Seriya': 'S-NEW',
                         'Ishlab chiqarilgan sana': '01.01.2026'}], allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1 and body['warnings'] == [], body
    assert level() == 30
    new = db.query(Batch).filter(Batch.product_id == pid, Batch.lot_number == 'S-NEW').one()
    assert Decimal(str(new.quantity)) == 10 and new.manufacture_date.date().isoformat() == '2026-01-01'
    assert sum(Decimal(str(b.quantity)) for b in db.query(Batch).filter(Batch.product_id == pid).all()) == 30
    # kamaytirish — inventarizatsiya orqali (import o'zgartirmaydi)
    body = _import(cl, [{'Nomi': 'Sitramon', 'Qoldiq': '5'}], allow_update='true', warehouse_id=w.id)
    assert any('Inventarizatsiya' in x['warning'] for x in body['warnings']), body
    assert level() == 30


def test_frontend_reads_excel_dates_as_iso_only_in_pharmacy():
    s = _read(PRODUCTS_JSX)
    assert "...(pharmacyOn ? { cellNF: true } : {})" in s and 'if (pharmacyOn) isoDateCells(XLSX, ws);' in s
    js = _read(PHARM_IMPORT_JS)
    assert 'export const isoDateCells = (XLSX, ws) =>' in js
    assert 'SSF.parse_date_code(c.v)' in js and "c.t !== 'n' || !c.z || !SSF.is_date(c.z)" in js


# ───────────────────────── P.6: shablon tartibi va Excel'ga yuklab olish ─────────────────────────

def test_template_order_matches_bulk_add_strip():
    headers = _template_headers()
    assert headers[3:11] == ['1 quti narxi', 'Qutidagi blister soni', 'Blisterdagi dona soni', 'Quti soni (qoldiq)',
                             'Seriya', 'Yaroqlilik muddati', 'Dori shakli', 'Ishlab chiqarilgan sana']
    assert headers[2] == 'MXIK kodi'


def _export_row(p):
    """pharmaExportRow ning Python nusxasi."""
    qty = float(p.get('stock_quantity') or 0)
    us = sorted([(float(u['ratio']), u.get('sale_price') if u.get('sale_price') is not None else u.get('price'))
                 for u in p.get('units') or [] if float(u['ratio']) > 1])
    simple = len(us) == 1 or (len(us) == 2 and (us[1][0] / us[0][0]).is_integer())
    mx = p.get('mxik_code') or ''
    nb = p.get('nearest_batch') or {}
    tail = [nb.get('lot_number') or '', nb.get('expiry_date') or '', nb.get('manufacture_date') or '', '']   # P.9: Ombor
    if not simple:
        return [mx, float(p.get('sale_price') or 0), '', '', round(qty, 3)] + tail
    big = us[-1]
    box = float(big[1]) if big[1] is not None else float(p.get('sale_price') or 0) * big[0]
    if len(us) == 2:
        return [mx, box, big[0] / us[0][0], us[0][0], round(qty / big[0], 3)] + tail
    return [mx, box, '', big[0], round(qty / big[0], 3)] + tail


def test_export_columns_roundtrip_with_import(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    body = _import(cl, [dict(r) for r in _template_rows()], warehouse_id=w.id)
    assert body['created'] == 2, body
    items = cl.get('/api/products/paginated', params={'limit': 100}).json()['items']
    by = {it['name']: it for it in items}
    para, sirop = by['Paratsetamol 500 mg'], by['Ambroksol sirop 100 ml']
    assert _export_row(para) == ['', 100000.0, 5.0, 10.0, 3.0, 'LOT2026A', FUTURE, '2025-12-01', '']   # 150 dona = 3 quti
    assert _export_row(sirop) == ['', 25000.0, '', '', 10.0, sirop['nearest_batch']['lot_number'], FUTURE, '', '']
    assert para['pharma']['dosage_form'] == 'tablet'
    # JS funksiya va sarlavhalar import shablonidagidek
    js = _read(PHARM_IMPORT_JS)
    blk = js[js.index('export const PHARMA_EXPORT_HEADERS = ['):js.index('];', js.index('export const PHARMA_EXPORT_HEADERS'))]
    ex_headers = re.findall(r"'([^']*)'", blk)
    assert ex_headers == ['MXIK kodi', '1 quti narxi', 'Qutidagi blister soni', 'Blisterdagi dona soni',
                          'Quti soni (qoldiq)', 'Seriya', 'Yaroqlilik muddati', 'Dori shakli', 'Ishlab chiqarilgan sana',
                          'Ombor']
    idx = _alias_index()
    assert all(idx.get(_norm(h)) for h in ex_headers)                      # qayta import qilinganda tanilad
    assert "return us.length === 2" in js and 'r3(qty / big.ratio)' in js


def test_export_columns_only_in_pharmacy_mode():
    s = _read(PRODUCTS_JSX)
    blk = s[s.index('// P.6/P.8: dorixonada oxiriga MXIK, qadoq, seriya va sanalar'):s.index("ws['!ref'] = `A1:${lastCol}")]
    assert 'if (pharmacyOn) {' in blk and 'pharmaExportRow(p, formLabel, b, lotOnly)' in blk
    assert "let lastCol = 'U';" in blk and "lastCol = 'AE';" in blk
    assert "...(pharmacyOn ? [{ wch: 20 }" in s


# ───────────────────────── P.8: sanalar — avval sanasiz kiritilganlar va qoldiqsiz qatorlar ─────────────────────────

def test_reimport_fills_dates_on_batches_without_expiry(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    # avval sanasiz kiritilgan qoldiq (masalan, modul yoqilishidan oldin): muddatsiz partiya
    p = Product(name='Eski dori', barcode='4780000009601', sku='SKU-P8-1', company_id=c.id,
                cost_price=Decimal('500'), sale_price=Decimal('1000'))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=w.id, quantity=Decimal('40')))
    db.add(Batch(product_id=p.id, warehouse_id=w.id, quantity=Decimal('40'), initial_quantity=Decimal('40'),
                 purchase_price=Decimal('500'), company_id=c.id, lot_number='manual'))
    db.flush()
    body = _import(cl, [{'Nomi': 'Eski dori', 'Yaroqlilik muddati': FUTURE, 'Ishlab chiqarilgan sana': '01.02.2026',
                         'Seriya': 'S-OLD'}], allow_update='true', warehouse_id=w.id)
    assert body['updated'] == 1, body
    db.expire_all()
    b = db.query(Batch).filter(Batch.product_id == p.id).one()
    assert str(b.expiry_date)[:10] == FUTURE and b.manufacture_date.date().isoformat() == '2026-02-01'
    assert b.lot_number == 'S-OLD' and Decimal(str(b.quantity)) == 40         # qoldiq o'zgarmadi
    # muddati bor partiyaga boshqa muddat yozilmaydi
    other = (tashkent_today() + timedelta(days=700)).isoformat()
    _import(cl, [{'Nomi': 'Eski dori', 'Yaroqlilik muddati': other}], allow_update='true', warehouse_id=w.id)
    db.expire_all()
    assert str(db.query(Batch).filter(Batch.product_id == p.id).one().expiry_date)[:10] == FUTURE


def test_dates_without_stock_warn(client, db, pharm):
    c, _, w, u = pharm
    body = _import(client.login(u), [{'Nomi': 'Qoldiqsiz', 'Barkod': '4780000009602', 'Katta qadoq narxi': '1000',
                                      'Yaroqlilik muddati': FUTURE}], warehouse_id=w.id)
    assert body['created'] == 1 and any('Qoldiq kiritilmagan' in x['warning'] for x in body['warnings']), body


def test_paginated_returns_nearest_batch_for_export(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    _import(cl, [{'Nomi': 'Partiyali', 'Barkod': '4780000009603', 'Katta qadoq narxi': '1000', 'Qoldiq': '5',
                  'Seriya': 'NB-1', 'Yaroqlilik muddati': FUTURE, 'Ishlab chiqarilgan sana': '2026-03-01'}],
            warehouse_id=w.id)
    items = cl.get('/api/products/paginated', params={'limit': 100}).json()['items']
    it = next(x for x in items if x['name'] == 'Partiyali')
    assert it['nearest_batch'] == {'lot_number': 'NB-1', 'expiry_date': FUTURE, 'manufacture_date': '2026-03-01'}


def test_paginated_plain_company_has_no_batch_field(client, db, mk):
    c, _, w, u = mk.tenant()
    client.login(u).post(IMPORT_URL, json=[{'Nomi': 'Oddiy P8', 'Barkod': '4780000009604', 'Qoldiq': '3'}],
                         params={'warehouse_id': w.id})
    items = client.login(u).get('/api/products/paginated', params={'limit': 100}).json()['items']
    assert 'nearest_batch' not in next(x for x in items if x['name'] == 'Oddiy P8')
