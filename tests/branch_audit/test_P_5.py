"""P.5 — "Dori qo'shish" soddalashtirildi: tasnifdan avtomatik to'ldirish, seriya ixtiyoriy, keng oyna, partiyalarni tahrirlash.

Qamrov:
 1. /api/pharmacy/tasnif/search va /tasnif/barcode/{code}: nom, MXIK, ATX (kirillcha harflar ham), ishlab chiqaruvchi, shakl,
    doza, modda; shtrix-kod — avval mahalliy katalog, keyin tasnif (faqat aynan mos), topilgani katalogga yoziladi;
    topilmasa 404, tarmoq xatosi 502. Oddiy korxonada yopiq.
 2. PUT /api/pharmacy/batches/{id}: seriya, yaroqlilik muddati, ishlab chiqarilgan sana; tekshiruvlar, audit, izolyatsiya.
 3. Frontend: keng uch ustunli oyna, MXIK birinchi bo'limda, shtrix-kod bo'sh boshlanadi va skanerda qidiriladi,
    qadoq shtrix-kodlari / ishlab chiqarilgan sana / ro'yxat muddati maydonlari yo'q, tahrirda partiyalar; kirimda seriya
    majburiy emas.
 4. i18n (i18n_pending/P.5.json).
"""
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.product_pharma import PharmaSubstance
from app.models.tovarlar_catalog import TovarlarCatalog
from app.services.batch_allocator import tashkent_today

sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MODAL = 'frontend/src/components/PharmacyProductModal.jsx'
PRODUCTS = 'frontend/src/pages/admin/Products.jsx'
TASNIF_JSX = 'frontend/src/components/TasnifSearch.jsx'
PURCHASES = 'frontend/src/pages/admin/Purchases.jsx'
PENDING = 'tests/branch_audit/i18n_pending/P.5.json'
FUTURE = (tashkent_today() + timedelta(days=400)).isoformat()

SULFACIL = {
    "mxikCode": "03004569001002007",
    "name": "Сулфацетамид - S01AB04: СУЛЬФАЦИЛ (Фармак), Кўз томчилари 200 мг/мл 10мл флаконлар",
    "internationalCode": "4823002200737",
    "brandName": "СУЛЬФАЦИЛ (Фармак)",
    "attributeName": "Кўз томчилари 200 мг/мл 10мл флаконлар",
    "mnnName": "сульфацетамид",
    "unitsName": "шт (флакон (200 мг/мл ,10 мл)) ",
    "groupName": "ФАРМАЦЕВТИКА МАҲСУЛОТИ",
}
ENALOZID = {   # ATX kodi kirillcha harflar bilan (С09ВА02)
    "mxikCode": "03004185002009001",
    "name": "Эналаприл ва диуретиклар - С09ВА02: Эналозид (Фармак), таблеткалар №20(2x10)",
    "internationalCode": "4823002227918",
    "brandName": "Эналозид (Фармак)",
    "attributeName": "таблеткалар №20(2x10)",
    "mnnName": "эналаприл, гидрохлоротиазид",
}


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


@pytest.fixture
def fake_tasnif(monkeypatch):
    calls = []

    def fake(text, size=20, lang='uz', timeout=8.0):
        calls.append(text)
        return [it for it in (SULFACIL, ENALOZID)
                if text in it['internationalCode'] or text.lower() in it['name'].lower() or text in it['mxikCode']
                or text[:6] in it['internationalCode']]
    monkeypatch.setattr('app.services.tasnif_service.tasnif_search_sync', fake)
    return calls


# ───────────────────────── 1. Tasnif ─────────────────────────

def test_tasnif_search_parses_drug_fields(client, db, pharm, fake_tasnif):
    c, _, _, u = pharm
    db.add(PharmaSubstance(company_id=c.id, name_uz='Sulfatsetamid', name_ru='Сульфацетамид'))
    db.flush()
    r = client.login(u).get('/api/pharmacy/tasnif/search', params={'q': 'сульфацил'})
    assert r.status_code == 200, r.text
    (d,) = r.json()
    assert d['mxik_code'] == '03004569001002007' and d['barcode'] == '4823002200737'
    assert d['name'].startswith('Сулфацетамид - S01AB04')
    assert d['atc_code'] == 'S01AB04' and d['manufacturer'] == 'Фармак'
    assert d['dosage_form'] == 'drops' and d['strength'] == '200 мг/мл'
    assert d['substance_name'] == 'сульфацетамид' and [s['name_uz'] for s in d['substances']] == ['Sulfatsetamid']


def test_tasnif_cyrillic_atc_and_tablet_form(client, db, pharm, fake_tasnif):
    _, _, _, u = pharm
    (d,) = client.login(u).get('/api/pharmacy/tasnif/search', params={'q': 'эналозид'}).json()
    assert d['atc_code'] == 'C09BA02' and d['dosage_form'] == 'tablet' and d['manufacturer'] == 'Фармак'
    assert d['substances'] == []                      # mavjud modda yo'q — yangisi yaratilmaydi


def test_tasnif_barcode_catalog_first_then_tasnif_exact_and_cache(client, db, pharm, fake_tasnif):
    _, _, _, u = pharm
    cl = client.login(u)
    db.add(TovarlarCatalog(barcode='4780000001234', mxik_code='03004001001000005',
                           mxik_name='Парацетамол - N02BE01: Парацетамол (Nika), таблеткалар 500 мг'))
    db.flush()
    r = cl.get('/api/pharmacy/tasnif/barcode/4780000001234')
    assert r.status_code == 200 and r.json()['source'] == 'catalog' and r.json()['atc_code'] == 'N02BE01'
    assert fake_tasnif == []                          # katalogda topildi — tashqi so'rov yo'q
    r = cl.get('/api/pharmacy/tasnif/barcode/4823002200737')
    assert r.status_code == 200 and r.json()['mxik_code'] == '03004569001002007' and r.json()['source'] == 'tasnif'
    cached = db.query(TovarlarCatalog).filter(TovarlarCatalog.barcode == '4823002200737').one()
    assert cached.mxik_code == '03004569001002007'
    # tasnif o'xshash (boshqa shtrix-kodli) natija qaytarsa ham — faqat aynan mos qabul qilinadi
    r = cl.get('/api/pharmacy/tasnif/barcode/4823002250732')
    assert r.status_code == 404 and 'nomi' in r.json()['detail']


def test_tasnif_network_error_is_502(client, db, pharm, monkeypatch):
    _, _, _, u = pharm

    def boom(*a, **k):
        raise RuntimeError('tarmoq yo\'q')
    monkeypatch.setattr('app.services.tasnif_service.tasnif_search_sync', boom)
    cl = client.login(u)
    assert cl.get('/api/pharmacy/tasnif/search', params={'q': 'abc'}).status_code == 502
    assert cl.get('/api/pharmacy/tasnif/barcode/4799999999999').status_code == 502


def test_tasnif_and_batch_edit_closed_for_plain_company(client, db, mk, fake_tasnif):
    _, _, _, u = mk.tenant()
    cl = client.login(u)
    assert cl.get('/api/pharmacy/tasnif/search', params={'q': 'abc'}).status_code in (403, 404)
    assert cl.get('/api/pharmacy/tasnif/barcode/4823002200737').status_code in (403, 404)
    assert cl.put('/api/pharmacy/batches/1', json={'lot_number': 'X'}).status_code in (403, 404)
    assert fake_tasnif == []


# ───────────────────────── 2. Partiyani tahrirlash ─────────────────────────

def _drug_with_batch(cl, w, barcode='4780000005555'):
    r = cl.post('/api/products/', json={
        'name': 'Tahrir dori ' + barcode[-4:], 'barcode': barcode, 'sku': 'SKU-' + barcode[-6:], 'unit': 'dona',
        'product_type': 'stock', 'cost_price': 1000, 'sale_price': 2000, 'mxik_code': '03004001001000007',
        'initial_stock': 10, 'initial_warehouse_id': w.id, 'initial_expiry_date': FUTURE,
    })
    assert r.status_code == 201, r.text
    rows = cl.get('/api/pharmacy/batches', params={'product_id': r.json()['id']}).json()
    assert len(rows) == 1
    return r.json()['id'], rows[0]


def test_batch_edit_lot_and_dates_with_audit(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    pid, b = _drug_with_batch(cl, w)
    assert b['lot_number'] == f'initial-{pid}' and b['manufacture_date'] is None      # seriya ixtiyoriy edi
    new_exp = (tashkent_today() + timedelta(days=700)).isoformat()
    mfg = (tashkent_today() - timedelta(days=30)).isoformat()
    r = cl.put(f"/api/pharmacy/batches/{b['batch_id']}",
               json={'lot_number': 'LOT-77', 'expiry_date': new_exp, 'manufacture_date': mfg})
    assert r.status_code == 200, r.text
    assert r.json() == {'batch_id': b['batch_id'], 'lot_number': 'LOT-77', 'expiry_date': new_exp, 'manufacture_date': mfg,
                        'quantity': r.json()['quantity']}
    assert float(r.json()['quantity']) == 10
    row = cl.get('/api/pharmacy/batches', params={'product_id': pid}).json()[0]
    assert (row['lot_number'], row['expiry_date'], row['manufacture_date']) == ('LOT-77', new_exp, mfg)
    log = db.query(AuditLog).filter(AuditLog.action == 'BATCH_EDIT', AuditLog.entity_id == b['batch_id']).one()
    assert log.old_values['lot_number'] == f'initial-{pid}' and log.new_values['lot_number'] == 'LOT-77'
    # faqat ishlab chiqarilgan sanani o'chirish; bo'sh seriya avvalgisini o'chirmaydi
    r = cl.put(f"/api/pharmacy/batches/{b['batch_id']}", json={'manufacture_date': None, 'lot_number': '  '})
    assert r.status_code == 200 and r.json()['manufacture_date'] is None and r.json()['lot_number'] == 'LOT-77'


def test_batch_edit_validation_and_isolation(client, db, pharm, mk):
    c, _, w, u = pharm
    cl = client.login(u)
    _, b = _drug_with_batch(cl, w, barcode='4780000005556')
    url = f"/api/pharmacy/batches/{b['batch_id']}"
    assert cl.put(url, json={'expiry_date': None}).status_code == 400
    assert cl.put(url, json={'manufacture_date': FUTURE}).status_code == 400              # muddatdan oldin emas
    assert cl.put(url, json={'lot_number': 'x' * 101}).status_code == 400
    c2, _, _, u2 = mk.tenant()
    _pharmacy_on(db, c2)
    assert client.login(u2).put(url, json={'lot_number': 'BEGONA'}).status_code == 404
    assert db.get(Batch, b['batch_id']).lot_number != 'BEGONA'


# ───────────────────────── 3. Frontend ─────────────────────────

def test_modal_wide_three_columns_and_simplified():
    s = _read(MODAL)
    body = s[s.index('export default function PharmacyProductModal'):]
    assert 'max-w-[1500px] h-[96vh]' in body and 'lg:grid-cols-3' in body
    # MXIK birinchi bo'limda (2-bo'limdan oldin), tasnifdan qidirish va shtrix-kod bo'yicha avtomatik
    assert body.index("tf('pharmaProduct.mxik'") < body.index("tf('drugForm.packTitle'")
    assert "import TasnifSearch, { lookupDrugByBarcode } from './TasnifSearch';" in s
    assert 'const res = await lookupDrugByBarcode(code);' in body and '<TasnifSearch' in body
    assert "if (!product) return { form: { ...base }, pack: { ...emptyPack }, pharma: pharmaToForm(null) };" in s
    assert "const barcode = form.barcode.trim() || genBarcodeByFormat('ean13');" in body
    # olib tashlangan maydonlar: qadoq shtrix-kodlari, ishlab chiqarilgan sana (qo'shishda), ro'yxat muddati
    for bad in ('big_barcode', 'mid_barcode', 'reg_valid_until', 'BARCODE_FORMATS.map'):
        assert bad not in body, bad
    # seriya va ishlab chiqarilgan sana ixtiyoriy (yulduzchasiz), yaroqlilik muddati majburiy
    # P.6: qadoq, narx va qoldiq — "Ko'p mahsulot qo'shish" yashil qatori tartibida
    stock = body[body.index("tf('drugForm.packTitle'"):body.index("{/* 3. Partiyalar (tahrirda) + Batafsil */}")]
    order = [stock.index(k) for k in ("'pharmacyModal.bigPrice'", "tf('packStruct.bulkMidCount'", "tf('packStruct.bulkUnitCount'",
                                      "tf('packStruct.bulkStockBig'", "tf('packStruct.lot'", "tf('packStruct.expiry'",
                                      "tf('drugForm.mfgOptional'")]
    assert order == sorted(order)
    assert "setP({ mfg: e.target.value })" in stock and "required={stockTotal > 0}" in stock
    assert 'PackStockFields' not in s and 'AutoTag' not in s and "form.mode" not in s
    assert 'if (pack.mfg) payload.initial_manufacture_date = pack.mfg;' in body
    v = s[s.index('export const validatePack'):s.index('export function SubstancePicker')]
    assert "packStruct.errLot" not in v                  # seriya ixtiyoriy
    # tahrirda partiyalar: seriya, muddat, ishlab chiqarilgan sana
    assert "api.get('/pharmacy/batches', { params: { product_id: product.id" in body
    assert 'await api.put(`/pharmacy/batches/${b.batch_id}`, body' in body
    assert "setB(b.batch_id, { manufacture_date: e.target.value })" in body


def test_purchases_lot_not_required_and_tasnif_component():
    p = _read(PURCHASES)
    assert "t('purchase.phLotRequired')" not in p
    assert "{t('purchase.lotNumber')} <span className=\"text-red-500\">*</span>" not in p
    assert "lot_number: String(l.lot || '').trim() || null" in p
    t = _read(TASNIF_JSX)
    assert "api.get('/pharmacy/tasnif/search'" in t and '/pharmacy/tasnif/barcode/' in t
    assert "if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); run(q); }" in t   # forma yuborilmaydi
    # "Ko'p mahsulot qo'shish" (yashil qator): seriya majburiy emas, dori shakli va ishlab chiqarilgan sana bor
    b = _read(PRODUCTS)
    assert not __import__('os').path.exists(__import__('os').path.join(ROOT, 'frontend/src/components/PharmacyBulkAddModal.jsx'))
    assert "updatePkField(row._key, 'pk_form'" in b and "updatePkField(row._key, 'pk_mfg'" in b
    assert "{tf('packStruct.lot', 'Seriya raqami')}</label>" in b


# ───────────────────────── 4. i18n ─────────────────────────

def test_i18n_p5_complete_and_merged_once():
    with open(os.path.join(ROOT, PENDING), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    src = _read(MODAL) + _read(TASNIF_JSX) + _read(PRODUCTS)
    used = set(re.findall(r"tf\('((?:drugForm|tasnif)\.[A-Za-z0-9_.]+)'", src))
    # P.9 kalitlari (qoldiqni tahrirlash) o'z faylida
    with open(os.path.join(ROOT, 'tests/branch_audit/i18n_pending/P.9.json'), encoding='utf-8') as f:
        p9 = set(json.load(f)['uz'])
    assert used and used <= set(data['uz']) | p9, sorted(used - set(data['uz']) - p9)
    for lang in ('uz', 'ru', 'en'):
        txt = _read(f'frontend/src/i18n/{lang}.js')
        for k in data[lang]:
            n = len(re.findall(r"^\s*['\"]" + re.escape(k) + r"['\"]\s*:", txt, re.M))
            assert n == 1, f'{k} {lang}.js da {n} marta'
