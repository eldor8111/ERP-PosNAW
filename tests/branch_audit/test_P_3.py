"""P.3 — "Ko'p mahsulot qo'shish" (dorixona rejimi): avvalgi jadval saqlanadi, yashil qatorga faqat dori shakli va
ishlab chiqarilgan sana qo'shildi (foydalanuvchi talabi: "oldingi holda qolsin, faqat aytganlarimni qo'sh").

Qamrov:
 1. Products.jsx: tugma avvalgidek eski jadvalni ochadi (alohida oyna yo'q); yashil qator faqat pharmacyOn da;
    yangi maydonlar pk_form (dori shakli) va pk_mfg (ishlab chiqarilgan sana); seriya majburiy emas, muddat majburiy.
 2. API: jadval yuboradigan payload — dori shakli `pharma.dosage_form`, ishlab chiqarilgan sana partiyaga yoziladi,
    seriyasiz qoldiq qabul qilinadi; oddiy korxonada bu maydonlar e'tiborsiz.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_P_3.py -q -p no:cacheprovider
"""
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.product_pharma import ProductPharma
from app.services.batch_allocator import tashkent_today

sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PRODUCTS_JSX = 'frontend/src/pages/admin/Products.jsx'
URL = '/api/products/'
FUTURE = (tashkent_today() + timedelta(days=400)).isoformat()
MFG = (tashkent_today() - timedelta(days=60)).isoformat()


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _pharmacy_on(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code='pharmacy', is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _strip(s):
    i = s.index('P.2: qadoq tuzilmasi va qoldiq seriyasi (faqat dorixona rejimida)')
    return s[i:s.index('})()}', i)]


# ───────────────────────── 1. Products.jsx ─────────────────────────

def test_bulk_button_opens_old_table_and_no_separate_window():
    s = _read(PRODUCTS_JSX)
    assert 'PharmacyBulkAddModal' not in s and 'pharmBulkOpen' not in s
    assert not os.path.exists(os.path.join(ROOT, 'frontend/src/components/PharmacyBulkAddModal.jsx'))
    btn = s[s.index('onClick={openBulkAdd}'):]
    assert "{t('product.bulkAddProduct')}" in btn[:btn.index('</button>')]
    assert re.search(r"\{pharmacyOn && \(\(\) => \{\s*const rpk = bulkRowPack\(row\);", s)


def test_strip_has_only_requested_new_fields():
    strip = _strip(_read(PRODUCTS_JSX))
    fields = re.findall(r"updatePkField\(row\._key, '(pk_\w+)'", strip)
    # avvalgi 6 ta + faqat foydalanuvchi so'ragan 2 ta (dori shakli, ishlab chiqarilgan sana)
    assert fields == ['pk_price', 'pk_big_qty', 'pk_mid_qty', 'pk_stock_big', 'pk_lot', 'pk_expiry', 'pk_form', 'pk_mfg']
    assert 'DOSAGE_FORMS.map(' in strip and "tf('pharmaProduct.dosageForm', 'Dori shakli')" in strip
    assert "tf('drugForm.mfgOptional', 'Ishlab chiqarilgan sana (ixtiyoriy)')" in strip
    # seriya majburiy emas (yulduzcha yo'q), yaroqlilik muddati qoldiq bo'lsa majburiy
    assert "{tf('packStruct.lot', 'Seriya raqami')}</label>" in strip
    assert "{tf('packStruct.expiry', 'Yaroqlilik muddati')}{needLot && <span className=\"text-red-500\"> *</span>}" in strip


def test_bulk_save_payload_and_validation():
    s = _read(PRODUCTS_JSX)
    body = s[s.index('const handleBulkAddSave = async () => {'):]
    body = body[:body.index('\n  };')]
    assert "if (!row.pk_expiry) {" in body and "if (row.pk_mfg && row.pk_mfg >= row.pk_expiry) {" in body
    assert "pk_lot || '').trim() || !row.pk_expiry" not in body          # seriya majburiy emas
    assert "...(row.pk_mfg ? { initial_manufacture_date: row.pk_mfg } : {})," in body
    assert "...(pharmacyOn && row.pk_form ? { pharma: { dosage_form: row.pk_form } } : {})," in body


# ───────────────────────── 2. API: jadval payloadi ─────────────────────────

def _row_payload(name, barcode, w, **kw):
    """handleBulkAddSave dorixonada yuboradigan payload: 100 000 / 5 blister / 10 dona, 3 quti qoldiq."""
    p = {
        'name': name, 'barcode': barcode, 'extra_barcodes': [], 'mxik_code': '03004001001000011',
        'cost_price': 1000, 'sale_price': 2000, 'unit': 'dona', 'product_type': 'stock',
        'initial_stock': 150, 'initial_warehouse_id': w.id, 'min_stock': 0, 'status': 'active',
        'units': [{'name': 'blister', 'ratio': 10, 'sale_price': 20000, 'barcode': None},
                  {'name': 'quti', 'ratio': 50, 'sale_price': 100000, 'barcode': None}],
        'initial_expiry_date': FUTURE, 'initial_manufacture_date': MFG,
        'pharma': {'dosage_form': 'capsule'},
    }
    p.update(kw)
    return {k: v for k, v in p.items() if v is not None}


def test_row_saves_dosage_form_and_manufacture_date_without_lot(client, db, mk):
    c, _, w, u = mk.tenant()
    _pharmacy_on(db, c)
    r = client.login(u).post(URL, json=_row_payload('Amoksitsillin 500', '4780000007001', w))
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    assert db.query(ProductPharma.dosage_form).filter(ProductPharma.product_id == pid).scalar() == 'capsule'
    b = db.query(Batch).filter(Batch.product_id == pid).one()
    assert Decimal(str(b.quantity)) == 150 and b.lot_number == f'initial-{pid}'
    assert b.manufacture_date.date().isoformat() == MFG and str(b.expiry_date)[:10] == FUTURE


def test_row_rejects_manufacture_after_expiry(client, db, mk):
    c, _, w, u = mk.tenant()
    _pharmacy_on(db, c)
    r = client.login(u).post(URL, json=_row_payload('Xato sana', '4780000007002', w, initial_manufacture_date=FUTURE))
    assert r.status_code == 400


def test_plain_company_ignores_pharmacy_fields(client, db, mk):
    c, _, w, u = mk.tenant()            # dorixona yoqilmagan
    body = _row_payload('Shampun', '4780000007003', w, mxik_code=None)
    r = client.login(u).post(URL, json=body)
    assert r.status_code == 201, r.text
    assert r.json()['units'] == [] and r.json()['pharma'] is None
    b = db.query(Batch).filter(Batch.product_id == r.json()['id']).one()
    assert b.expiry_date is None and b.manufacture_date is None
