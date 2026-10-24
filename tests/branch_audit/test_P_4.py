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
        ['Paratsetamol 500 mg', '4780012345678', '', 'Paratsetamol', 'tabletka', '500 mg', 'Nika Pharm', "yo'q",
         '100 000', '5', '10', '70000', '3', 'LOT2026A', FUTURE, '01.12.2025', 'Dorilar', "O'zbekiston", '', 'N02BE01'],
        ['Ambroksol sirop 100 ml', '4780012345685', '', 'Ambroksol', 'sirop', '15 mg/5 ml', '', "yo'q",
         '25000', '', '', '18000', '10', '', FUTURE, '', 'Dorilar', '', '', ''],
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
           'Qoldiq (katta qadoq)': '2', 'MXIK': '03004001001000009'}
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
