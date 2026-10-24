"""P.2 — Alohida "Dori qo'shish" oynasi va qadoq tuzilmasi: frontend.

Qamrov:
 1. ProductAddModal (oddiy forma) da dorixonaga oid hech narsa yo'q (pharma, substance_ids, "Dori ma'lumotlari", qadoq tuzilmasi),
    yaroqlilik muddati maydoni avvalgidek qoladi.
 2. PharmacyProductModal: calcPackPrices (100000 / 5 / 10 -> 20000 / 2000), units, initial_lot_number, initial_expiry_date,
    initial_manufacture_date yuborilishi, "Batafsil" bloki (sukut bo'yicha yopiq), ATX izohi, tahrirda PUT.
 3. Products.jsx: dorixona rejimida ikki tugma ("Dori qo'shish" + "Boshqa mahsulot"), oddiy korxonada bitta tugma;
    pharma bor mahsulot tahrirlashda PharmacyProductModal, ro'yxatda qadoq ko'rinishi.
 4. i18n (i18n_pending/P.2.json): uch tilda bir xil kalitlar, koddagi hamma kalit mavjud, umumiy lug'atlarda aynan bir marta.
 5. API shartnomasi (oyna yuboradigan payload): dorixonada units + seriya/muddatli qoldiq saqlanadi; oddiy korxonada units
    e'tiborsiz (regressiya); ikki korxona izolyatsiyasi.
 6. Sintaksis (jsxcheck) va narx formulasi (node bo'lsa — JS funksiyaning o'zi ishga tushiriladi).

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_P_2.py -q -p no:cacheprovider
"""
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.product_units import ProductUnit
from app.services.batch_allocator import tashkent_today

# SQLite Integer ustuniga (products.min_stock) Decimal bog'lab bo'lmaydi — faqat test muhiti uchun adapter
sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PHARM_MODAL = 'frontend/src/components/PharmacyProductModal.jsx'
PLAIN_MODAL = 'frontend/src/components/ProductAddModal.jsx'
PRODUCTS_JSX = 'frontend/src/pages/admin/Products.jsx'
PENDING = 'tests/branch_audit/i18n_pending/P.2.json'
URL = '/api/products/'
FUTURE = (tashkent_today() + timedelta(days=400)).isoformat()


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


# ───────────────────────── 1. oddiy forma: dorixona qismlari yo'q ─────────────────────────

def test_plain_product_modal_has_no_pharmacy_parts():
    s = _read(PLAIN_MODAL)
    for bad in ('pharma', 'substance_ids', 'substances', "Dori ma'lumotlari", 'PharmaSection', 'PackStructure',
                'packStruct', 'calcPackPrices', 'emptyPack', 'units:', 'initial_lot_number', 'initial_expiry_date',
                'initial_manufacture_date', 'useCompanyFeatures', 'pharmacyOn', 'mxik'):
        assert bad not in s, bad
    # yaroqlilik muddati maydoni oddiy formada avvalgidek ko'rinadi va yuboriladi
    assert 'expiry_date:      form.expiry_date || null' in s
    assert 'Yaroqlilik muddati' in s
    # oddiy formaning boshlang'ich qoldig'i oddiy maydon
    assert 'value={form.initial_stock}' in s


# ───────────────────────── 2. PharmacyProductModal ─────────────────────────

def test_pharmacy_modal_pack_price_calc_and_payload():
    s = _read(PHARM_MODAL)
    # sof funksiya va formula
    assert 'export const calcPackPrices = (bigPrice, bigQty, midQty, round) =>' in s
    block = s[s.index('// PACK-CALC-START'):s.index('// PACK-CALC-END')]
    assert 'up(price / bq)' in block and 'up(mid / mq)' in block
    assert 'Math.ceil(x / step - 1e-9) * step' in block           # price_round qadamiga YUQORIGA
    assert 'Math.ceil(x * 100 - 1e-6) / 100' in block             # round = 0 bo'lsa 2 xonali
    # saqlash: shartnoma maydonlari
    for token in ('payload.units =', 'payload.initial_stock = stockTotal', 'payload.initial_lot_number = pack.lot.trim()',
                  'payload.initial_expiry_date = pack.expiry', 'payload.initial_manufacture_date = pack.mfg',
                  'payload.initial_warehouse_id', "payload.product_type = 'stock'", "payload.unit = 'dona'",
                  'pharma: pharmaToPayload(pharma)', 'requires_marking: !!form.requires_marking',
                  'mxik_code: form.mxik.trim()', 'cost_price: round4((Number(form.cost) || 0) / topRatio)',
                  'sale_price: round4(pr.unit ?? 0)'):
        assert token in s, token
    # yangi mahsulot -> POST, tahrir -> PUT (initial_* faqat yangida)
    assert "api.put(`/products/${product.id}`, payload)" in s and "api.post('/products', payload)" in s
    assert re.search(r"if \(!isEdit\) \{.*?payload\.initial_lot_number", s, re.S)
    # murakkab tuzilma tegilmaydi
    assert 'if (!pack.unsupported) payload.units' in s
    # dori ma'lumotlari va moddalar
    assert "api.get('/pharmacy/substances'" in s and "api.post('/pharmacy/substances'" in s
    assert 'substance_ids' in s
    # server xatosi aniq ko'rsatiladi
    assert 'err.response?.data?.detail' in s and 'detail.map(d => d.msg)' in s


def test_pharmacy_modal_sections_and_details_block():
    s = _read(PHARM_MODAL)
    for n in ('s1', 's2', 's3'):
        assert f"tf('pharmacyModal.{n}'" in s
    # "Batafsil" bloki sukut bo'yicha yopiq
    assert "const [showMore, setShowMore] = useState(false)" in s
    assert "tf('pharmacyModal.details', 'Batafsil')" in s
    assert '{showMore && (' in s
    # ATX izohi va namuna
    assert "masalan N02BE01" in s and "JSST xalqaro tasnif kodi, yo'riqnomada yoziladi" in s
    # MXIK majburiy: xatoda "Batafsil" o'zi ochiladi
    assert "fail(tf('pharmaProduct.mxikRequired'" in s and "true)" in s
    assert 'setShowMore(true)' in s
    # qadoq: o'rta qadoq belgisi, "jami", xulosa
    assert "tf('pharmacyModal.hasMid'" in s and 'packLine(' in s and 'packStockTotal(' in s
    # Section/AutoTag komponent TASHQARISIDA (fokus yo'qolmasligi uchun)
    top = s[:s.index('export default function PharmacyProductModal')]
    assert 'const Section = ' in top and 'const AutoTag = ' in top
    # retsept, markirovka, kategoriya
    assert "pharmaProduct.isRx" in s and 'pharmacyModal.requiresMarking' in s and "api.get('/categories/all')" in s


def _calc(price, big_qty, mid_qty, step):
    """calcPackPrices ning Python nusxasi (JS bilan bir xil qoida)."""
    if not (price > 0) or not (big_qty > 1):
        return None, None
    mq = mid_qty or 0

    def up(x):
        return math.ceil(x / step - 1e-9) * step if step > 0 else math.ceil(x * 100 - 1e-6) / 100
    if mq > 1:
        mid = up(price / big_qty)
        return mid, up(mid / mq)
    return None, up(price / big_qty)


def test_price_rule_examples_python_mirror():
    assert _calc(100000, 5, 10, 0) == (20000, 2000)       # tz misoli: 100 000 -> 20 000 -> 2 000
    assert _calc(100000, 50, 0, 0) == (None, 2000)        # o'rta qadoqsiz
    assert _calc(100000, 3, 0, 100) == (None, 33400)      # bo'linmasa yaxlitlash qadamiga yuqoriga
    assert _calc(0, 5, 10, 0) == (None, None)


def test_price_rule_js_function_runs_if_node_available():
    node = shutil.which('node')
    if not node:
        pytest.skip('node topilmadi')
    s = _read(PHARM_MODAL)
    block = s[s.index('// PACK-CALC-START'):s.index('// PACK-CALC-END')].replace('export const', 'const')
    code = block + "\nconsole.log(JSON.stringify([calcPackPrices(100000,5,10,0), calcPackPrices(100000,50,0,0), calcPackPrices(100000,3,0,100)]));"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'calc.js')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(code)
        out = subprocess.run([node, p], capture_output=True, text=True, timeout=30).stdout.strip()
    assert json.loads(out) == [{'mid': 20000, 'unit': 2000}, {'mid': None, 'unit': 2000}, {'mid': None, 'unit': 33400}]


# ───────────────────────── 3. Products.jsx ─────────────────────────

def test_products_page_two_buttons_in_pharmacy_mode_and_single_in_plain():
    s = _read(PRODUCTS_JSX)
    assert "import PharmacyProductModal, {" in s and "components/PharmacyProductModal'" in s
    assert "components/ProductAddModal'" not in s
    # dorixona rejimida ikki tugma, oddiy korxonada avvalgi bitta tugma
    m = re.search(r"\{pharmacyOn && activeTab === 'products' \? \((.*?)\) : \(\s*<button(.*?)</button>\s*\)\}", s, re.S)
    assert m, 'tugmalar bloki topilmadi'
    pharm_btns, plain_btn = m.group(1), m.group(2)
    assert pharm_btns.count('<button') == 2
    assert "setPharmModal({ product: null })" in pharm_btns and "tf('pharmacyModal.addDrug'" in pharm_btns
    assert 'onClick={openAdd}' in pharm_btns and "tf('pharmacyModal.addOther'" in pharm_btns
    assert "t('product.addProduct')" in plain_btn and 'openAddCat' in plain_btn and 'openAddBl' in plain_btn
    assert plain_btn.count('<svg') == 1
    # oyna faqat dorixona rejimida ochiladi
    assert re.search(r"\{pharmacyOn && pharmModal && \(\s*<PharmacyProductModal", s)
    # tahrirlash: pharma bor mahsulot -> alohida oyna; qolganlari oddiy forma
    assert 'if (pharmacyOn && full.pharma) { setSelected(null); setPharmModal({ product: full }); return; }' in s
    # oddiy formada dorixona qismlari qolmagan
    for bad in ('PharmaSection', 'PackStructureSection', 'PackStockFields', 'pharmaForm', 'setPharmaForm', 'packForm',
                'changePack', 'payload.pharma', 'validatePack', 'packRestore'):
        assert bad not in s, bad
    # MXIK: dorixonada "Boshqa mahsulot" ham server talabi bo'yicha majburiy
    assert 'required={pharmacyOn}' in s and 'pharmacyOn && !(mxikCode ||' in s


def test_products_page_list_pack_summary_and_bulk_columns():
    s = _read(PRODUCTS_JSX)
    assert 'pharmacyOn && Array.isArray(p.units) && p.units.length > 0' in s and 'packSummary(p.units, p.unit)' in s
    # "Ko'p mahsulot qo'shish": dorixonada qo'shimcha ustunlar
    bulk = s[s.index('P.2: qadoq tuzilmasi va qoldiq seriyasi (faqat dorixona rejimida)'):]
    bulk = bulk[:bulk.index('})()}')]
    for token in ('pk_price', 'pk_big_qty', 'pk_mid_qty', 'pk_stock_big', 'pk_lot', 'pk_expiry'):
        assert token in bulk, token
    assert s.count('{pharmacyOn && (() => {') >= 1
    # saqlash: units + seriya/muddat faqat dorixonada, qoldiq quti sonidan donaga aylantiriladi
    assert "...(pharmacyOn && rowUnitPrice != null ? { units: packToUnits(" in s
    assert "initial_lot_number: row.pk_lot.trim(), initial_expiry_date: row.pk_expiry" in s
    assert 'Number(nr.pk_stock_big) * L.topRatio' in s


def test_jsx_syntax_ok_if_checker_available():
    checker = os.environ.get('JSXCHECK') or r'C:\Users\ANUBIS\AppData\Local\Temp\claude\c--Users-ANUBIS-Desktop-e-code\b1bc2b5a-acdd-438e-85e8-7f67984241d9\scratchpad\audit-exec\jsxcheck.cmd'
    if not os.path.exists(checker):
        pytest.skip('jsxcheck topilmadi')
    files = [os.path.join(ROOT, f) for f in (PHARM_MODAL, PLAIN_MODAL, PRODUCTS_JSX)]
    r = subprocess.run([checker, *files], capture_output=True, text=True, shell=True, timeout=120)
    assert r.returncode == 0 and r.stdout.count('OK:') == 3, r.stdout + r.stderr


# ───────────────────────── 4. i18n ─────────────────────────

def test_i18n_pending_complete_consistent_and_not_duplicated():
    with open(os.path.join(ROOT, PENDING), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    assert all(v.strip() for lang in data.values() for v in lang.values())
    src = _read(PHARM_MODAL) + _read(PRODUCTS_JSX)
    used = set(re.findall(r"(?:tf|packName)\(\s*(?:tf,\s*)?'((?:packStruct|pharmacyModal)\.[A-Za-z0-9_.]+)'", src))
    assert used, 'ishlatilgan kalitlar topilmadi'
    assert used <= set(data['uz']), sorted(used - set(data['uz']))
    # {name}/{inner} o'rinbosarlari uch tilda ham saqlangan
    for k, v in data['uz'].items():
        for ph in re.findall(r'\{\w+\}', v):
            assert ph in data['ru'][k] and ph in data['en'][k], k
    # birlashtirilgandan keyin: har kalit umumiy lug'atda aynan bir marta (takror yo'q)
    for lang in ('uz', 'ru', 'en'):
        txt = _read(f'frontend/src/i18n/{lang}.js')
        for k in data[lang]:
            n = len(re.findall(r"^\s*['\"]" + re.escape(k) + r"['\"]\s*:", txt, re.M))
            assert n == 1, f'{k} {lang}.js da {n} marta'


# ───────────────────────── 5. API shartnomasi ─────────────────────────

def _pharmacy_on(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code='pharmacy', is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _modal_payload(barcode='4780000000001', with_stock=True):
    """PharmacyProductModal.handleSave yuboradigan payload: 100 000 / 5 blister / 10 dona."""
    p = {
        'name': 'Parasetamol 500 mg', 'barcode': barcode, 'sku': 'SKU-P2TEST', 'unit': 'dona', 'product_type': 'stock',
        'cost_price': 1000, 'sale_price': 2000, 'mxik_code': '30049099001000000', 'requires_marking': False,
        'category_id': None,
        'pharma': {'dosage_form': 'tablet', 'strength': '500 mg', 'is_rx': False, 'control_class': 'none',
                   'substance_ids': [], 'atc_code': 'N02BE01'},
        'units': [
            {'name': 'blister', 'ratio': 10, 'sale_price': 20000, 'barcode': None},
            {'name': 'quti', 'ratio': 50, 'sale_price': 100000, 'barcode': None},
        ],
    }
    if with_stock:
        p.update({'initial_stock': 130, 'initial_lot_number': 'LOT2026A', 'initial_expiry_date': FUTURE,
                  'initial_manufacture_date': '2025-12-01'})
    return p


def test_modal_payload_saves_units_and_lot_in_pharmacy(client, db, mk):
    c, _, _, u = mk.tenant()
    _pharmacy_on(db, c)
    cl = client.login(u)
    r = cl.post(URL, json=_modal_payload())
    assert r.status_code == 201, r.text
    out = r.json()
    assert [(x['name'], x['ratio'], x['sale_price']) for x in out['units']] == [('blister', 10, 20000.0), ('quti', 50, 100000.0)]
    batch = db.query(Batch).filter(Batch.product_id == out['id']).one()
    assert batch.lot_number == 'LOT2026A' and str(batch.expiry_date)[:10] == FUTURE
    # tahrir (PUT): oyna initial_* yubormaydi, units to'liq almashtiriladi
    put = {'name': 'Parasetamol 500 mg', 'sale_price': 2000, 'units': [{'name': 'quti', 'ratio': 20, 'sale_price': 40000, 'barcode': None}]}
    r2 = cl.put(f"{URL}{out['id']}", json=put)
    assert r2.status_code == 200, r2.text
    assert [(x['name'], x['ratio']) for x in r2.json()['units']] == [('quti', 20)]


def test_modal_payload_requires_lot_and_expiry_with_stock(client, db, mk):
    c, _, _, u = mk.tenant()
    _pharmacy_on(db, c)
    bad = _modal_payload()
    bad.pop('initial_lot_number')
    r = client.login(u).post(URL, json=bad)
    assert r.status_code == 400, r.text


def test_plain_company_ignores_units_regression(client, db, mk):
    c, _, _, u = mk.tenant()          # dorixona yoqilmagan
    cl = client.login(u)
    body = _modal_payload(with_stock=False)
    body.pop('pharma')
    r = cl.post(URL, json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out['units'] == [] and out['pharma'] is None
    assert db.query(ProductUnit).filter(ProductUnit.product_id == out['id']).count() == 0


def test_two_company_isolation(client, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, _, _, ub = mk.tenant()
    _pharmacy_on(db, ca)
    _pharmacy_on(db, cb)
    pid = client.login(ua).post(URL, json=_modal_payload()).json()['id']
    # o'z resursi ishlaydi
    own = client.login(ua).get(f'{URL}{pid}')
    assert own.status_code == 200 and len(own.json()['units']) == 2
    # boshqa korxona foydalanuvchisi ko'ra/o'zgartira olmaydi
    assert client.login(ub).get(f'{URL}{pid}').status_code in (403, 404)
    assert client.login(ub).put(f'{URL}{pid}', json={'units': []}).status_code in (403, 404)
    assert len(client.login(ua).get(f'{URL}{pid}').json()['units']) == 2
