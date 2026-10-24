"""D2.2 — Mahsulot formasi va Excel import (dori maydonlari).

Qamrov:
 1. Excel import (POST /products/bulk-import), dorixona korxonasi: dori ustunlari (modda — vergul bilan bir nechta,
    doza, shakl, qadoqdagi soni, ishlab chiqaruvchi, mamlakat, ro'yxat raqami, retseptli, nazorat toifasi) saqlanadi;
    modda umumiy ro'yxatdan (uz/lotin nomi bo'yicha) topiladi, topilmasa korxona yozuvi sifatida yaratiladi.
 2. Yangilash (allow_update): bo'sh katak o'zgartirmaydi, "Modda" to'ldirilsa ro'yxat almashadi.
 3. Xatolar qator raqami bilan; xato qator mahsulot ham, modda ham yaratmaydi; qolgan qatorlar saqlanadi.
 4. Oddiy korxona (regressiya): dori ustunlari e'tiborsiz, xato bermaydi, dori yozuvi yaratilmaydi.
 5. Ikki korxona izolyatsiyasi: begona korxona moddasi/mahsuloti ishlatilmaydi.
 6. Frontend fayl-matn tekshiruvlari: forma bo'limi, yagona "Yaroqlilik muddati" yashirinishi, filtrlar/ustunlar,
    import ustunlari va shablon, i18n (pending/D2.2.json) kalitlari.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D2_2.py -q -p no:cacheprovider
"""
import json
import os
import py_compile
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.billing import CompanyPackage
from app.models.product import Product
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance

# SQLite Integer ustuniga (products.min_stock) Decimal bog'lab bo'lmaydi — faqat test muhiti uchun adapter
sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))

IMPORT_URL = '/api/products/bulk-import'
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _pharmacy_on(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _substance(db, name, company=None, lat=None, ru=None):
    s = PharmaSubstance(company_id=company.id if company else None, name_uz=name, name_lat=lat, name_ru=ru)
    db.add(s)
    db.flush()
    return s


def _pharma_row(name, barcode, **kw):
    row = {
        'Nomi': name, 'Barkod': barcode, 'Tan narxi': 1000, 'Chakana narxi': 1500,
        'Modda': 'Paratsetamol', 'Doza': '500 mg', 'Shakl': 'tablet', 'Qadoqdagi soni': 20,
        'Ishlab chiqaruvchi': 'Nika Pharm', 'Mamlakat': "O'zbekiston", "Ro'yxat raqami": 'DV/M 01234/01/24',
        'Retseptli': 'ha', 'Nazorat toifasi': 'potent',
    }
    row.update(kw)
    return row


def _product(db, company, name):
    return db.query(Product).filter(Product.company_id == company.id, Product.name == name).one()


def _pharma_of(db, product):
    return db.query(ProductPharma).filter(ProductPharma.product_id == product.id).first()


def _subs_of(db, product):
    return sorted(
        n for (n,) in db.query(PharmaSubstance.name_uz)
        .join(ProductSubstance, ProductSubstance.substance_id == PharmaSubstance.id)
        .filter(ProductSubstance.product_id == product.id).all()
    )


# ---------------------------------------------------------------- dorixona: import (yaratish)

def test_pharmacy_import_creates_pharma_block_with_substances(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    common = _substance(db, 'Paratsetamol', lat='Paracetamolum', ru='Парацетамол')   # umumiy
    rows = [_pharma_row('Panadol', '4780000010011', Modda='paratsetamol, Kofein ; paracetamolum')]
    r = client.login(admin).post(IMPORT_URL, json=rows)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['created'] == 1 and body['errors'] == [], body

    p = _product(db, c, 'Panadol')
    ph = _pharma_of(db, p)
    assert ph is not None and ph.company_id == c.id
    assert ph.dosage_form == 'tablet' and ph.strength == '500 mg' and ph.pack_qty == 20
    assert ph.manufacturer == 'Nika Pharm' and ph.country == "O'zbekiston" and ph.reg_number == 'DV/M 01234/01/24'
    assert ph.is_rx is True and ph.control_class == 'potent'
    # "paratsetamol" va "paracetamolum" bitta umumiy moddaga (takrorsiz); "Kofein" — yangi korxona moddasi
    assert _subs_of(db, p) == ['Kofein', 'Paratsetamol']
    new = db.query(PharmaSubstance).filter(PharmaSubstance.name_uz == 'Kofein').one()
    assert new.company_id == c.id
    assert db.query(PharmaSubstance).filter(PharmaSubstance.name_uz == 'Paratsetamol').count() == 1   # umumiy qayta yaratilmadi
    assert common.company_id is None


def test_pharmacy_import_accepts_aliases_and_reuses_new_substance(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    rows = [
        _pharma_row('Dori A', '4780000010028', Modda='Yangi modda', Shakl='Tabletka', Retseptli="yo'q",
                    **{'Nazorat toifasi': 'Giyohvand'}),
        _pharma_row('Dori B', '4780000010035', Modda='YANGI MODDA', Shakl='kapsula', Retseptli='Yes',
                    **{'Nazorat toifasi': 'yo\'q'}),
    ]
    r = client.login(admin).post(IMPORT_URL, json=rows)
    assert r.status_code == 200 and r.json()['created'] == 2 and r.json()['errors'] == [], r.text
    a, b = _product(db, c, 'Dori A'), _product(db, c, 'Dori B')
    assert (_pharma_of(db, a).dosage_form, _pharma_of(db, a).is_rx, _pharma_of(db, a).control_class) == ('tablet', False, 'narcotic')
    assert (_pharma_of(db, b).dosage_form, _pharma_of(db, b).is_rx, _pharma_of(db, b).control_class) == ('capsule', True, 'none')
    # ikkala qator bitta korxona moddasini ishlatadi (ikkinchi marta yaratilmaydi)
    assert db.query(PharmaSubstance).filter(PharmaSubstance.company_id == c.id).count() == 1
    assert _subs_of(db, a) == _subs_of(db, b) == ['Yangi modda']


def test_pharmacy_import_row_without_pharma_columns_creates_no_pharma_block(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    r = client.login(admin).post(IMPORT_URL, json=[{'Nomi': 'Oddiy tovar', 'Barkod': '4780000010042', 'Chakana narxi': 500}])
    assert r.status_code == 200 and r.json()['created'] == 1 and r.json()['errors'] == [], r.text
    assert _pharma_of(db, _product(db, c, 'Oddiy tovar')) is None


# ---------------------------------------------------------------- dorixona: import (yangilash)

def test_pharmacy_import_update_blank_cells_keep_values_and_substances_replace(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    cl = client.login(admin)
    assert cl.post(IMPORT_URL, json=[_pharma_row('Aspirin', '4780000010059', Modda='Atsetilsalitsil kislota')]).json()['created'] == 1
    p = _product(db, c, 'Aspirin')

    # bo'sh katak o'zgartirmaydi; faqat Doza va Retseptli yangilanadi, Modda bo'sh -> ro'yxat saqlanadi
    row = {'Nomi': 'Aspirin', 'Doza': '100 mg', 'Retseptli': "yo'q", 'Modda': '', 'Shakl': '', 'Mamlakat': ''}
    r = cl.post(f'{IMPORT_URL}?allow_update=true', json=[row])
    assert r.status_code == 200 and r.json()['updated'] == 1 and r.json()['errors'] == [], r.text
    db.expire_all()
    ph = _pharma_of(db, p)
    assert ph.strength == '100 mg' and ph.is_rx is False
    assert ph.dosage_form == 'tablet' and ph.country == "O'zbekiston" and ph.control_class == 'potent'
    assert _subs_of(db, p) == ['Atsetilsalitsil kislota']

    # Modda to'ldirilsa ro'yxat to'liq almashadi
    r = cl.post(f'{IMPORT_URL}?allow_update=true', json=[{'Nomi': 'Aspirin', 'Modda': 'Kofein, Parasetamol'}])
    assert r.status_code == 200 and r.json()['updated'] == 1, r.text
    db.expire_all()
    assert _subs_of(db, p) == ['Kofein', 'Parasetamol']
    assert db.query(ProductPharma).filter(ProductPharma.product_id == p.id).count() == 1   # 1:1


def test_pharmacy_import_update_creates_pharma_block_for_existing_plain_product(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    cl = client.login(admin)
    cl.post(IMPORT_URL, json=[{'Nomi': 'Eski tovar', 'Barkod': '4780000010066'}])
    p = _product(db, c, 'Eski tovar')
    assert _pharma_of(db, p) is None
    r = cl.post(f'{IMPORT_URL}?allow_update=true', json=[{'Nomi': 'Eski tovar', 'Ishlab chiqaruvchi': 'Jurabek Labs'}])
    assert r.status_code == 200 and r.json()['updated'] == 1, r.text
    db.expire_all()
    assert _pharma_of(db, p).manufacturer == 'Jurabek Labs'


# ---------------------------------------------------------------- dorixona: xatolar qator raqami bilan

def test_pharmacy_import_errors_have_row_numbers_and_bad_rows_create_nothing(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    rows = [
        _pharma_row('Yaxshi 1', '4780000010073'),                                               # qator 2
        _pharma_row('Yomon shakl', '4780000010080', Modda='Xato modda 1', Shakl='pill'),        # qator 3
        _pharma_row('Yomon son', '4780000010097', Modda='Xato modda 2', **{'Qadoqdagi soni': '0'}),   # qator 4
        _pharma_row('Yomon rx', '4780000010103', Modda='Xato modda 3', Retseptli='balki'),      # qator 5
        _pharma_row('Yomon nazorat', '4780000010110', Modda='Xato modda 4', **{'Nazorat toifasi': 'qora'}),   # qator 6
        _pharma_row('Yomon son 2', '4780000010127', Modda='Xato modda 5', **{'Qadoqdagi soni': '2.5'}),   # qator 7
        _pharma_row('Yaxshi 2', '4780000010134'),                                               # qator 8
    ]
    r = client.login(admin).post(IMPORT_URL, json=rows)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['created'] == 2, body
    assert sorted(e['row'] for e in body['errors']) == [3, 4, 5, 6, 7]
    by_row = {e['row']: e['error'] for e in body['errors']}
    assert 'shakli' in by_row[3] and 'Qadoqdagi' in by_row[4] and 'Retseptli' in by_row[5] and 'Nazorat' in by_row[6]
    assert db.query(Product).filter(Product.company_id == c.id).count() == 2
    # xato qatorlar uchun moddalar ham yaratilmaydi
    assert db.query(PharmaSubstance).filter(PharmaSubstance.name_uz.like('Xato modda%')).count() == 0


def test_pharmacy_import_update_error_keeps_existing_data(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    cl = client.login(admin)
    cl.post(IMPORT_URL, json=[_pharma_row('Mavjud', '4780000010141')])
    p = _product(db, c, 'Mavjud')
    r = cl.post(f'{IMPORT_URL}?allow_update=true', json=[{'Nomi': 'Mavjud', 'Doza': '999 mg', 'Shakl': 'noma\'lum'}])
    body = r.json()
    assert body['updated'] == 0 and [e['row'] for e in body['errors']] == [2], body
    db.expire_all()
    assert _pharma_of(db, p).strength == '500 mg'


# ---------------------------------------------------------------- oddiy korxona: regressiya

def test_regular_company_import_ignores_pharma_columns(client, db, mk):
    c, _, _, admin = mk.tenant()          # dorixona moduli YOQILMAGAN
    rows = [
        _pharma_row('Oddiy 1', '4780000010158', Shakl='pill'),     # dorixonada xato bo'lardi — bu yerda e'tiborsiz
        {'Nomi': 'Oddiy 2', 'Barkod': '4780000010165', 'Chakana narxi': 700},
    ]
    r = client.login(admin).post(IMPORT_URL, json=rows)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['created'] == 2 and body['errors'] == [], body
    assert db.query(ProductPharma).count() == 0
    assert db.query(ProductSubstance).count() == 0
    assert db.query(PharmaSubstance).filter(PharmaSubstance.company_id == c.id).count() == 0
    p = _product(db, c, 'Oddiy 1')
    assert p.sale_price == Decimal('1500')

    # yangilash ham avvalgidek: dori ustunlari hech narsa yozmaydi
    r = client.login(admin).post(f'{IMPORT_URL}?allow_update=true',
                                 json=[{'Nomi': 'Oddiy 1', 'Chakana narxi': 1800, 'Modda': 'Paratsetamol', 'Doza': '1 g'}])
    assert r.status_code == 200 and r.json()['updated'] == 1 and r.json()['errors'] == [], r.text
    db.expire_all()
    assert _product(db, c, 'Oddiy 1').sale_price == Decimal('1800')
    assert db.query(ProductPharma).count() == 0 and db.query(PharmaSubstance).count() == 0


def test_pharmacy_module_off_after_package_expired_behaves_as_regular(client, db, mk):
    """pharmacy_enabled=True, lekin paket faol emas -> modul o'chiq hisoblanadi (oddiy xatti-harakat)."""
    c, _, _, admin = mk.tenant()
    c.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=now - timedelta(days=60), ends_at=now - timedelta(days=30)))
    db.flush()
    r = client.login(admin).post(IMPORT_URL, json=[_pharma_row('Muddati o\'tgan', '4780000010172', Shakl='pill')])
    assert r.status_code == 200 and r.json()['created'] == 1 and r.json()['errors'] == [], r.text
    assert db.query(ProductPharma).count() == 0


# ---------------------------------------------------------------- ikki korxona izolyatsiyasi

def test_two_companies_import_isolation(client, db, mk):
    ca, _, _, admin_a = mk.tenant()
    cb, _, _, admin_b = mk.tenant()
    _pharmacy_on(db, ca)
    _pharmacy_on(db, cb)
    sub_b = _substance(db, 'Faqat B moddasi', company=cb)
    client.login(admin_b).post(IMPORT_URL, json=[_pharma_row('Umumiy nom', '4780000010189', Modda='Faqat B moddasi')])
    pb = _product(db, cb, 'Umumiy nom')
    assert _subs_of(db, pb) == ['Faqat B moddasi']
    pharma_b_before = _pharma_of(db, pb).strength

    # A xuddi shu nom va moddani yuklaydi: B moddasi ishlatilmaydi, A o'zining yozuvini yaratadi
    r = client.login(admin_a).post(f'{IMPORT_URL}?allow_update=true', json=[
        _pharma_row('Umumiy nom', '4780000010196', Modda='Faqat B moddasi', Doza='1 g')])
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 1 and r.json()['updated'] == 0 and r.json()['errors'] == [], r.json()
    pa = _product(db, ca, 'Umumiy nom')
    assert pa.id != pb.id
    own = db.query(PharmaSubstance).filter(PharmaSubstance.company_id == ca.id, PharmaSubstance.name_uz == 'Faqat B moddasi').one()
    assert own.id != sub_b.id
    link = db.query(ProductSubstance).filter(ProductSubstance.product_id == pa.id).one()
    assert link.substance_id == own.id
    # B ning mahsuloti va moddasi o'zgarmagan
    db.expire_all()
    assert _pharma_of(db, pb).strength == pharma_b_before
    assert db.query(ProductSubstance).filter(ProductSubstance.product_id == pb.id).one().substance_id == sub_b.id


# ---------------------------------------------------------------- frontend: fayl-matn tekshiruvlari

MODAL = 'frontend/src/components/PharmacyProductModal.jsx'   # P.2: dori maydonlari alohida oynaga ko'chirildi
PLAIN_MODAL = 'frontend/src/components/ProductAddModal.jsx'
PRODUCTS_JSX = 'frontend/src/pages/admin/Products.jsx'


def test_import_module_compiles():
    py_compile.compile(os.path.join(ROOT, 'app/routers/product_import.py'), doraise=True)


def test_pharmacy_modal_has_pharma_fields_and_plain_modal_keeps_expiry():
    s = _read(MODAL)
    # P.2: dori maydonlari alohida PharmacyProductModal oynasida (faqat dorixona rejimida ochiladi)
    assert "import useCompanyFeatures from '../hooks/useCompanyFeatures'" in s
    assert "api.get('/pharmacy/substances'" in s and "api.post('/pharmacy/substances'" in s
    for field in ('dosage_form', 'strength', 'pack_qty', 'manufacturer', 'country', 'reg_number',
                  'reg_valid_until', 'atc_code', 'storage', 'is_rx', 'control_class', 'max_retail_price', 'substance_ids'):
        assert field in s, field
    # MXIK majburiy va yuboriladi; pharma bloki yuboriladi
    assert '!form.mxik.trim()' in s and 'mxik_code: form.mxik.trim()' in s
    assert 'pharma: pharmaToPayload(pharma)' in s
    # oddiy forma: dori maydonlari yo'q, yagona "Yaroqlilik muddati" avvalgidek ko'rinadi va yuboriladi
    p = _read(PLAIN_MODAL)
    for bad in ('pharma', 'substance', 'PharmaSection', 'useCompanyFeatures'):
        assert bad not in p, bad
    assert 'expiry_date:      form.expiry_date || null' in p
    assert 'Yaroqlilik muddati' in p


def test_products_page_edit_form_filters_columns_and_import():
    s = _read(PRODUCTS_JSX)
    assert "import useCompanyFeatures from '../../hooks/useCompanyFeatures'" in s
    assert 'const pharmacyOn = !!features?.pharmacy' in s
    # P.2: pharma bor mahsulot alohida PharmacyProductModal da tahrirlanadi, oddiy formada pharma yuborilmaydi; MXIK majburiy
    assert 'if (pharmacyOn && full.pharma) { setSelected(null); setPharmModal({ product: full }); return; }' in s
    assert 'payload.pharma' not in s and 'PharmaSection' not in s
    assert 'pharmacyOn && !(mxikCode ||' in s
    assert 'required={pharmacyOn}' in s
    # filtrlar faqat dorixona rejimida so'rovga qo'shiladi
    m = re.search(r"if \(pharmacyOn\) \{(.*?)\n    \}", s, re.S)
    assert m, 'dori filtrlari bloki topilmadi'
    for param in ('substance_id', 'manufacturer', 'is_rx', 'control_class'):
        assert f"params.append('{param}'" in m.group(1), param
    # ro'yxat ustunlari (modda, ishlab chiqaruvchi) faqat dorixona rejimida
    assert "pharmacyOn && <col" in s and 'p.pharma?.substances' in s and 'p.pharma?.manufacturer' in s
    assert "...(pharmacyOn ? [tf('pharmaProduct.colSubstance'" in s


def test_import_columns_and_template_in_frontend_match_backend():
    from app.routers.product_import import FIELD_MAP, LOT_COLUMNS, PACK_COLUMNS, PHARMA_COLUMNS
    s = _read(PRODUCTS_JSX)
    m = re.search(r"\.\.\.\(pharmacyOn \? \[(.*?)\] : \[\]\),\s*\{ key: '__SKIP__'", s, re.S)
    assert m, 'IMPORT_FIELDS dori ustunlari topilmadi'
    keys = re.findall(r"key: (?:'([^']*)'|\"([^\"]*)\")", m.group(1))
    keys = [a or b for a, b in keys]
    # P.1/P.2: dori ustunlariga qadoq tuzilmasi ustunlari (PACK_COLUMNS, LOT_COLUMNS) ham qo'shilgan
    assert keys == list(PHARMA_COLUMNS) + list(PACK_COLUMNS) + list(LOT_COLUMNS)
    # dori ustunlari mavjud FIELD_MAP kalitlari bilan to'qnashmaydi
    assert not (set(PHARMA_COLUMNS) | set(PACK_COLUMNS) | set(LOT_COLUMNS)) & set(FIELD_MAP)
    # shablon: dorixona rejimida qo'shimcha ustunlar bor, oddiy shablon o'zgarmagan
    t = re.search(r"const downloadTemplate = async \(\) => \{(.*?)saveAs\(", s, re.S)
    assert t
    body = t.group(1)
    assert 'pharmacyOn ? {' in body
    for col in list(PHARMA_COLUMNS) + list(PACK_COLUMNS) + list(LOT_COLUMNS):
        assert (f"'{col}'" in body) or (f'"{col}"' in body), col
    assert "'Nomi': 'Coca-Cola 0.5L'" in body and "'Ombor': ''   // T4.5" in body


def test_i18n_pending_keys_complete_and_consistent():
    path = os.path.join(os.path.dirname(__file__), 'i18n_pending', 'D2.2.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    assert all(v.strip() for lang in data.values() for v in lang.values())
    src = _read(MODAL) + _read(PRODUCTS_JSX)
    used = set(re.findall(r"'(pharmaProduct\.[A-Za-z0-9_.]+)'", src))
    assert used and used <= set(data['uz']), sorted(used - set(data['uz']))
    # dinamik kalitlar (shakl, saqlash, nazorat toifasi) ham to'liq
    for k in ('tablet', 'capsule', 'syrup', 'injection', 'ointment', 'drops', 'powder', 'solution', 'suppository', 'other'):
        assert f'pharmaProduct.form.{k}' in data['uz']
    for k in ('room', 'cold_2_8', 'frozen'):
        assert f'pharmaProduct.storageType.{k}' in data['uz']
    for k in ('none', 'potent', 'psychotropic', 'narcotic', 'precursor'):
        assert f'pharmaProduct.control.{k}' in data['uz']
