"""Dorixona kirimi (PO): qatorda ishlab chiqarilgan sana ham kiritiladi va partiyaga yoziladi.

Avval yangi kirim formasida faqat seriya va yaroqlilik muddati bor edi; server `manufacture_date` ni allaqachon
qabul qilardi (qabul oynasida ham bor). Endi forma uni yuboradi.
"""
import os

from tests.branch_audit.test_D1_3 import _batches, _create_po, _iso, _product, _receive, world   # noqa: F401

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _d(batch_dt):
    return str(batch_dt)[:10]


def test_received_po_writes_manufacture_date_to_batch(client, db, world):
    w = world
    p = _product(db, w['ph'])
    r = _create_po(client, w['padmin'], w['pw'], w['psup'], p, status='received',
                   lot_number='M1', expiry_date=_iso(400), manufacture_date=_iso(-20))
    assert r.status_code == 200, r.text
    (b,) = _batches(db, p)
    assert _d(b.manufacture_date) == _iso(-20)[:10] and _d(b.expiry_date) == _iso(400)[:10]


def test_sent_po_keeps_manufacture_date_until_receive(client, db, world):
    w = world
    p = _product(db, w['ph'])
    po = _create_po(client, w['padmin'], w['pw'], w['psup'], p, lot_number='M2', expiry_date=_iso(300),
                    manufacture_date=_iso(-10)).json()
    assert str(po['items'][0]['manufacture_date'])[:10] == _iso(-10)[:10]
    r = _receive(client, w['padmin'], po['id'], [{'po_item_id': po['items'][0]['id'], 'qty_received': 100,
                                                  'lot_number': 'M2', 'expiry_date': _iso(300)}])
    assert r.status_code == 200, r.text
    assert _d(_batches(db, p)[0].manufacture_date) == _iso(-10)[:10]


def test_purchase_form_sends_manufacture_date():
    with open(os.path.join(ROOT, 'frontend/src/pages/admin/Purchases.jsx'), encoding='utf-8') as f:
        src = f.read()
    assert "manufacture_date: i.manufacture_date || null" in src
    assert "updFn(i, 'manufacture_date', e.target.value)" in src
    for lang in ('uz', 'ru', 'en'):
        with open(os.path.join(ROOT, f'frontend/src/i18n/{lang}.js'), encoding='utf-8') as f:
            assert "'purchase.phMfgBeforeExpiry'" in f.read()
