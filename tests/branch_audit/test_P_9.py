"""P.9 — "Dorini tahrirlash": qoldiqni tahrirlash (faqat dorixonada).

Qamrov:
 1. PUT /api/pharmacy/batches/{id} `quantity`: partiya qoldig'i va ombor qoldig'i farqqa o'zgaradi, ADJUST harakati
    (reference_type=batch_edit), audit; manfiy — 400; qoldiqni faqat admin/direktor/menejer (omborchi sanalarni
    to'g'rilay oladi, qoldiqni emas); boshqa korxona — 404.
 2. Yangi qoldiq: oyna yuboradigan POST /api/inventory/receive (seriyasiz, muddat va ishlab chiqarilgan sana bilan).
 3. Frontend: partiya qoldig'i maydoni, "Qoldiq qo'shish" shakli, saqlash tartibi.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel, StockMovement
from app.models.user import UserRole
from app.services.batch_allocator import tashkent_today

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
MODAL = 'frontend/src/components/PharmacyProductModal.jsx'
PENDING = 'tests/branch_audit/i18n_pending/P.9.json'
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


def _drug(cl, w, barcode='4780000009901', qty=10):
    r = cl.post('/api/products/', json={
        'name': 'Qoldiq dori ' + barcode[-4:], 'barcode': barcode, 'sku': 'SKU-' + barcode[-6:], 'unit': 'dona',
        'product_type': 'stock', 'cost_price': 500, 'sale_price': 1000, 'mxik_code': '03004001001000013',
        'initial_stock': qty, 'initial_warehouse_id': w.id, 'initial_expiry_date': FUTURE,
    })
    assert r.status_code == 201, r.text
    pid = r.json()['id']
    rows = cl.get('/api/pharmacy/batches', params={'product_id': pid}).json()
    return pid, rows[0]['batch_id']


def _level(db, pid, w):
    db.expire_all()
    return D(str(db.query(StockLevel).filter(StockLevel.product_id == pid, StockLevel.warehouse_id == w.id).one().quantity))


def test_batch_quantity_edit_updates_stock_movement_and_audit(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    pid, bid = _drug(cl, w)
    r = cl.put(f'/api/pharmacy/batches/{bid}', json={'quantity': 7})
    assert r.status_code == 200, r.text
    assert float(r.json()['quantity']) == 7 and _level(db, pid, w) == 7
    mv = db.query(StockMovement).filter(StockMovement.reference_type == 'batch_edit',
                                        StockMovement.reference_id == bid).one()
    assert D(str(mv.qty_before)) == 10 and D(str(mv.qty_after)) == 7 and D(str(mv.quantity)) == 3
    log = db.query(AuditLog).filter(AuditLog.action == 'BATCH_EDIT', AuditLog.entity_id == bid).one()
    assert float(log.old_values['quantity']) == 10 and float(log.new_values['quantity']) == 7
    # oshirish: boshlang'ich miqdor ham kattalashadi
    assert cl.put(f'/api/pharmacy/batches/{bid}', json={'quantity': 12}).status_code == 200
    assert _level(db, pid, w) == 12
    b = db.get(Batch, bid)
    assert D(str(b.quantity)) == 12 and D(str(b.initial_quantity)) == 12
    # o'zgarishsiz so'rov — yangi harakat yozilmaydi
    assert cl.put(f'/api/pharmacy/batches/{bid}', json={'quantity': 12}).status_code == 200
    assert db.query(StockMovement).filter(StockMovement.reference_type == 'batch_edit').count() == 2


def test_batch_quantity_validation_roles_and_isolation(client, db, pharm, mk):
    c, b, w, u = pharm
    cl = client.login(u)
    pid, bid = _drug(cl, w, barcode='4780000009902')
    assert cl.put(f'/api/pharmacy/batches/{bid}', json={'quantity': -1}).status_code == 400
    wh_user = mk.user(c, role=UserRole.warehouse, branch=b)
    wcl = client.login(wh_user)
    assert wcl.put(f'/api/pharmacy/batches/{bid}', json={'quantity': 3}).status_code == 403       # qoldiq — yo'q
    assert wcl.put(f'/api/pharmacy/batches/{bid}', json={'lot_number': 'W-1'}).status_code == 200  # sanalar/seriya — bor
    assert _level(db, pid, w) == 10
    c2, _, _, u2 = mk.tenant()
    _pharmacy_on(db, c2)
    assert client.login(u2).put(f'/api/pharmacy/batches/{bid}', json={'quantity': 0}).status_code == 404
    assert _level(db, pid, w) == 10


def test_add_stock_from_edit_window_creates_batch(client, db, pharm):
    c, _, w, u = pharm
    cl = client.login(u)
    pid, _ = _drug(cl, w, barcode='4780000009903')
    # PharmacyProductModal.handleSave (tahrirda "Qoldiq qo'shish") yuboradigan so'rov
    r = cl.post('/api/inventory/receive', json={
        'warehouse_id': w.id, 'note': "Dorini tahrirlash oynasidan qoldiq qo'shildi",
        'items': [{'product_id': pid, 'quantity': 50, 'purchase_price': 500, 'expiry_date': FUTURE,
                   'manufacture_date': '2026-01-10'}],
    })
    assert r.status_code == 200, r.text
    assert _level(db, pid, w) == 60
    new = db.query(Batch).filter(Batch.product_id == pid).order_by(Batch.id.desc()).first()
    assert D(str(new.quantity)) == 50 and new.manufacture_date.date().isoformat() == '2026-01-10'
    assert new.lot_number                                                           # seriyasiz — avtomatik nom


def test_edit_window_stock_ui():
    s = _read(MODAL)
    body = s[s.index('export default function PharmacyProductModal'):]
    assert "quantity: String(Number(b.quantity || 0)),   // P.9" in body
    assert "['lot_number', 'expiry_date', 'manufacture_date', 'quantity']" in body
    assert "if (b.quantity !== b._orig.quantity) body.quantity = Number(b.quantity);" in body
    assert "setB(b.batch_id, { quantity: e.target.value.replace(/[^0-9.]/g, '') })" in body
    # yangi qoldiq: quti soni -> dona, P.15: muddat ixtiyoriy, ombor, qo'lda kirim
    assert "const addQty = isEdit && newStock.open ? (Number(newStock.boxes) || 0) * topRatio : 0;" in body
    assert "await api.post('/inventory/receive', {" in body and 'product_id: product.id, quantity: addQty,' in body
    assert "if (!newStock.expiry) return fail(" not in body
    assert "...(newStock.expiry ? { expiry_date: newStock.expiry } : {})," in body
    assert "tf('drugForm.newStockButton'" in body


def test_i18n_p9():
    with open(os.path.join(ROOT, PENDING), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    used = set(re.findall(r"tf\('(drugForm\.(?:batchQty\w+|newStock\w+))'", _read(MODAL)))
    assert used == set(data['uz']), used ^ set(data['uz'])
    for lang in ('uz', 'ru', 'en'):
        txt = _read(f'frontend/src/i18n/{lang}.js')
        for k in data[lang]:
            assert len(re.findall(r"^\s*['\"]" + re.escape(k) + r"['\"]\s*:", txt, re.M)) == 1, (lang, k)
