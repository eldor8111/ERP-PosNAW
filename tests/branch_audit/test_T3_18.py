"""T3.18 — To'lov va fiskal integratsiyalar filial/kassa bo'yicha.

Qamrov (qabul mezonlari):
 1. HIPPO_SERVER_ENABLED o'chiq: /hippo/* 404; POST /sales/ + X-Hippo-Factory-Id server fiskallamaydi.
 2. fiscalize_sale natijasi Sale ga yoziladi; PATCH /sales/{id}/fiscal fiscal_factory_id ni saqlaydi, GET da ko'rinadi.
 3. Filial qurilmasi ro'yxatda bo'lsa boshqa filial factory_id si bilan PATCH -> 409; ro'yxat bo'sh korxonada eski xatti-harakat.
 4. Flag yoqilganda admin PUT /hippo/settings -> 403, super_admin -> ruxsat; factory_id registrida bo'lmasa 403.
 5. Faol click terminali (require_reference) bo'lsa reference'siz click to'lovi 400; terminal bo'lmasa o'tadi.
 6. CSV solishtirish: reference mos -> matched; qolganlari only_in_*; filial va sana filtri.
 7. /mine faqat o'z filiali terminal/qurilmalarini qaytaradi.
 + CRUD rol/izolyatsiya (403 / 404 / 409), i18n pending kalitlari, migratsiya <-> model mosligi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_18.py -q -p no:cacheprovider
"""
import io
import itertools
import json
import os
import py_compile
import re
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.config import settings
from app.models.fiscal_device import FiscalDevice
from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Wallet
from app.models.payment_terminal import PaymentTerminal
from app.models.product import Product
from app.models.sale import Sale, SalePayment
from app.models.user import UserRole
from app.routers import hippo as hippo_router
from app.routers import sales as sales_router
from app.services import hippo_fiscalize

_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company, price="1000"):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T318-{n}", barcode=f"B318-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal(price))
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty=100):
    db.add(StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()


def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"),
               company_id=company.id, branch_id=branch.id if branch else None, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _device(db, company, factory_id, branch=None, active=True):
    d = FiscalDevice(company_id=company.id, branch_id=branch.id if branch else None,
                     factory_id=factory_id, label=factory_id, is_active=active)
    db.add(d)
    db.flush()
    return d


def _terminal(db, company, provider, branch=None, require_reference=True, active=True):
    t = PaymentTerminal(company_id=company.id, branch_id=branch.id if branch else None, provider=provider,
                        label=f"{provider}-{next(_seq)}", merchant_id=f"M{next(_seq)}",
                        require_reference=require_reference, is_active=active)
    db.add(t)
    db.flush()
    return t


@pytest.fixture(autouse=True)
def _no_sale_side_effects(monkeypatch):
    """Sotuvdan keyingi fon vazifasi (Telegram xabari) tarmoqqa chiqmasin — bu test uchun muhim emas."""
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(sales_router, 'notify_new_sale', _noop)


@pytest.fixture
def w(db, mk):
    """A korxona: a1 (wh1), a2 (wh2); admin; a1/a2 kassirlari. B korxona: admin + filial."""
    ca, a1, wh1, admin = mk.tenant(UserRole.admin)
    a2 = mk.branch(ca, "Filial A-2")
    wh2 = mk.warehouse(ca, a2, name="Ombor A2")
    cash1 = mk.user(ca, role=UserRole.cashier, branch=a1)
    cash2 = mk.user(ca, role=UserRole.cashier, branch=a2)
    _wallet(db, ca, a1)
    _wallet(db, ca, a2)
    p = _product(db, ca)
    _stock(db, p, wh1)
    _stock(db, p, wh2)
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    _wallet(db, cb, b1)
    return dict(ca=ca, a1=a1, a2=a2, wh1=wh1, wh2=wh2, admin=admin, cash1=cash1, cash2=cash2, p=p,
                cb=cb, b1=b1, whb=whb, admin_b=admin_b)


def _sale_body(w, wh, payments, price=1000):
    total = sum(x['amount'] for x in payments)
    return {'items': [{'product_id': w['p'].id, 'quantity': 1, 'unit_price': price}],
            'payment_type': payments[0]['type'], 'paid_amount': total, 'payments': payments,
            'warehouse_id': wh.id}


def _post_sale(client, user, w, wh, payments, headers=None):
    return client.login(user).post('/api/sales/', json=_sale_body(w, wh, payments), headers=headers or {})


def _any_sale(client, w, key='k318'):
    r = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'cash', 'amount': 1000}], {'Idempotency-Key': key})
    assert r.status_code == 200, r.text
    return r.json()['id']


# ── 1. Hippo server yuzasi flag orqasida ─────────────────────────────────────

def test_hippo_router_404_when_flag_off(client, w, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', False)
    r = client.login(w['admin']).get('/api/hippo/fiscal-modules')
    assert r.status_code == 404
    assert client.login(w['admin']).get('/api/hippo/health').status_code == 404


def test_server_does_not_fiscalize_when_flag_off(client, w, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', False)
    called = []
    monkeypatch.setattr(sales_router, 'fiscalize_sale', lambda *a, **k: called.append(a))
    r = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'cash', 'amount': 1000}],
                   {'X-Hippo-Factory-Id': 'FM-1', 'Idempotency-Key': 'k318-off'})
    assert r.status_code == 200, r.text
    assert called == []


def test_server_fiscalizes_when_flag_on(client, w, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    called = []
    monkeypatch.setattr(sales_router, 'fiscalize_sale', lambda db, sid, fid: called.append((sid, fid)))
    r = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'cash', 'amount': 1000}],
                   {'X-Hippo-Factory-Id': 'FM-1', 'Idempotency-Key': 'k318-on'})
    assert r.status_code == 200, r.text
    assert called == [(r.json()['id'], 'FM-1')]


def test_server_fiscalize_skips_foreign_branch_device_when_flag_on(client, db, w, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    _device(db, w['ca'], 'FM-A2', branch=w['a2'])
    called = []
    monkeypatch.setattr(sales_router, 'fiscalize_sale', lambda db, sid, fid: called.append(fid))
    r = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'cash', 'amount': 1000}],
                   {'X-Hippo-Factory-Id': 'FM-A2', 'Idempotency-Key': 'k318-fb'})
    assert r.status_code == 200, r.text
    assert called == []   # a1 sotuvi a2 qurilmasi bilan fiskallanmaydi


def test_hippo_settings_super_admin_only_and_device_scope(client, db, mk, w, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    monkeypatch.setattr(hippo_router.hippo_service, 'update_settings', lambda data: {'ok': True})
    monkeypatch.setattr(hippo_router.hippo_service, 'get_fiscal_module_info', lambda fid: {'factory_id': fid})
    monkeypatch.setattr(hippo_router.hippo_service, 'get_fiscal_modules',
                        lambda: [{'factory_id': 'FM-A1'}, {'factory_id': 'FM-B1'}])
    # A korxona admini kommunikator sozlamasini o'zgartira olmaydi
    assert client.login(w['admin']).put('/api/hippo/settings', json={'x': 1}).status_code == 403
    sa = mk.user(None, role=UserRole.super_admin)
    assert client.login(sa).put('/api/hippo/settings', json={'x': 1}).status_code == 200

    _device(db, w['ca'], 'FM-A1', branch=w['a1'])
    _device(db, w['cb'], 'FM-B1')
    # Ro'yxatda yo'q / boshqa korxona qurilmasi -> 403
    assert client.login(w['admin']).get('/api/hippo/fiscal-modules/info', params={'factory_id': 'NOPE'}).status_code == 403
    assert client.login(w['admin']).get('/api/hippo/fiscal-modules/info', params={'factory_id': 'FM-B1'}).status_code == 403
    assert client.login(w['admin']).get('/api/hippo/fiscal-modules/info', params={'factory_id': 'FM-A1'}).status_code == 200
    # a2 kassiri a1 qurilmasidan foydalana olmaydi
    assert client.login(w['cash2']).get('/api/hippo/fiscal-modules/info', params={'factory_id': 'FM-A1'}).status_code == 403
    # Ro'yxat faqat o'z korxonasi qurilmalari bilan cheklanadi
    lst = client.login(w['admin']).get('/api/hippo/fiscal-modules').json()
    assert [x['factory_id'] for x in lst] == ['FM-A1']
    # Z-hisobot (body factory_id) ham tekshiriladi
    assert client.login(w['admin']).post('/api/hippo/z-report/close', json={'factory_id': 'FM-B1'}).status_code == 403


def test_hippo_requires_pos_role(client, db, mk, w, monkeypatch):
    monkeypatch.setattr(settings, 'HIPPO_SERVER_ENABLED', True)
    acc = mk.user(w['ca'], role=UserRole.warehouse, branch=w['a1'])
    assert client.login(acc).get('/api/hippo/health').status_code == 403


# ── 2. Natijani Sale ga yozish ───────────────────────────────────────────────

def test_fiscalize_sale_saves_result_to_sale(client, db, w, monkeypatch):
    sid = _any_sale(client, w, 'k318-save')
    monkeypatch.setattr(hippo_fiscalize.hippo_client, 'post', lambda path, payload: {
        'fiscal_sign': 'SIGN123', 'qr_code_url': 'https://ofd.uz/q/1', 'transaction_id': 777, 'receipt_seq': 5})
    res = hippo_fiscalize.fiscalize_sale(db, sid, 'FM-A1')
    assert res['fiscal_sign'] == 'SIGN123'
    sale = db.get(Sale, sid)
    assert sale.fiscal_sign == 'SIGN123' and sale.fiscal_qr_url == 'https://ofd.uz/q/1'
    assert sale.fiscal_transaction_id == '777' and sale.fiscal_receipt_seq == 5
    assert sale.fiscal_factory_id == 'FM-A1' and sale.fiscal_at is not None


def test_fiscalize_sale_failed_result_does_not_write(client, db, w, monkeypatch):
    sid = _any_sale(client, w, 'k318-nosave')
    monkeypatch.setattr(hippo_fiscalize.hippo_client, 'post', lambda path, payload: {'local_id': 3})
    hippo_fiscalize.fiscalize_sale(db, sid, 'FM-A1')
    assert db.get(Sale, sid).fiscal_sign is None


def test_patch_fiscal_saves_factory_and_get_returns_it(client, db, w):
    sid = _any_sale(client, w, 'k318-patch')
    r = client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={
        'fiscal_sign': 'S1', 'fiscal_qr_url': 'https://q/1', 'fiscal_factory_id': 'FM-LOCAL'})
    assert r.status_code == 200, r.text
    d = client.login(w['admin']).get(f'/api/sales/{sid}').json()
    assert d['fiscal_sign'] == 'S1' and d['fiscal_qr_url'] == 'https://q/1' and d['fiscal_factory_id'] == 'FM-LOCAL'


# ── 3. PATCH /fiscal: filial qurilmasi tekshiruvi ────────────────────────────

def test_patch_fiscal_foreign_branch_device_409(client, db, w):
    _device(db, w['ca'], 'FM-A1', branch=w['a1'])
    _device(db, w['ca'], 'FM-A2', branch=w['a2'])
    sid = _any_sale(client, w, 'k318-409')            # wh1 -> a1 filiali
    r = client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={'fiscal_sign': 'S', 'fiscal_factory_id': 'FM-A2'})
    assert r.status_code == 409 and 'biriktirilmagan' in r.json()['detail']
    r = client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={'fiscal_sign': 'S', 'fiscal_factory_id': 'NOT-REGISTERED'})
    assert r.status_code == 409
    ok = client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={'fiscal_sign': 'S', 'fiscal_factory_id': 'FM-A1'})
    assert ok.status_code == 200 and ok.json()['fiscal_factory_id'] == 'FM-A1'


def test_patch_fiscal_company_wide_device_ok_and_inactive_ignored(client, db, w):
    _device(db, w['ca'], 'FM-ALL')                     # butun korxona
    _device(db, w['ca'], 'FM-OLD', branch=w['a1'], active=False)
    sid = _any_sale(client, w, 'k318-wide')
    assert client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={'fiscal_factory_id': 'FM-ALL'}).status_code == 200
    assert client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={'fiscal_factory_id': 'FM-OLD'}).status_code == 409


def test_patch_fiscal_empty_registry_keeps_old_behavior(client, db, w):
    sid = _any_sale(client, w, 'k318-empty')
    r = client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={'fiscal_sign': 'S', 'fiscal_factory_id': 'ANY-ID'})
    assert r.status_code == 200 and r.json()['fiscal_factory_id'] == 'ANY-ID'
    # B korxona registri A korxonaga ta'sir qilmaydi
    _device(db, w['cb'], 'FM-B1')
    r2 = client.login(w['admin']).patch(f'/api/sales/{sid}/fiscal', json={'fiscal_factory_id': 'ANOTHER'})
    assert r2.status_code == 200


# ── Fiskal qurilmalar CRUD ────────────────────────────────────────────────────

def test_fiscal_devices_crud_roles_isolation_and_conflict(client, db, w):
    A = '/api/fiscal-devices'
    assert client.login(w['cash1']).get(A).status_code == 403
    assert client.login(w['cash1']).post(A, json={'factory_id': 'X'}).status_code == 403
    r = client.login(w['admin']).post(A, json={'factory_id': ' FM-1 ', 'branch_id': w['a1'].id, 'label': 'Kassa 1'})
    assert r.status_code == 201, r.text
    dev = r.json()
    assert dev['factory_id'] == 'FM-1' and dev['branch_id'] == w['a1'].id and dev['is_active'] is True
    assert client.login(w['admin']).post(A, json={'factory_id': 'FM-1'}).status_code == 409      # takror
    # Boshqa korxona filiali / kassasi -> 404
    assert client.login(w['admin']).post(A, json={'factory_id': 'FM-2', 'branch_id': w['b1'].id}).status_code == 404
    other_wallet = _wallet(db, w['cb'], w['b1'])
    assert client.login(w['admin']).post(A, json={'factory_id': 'FM-3', 'wallet_id': other_wallet.id}).status_code == 404
    # Boshqa korxona admini bu yozuvni ko'rmaydi/o'zgartirmaydi/o'chirmaydi
    assert client.login(w['admin_b']).put(f"{A}/{dev['id']}", json={'label': 'hack'}).status_code == 404
    assert client.login(w['admin_b']).delete(f"{A}/{dev['id']}").status_code == 404
    assert client.login(w['admin_b']).get(A).json() == []
    # Yangilash (filialni butun korxonaga o'tkazish) va o'chirish
    up = client.login(w['admin']).put(f"{A}/{dev['id']}", json={'branch_id': None, 'label': 'Umumiy'})
    assert up.status_code == 200 and up.json()['branch_id'] is None and up.json()['label'] == 'Umumiy'
    d2 = client.login(w['admin']).post(A, json={'factory_id': 'FM-9'}).json()
    assert client.login(w['admin']).put(f"{A}/{d2['id']}", json={'factory_id': 'FM-1'}).status_code == 409
    assert client.login(w['admin']).delete(f"{A}/{dev['id']}").status_code == 200
    assert [x['factory_id'] for x in client.login(w['admin']).get(A).json()] == ['FM-9']


def test_fiscal_devices_mine_only_own_branch(client, db, w):
    _device(db, w['ca'], 'FM-A1', branch=w['a1'])
    _device(db, w['ca'], 'FM-A2', branch=w['a2'])
    _device(db, w['ca'], 'FM-ALL')
    _device(db, w['ca'], 'FM-OFF', branch=w['a1'], active=False)
    _device(db, w['cb'], 'FM-B1')
    ids1 = sorted(x['factory_id'] for x in client.login(w['cash1']).get('/api/fiscal-devices/mine').json())
    ids2 = sorted(x['factory_id'] for x in client.login(w['cash2']).get('/api/fiscal-devices/mine').json())
    assert ids1 == ['FM-A1', 'FM-ALL']
    assert ids2 == ['FM-A2', 'FM-ALL']


# ── 5. To'lov terminallari va majburiy reference ─────────────────────────────

def test_click_requires_reference_when_terminal_requires(client, db, w):
    _terminal(db, w['ca'], 'click', branch=w['a1'], require_reference=True)
    pay = [{'type': 'click', 'amount': 1000}]
    r = _post_sale(client, w['admin'], w, w['wh1'], pay, {'Idempotency-Key': 'k318-c1'})
    assert r.status_code == 400 and 'Tranzaksiya raqamini kiriting' in r.json()['detail']
    r = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'click', 'amount': 1000, 'reference': '  '}],
                   {'Idempotency-Key': 'k318-c1b'})
    assert r.status_code == 400
    # Eski maydon (paid_click) orqali ham aylanib o'tib bo'lmaydi
    body = _sale_body(w, w['wh1'], pay)
    body.pop('payments')
    body['paid_click'] = 1000
    r = client.login(w['admin']).post('/api/sales/', json=body, headers={'Idempotency-Key': 'k318-c1c'})
    assert r.status_code == 400
    # Reference bilan o'tadi va SalePayment ga yoziladi
    r = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'click', 'amount': 1000, 'reference': 'CLK-777'}],
                   {'Idempotency-Key': 'k318-c2'})
    assert r.status_code == 200, r.text
    sp = db.query(SalePayment).filter(SalePayment.sale_id == r.json()['id']).one()
    assert sp.reference == 'CLK-777' and sp.payment_type == 'click'
    got = client.login(w['admin']).get(f"/api/sales/{r.json()['id']}").json()
    assert got['payments'][0]['reference'] == 'CLK-777'


def test_click_without_terminal_or_other_branch_passes(client, db, w):
    # Terminal faqat a2 da; a1 (terminalsiz filial) oldingidek reference'siz o'tadi
    _terminal(db, w['ca'], 'click', branch=w['a2'], require_reference=True)
    r = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'click', 'amount': 1000}], {'Idempotency-Key': 'k318-n1'})
    assert r.status_code == 200, r.text
    # a2 da esa majburiy
    r2 = _post_sale(client, w['admin'], w, w['wh2'], [{'type': 'click', 'amount': 1000}], {'Idempotency-Key': 'k318-n2'})
    assert r2.status_code == 400
    # Boshqa korxona terminali ta'sir qilmaydi
    _terminal(db, w['cb'], 'payme', require_reference=True)
    r3 = _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'payme', 'amount': 1000}], {'Idempotency-Key': 'k318-n3'})
    assert r3.status_code == 200, r3.text


def test_terminal_require_reference_off_and_inactive(client, db, w):
    _terminal(db, w['ca'], 'click', branch=w['a1'], require_reference=False)
    _terminal(db, w['ca'], 'payme', branch=w['a1'], require_reference=True, active=False)
    assert _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'click', 'amount': 1000}],
                      {'Idempotency-Key': 'k318-o1'}).status_code == 200
    assert _post_sale(client, w['admin'], w, w['wh1'], [{'type': 'payme', 'amount': 1000}],
                      {'Idempotency-Key': 'k318-o2'}).status_code == 200


def test_sale_terminal_id_must_belong_to_company_and_branch(client, db, w):
    own = _terminal(db, w['ca'], 'click', branch=w['a1'])
    other_branch = _terminal(db, w['ca'], 'click', branch=w['a2'])
    foreign = _terminal(db, w['cb'], 'click')
    wide = _terminal(db, w['ca'], 'click', branch=None)
    for i, t in enumerate((other_branch, foreign)):
        r = _post_sale(client, w['admin'], w, w['wh1'],
                       [{'type': 'click', 'amount': 1000, 'reference': 'R1', 'terminal_id': t.id}],
                       {'Idempotency-Key': f'k318-t{i}'})
        assert r.status_code == 404, r.text
    r = _post_sale(client, w['admin'], w, w['wh1'],
                   [{'type': 'click', 'amount': 1000, 'reference': 'R2', 'terminal_id': own.id}],
                   {'Idempotency-Key': 'k318-t5'})
    assert r.status_code == 200, r.text
    sp = db.query(SalePayment).filter(SalePayment.sale_id == r.json()['id']).one()
    assert sp.terminal_id == own.id and sp.reference == 'R2'
    r = _post_sale(client, w['admin'], w, w['wh1'],
                   [{'type': 'click', 'amount': 1000, 'reference': 'R3', 'terminal_id': wide.id}],
                   {'Idempotency-Key': 'k318-t6'})
    assert r.status_code == 200
    # Provayder mos kelmasa (payme to'lovi click terminali bilan) -> 400
    r = _post_sale(client, w['admin'], w, w['wh1'],
                   [{'type': 'payme', 'amount': 1000, 'reference': 'R4', 'terminal_id': own.id}],
                   {'Idempotency-Key': 'k318-t7'})
    assert r.status_code == 400


def test_mixed_payments_references_attached_to_right_rows(client, db, w):
    _terminal(db, w['ca'], 'click', branch=w['a1'])
    r = _post_sale(client, w['admin'], w, w['wh1'], [
        {'type': 'cash', 'amount': 400},
        {'type': 'click', 'amount': 600, 'reference': 'CLK-MIX'},
    ])
    assert r.status_code == 200, r.text
    rows = {p.payment_type: p for p in db.query(SalePayment).filter(SalePayment.sale_id == r.json()['id']).all()}
    assert rows['click'].reference == 'CLK-MIX' and rows['cash'].reference is None


def test_payment_terminals_crud_roles_isolation_validation(client, db, w):
    A = '/api/payment-terminals'
    assert client.login(w['cash1']).get(A).status_code == 403
    assert client.login(w['cash1']).post(A, json={'provider': 'click'}).status_code == 403
    r = client.login(w['admin']).post(A, json={'provider': 'click', 'branch_id': w['a1'].id, 'merchant_id': 'M-1'})
    assert r.status_code == 201, r.text
    t = r.json()
    assert t['require_reference'] is True and t['is_active'] is True and 'secret' not in json.dumps(t)
    assert client.login(w['admin']).post(A, json={'provider': 'bitcoin'}).status_code == 422
    assert client.login(w['admin']).post(A, json={'provider': 'click', 'branch_id': w['b1'].id}).status_code == 404
    assert client.login(w['admin_b']).put(f"{A}/{t['id']}", json={'label': 'x'}).status_code == 404
    assert client.login(w['admin_b']).delete(f"{A}/{t['id']}").status_code == 404
    assert client.login(w['admin_b']).get(A).json() == []
    up = client.login(w['admin']).put(f"{A}/{t['id']}", json={'require_reference': False})
    assert up.status_code == 200 and up.json()['require_reference'] is False
    # Terminal o'chirilsa SalePayment.reference saqlanib qoladi, terminal_id NULL bo'ladi
    t2 = client.login(w['admin']).post(A, json={'provider': 'payme', 'branch_id': w['a1'].id}).json()
    rs = _post_sale(client, w['admin'], w, w['wh1'],
                    [{'type': 'payme', 'amount': 1000, 'reference': 'PM-1', 'terminal_id': t2['id']}],
                    {'Idempotency-Key': 'k318-del'})
    assert rs.status_code == 200, rs.text
    assert client.login(w['admin']).delete(f"{A}/{t2['id']}").status_code == 200
    db.expire_all()
    sp = db.query(SalePayment).filter(SalePayment.sale_id == rs.json()['id']).one()
    assert sp.reference == 'PM-1' and sp.terminal_id is None


def test_payment_terminals_mine_only_own_branch(client, db, w):
    t1 = _terminal(db, w['ca'], 'click', branch=w['a1'])
    t2 = _terminal(db, w['ca'], 'click', branch=w['a2'])
    tw = _terminal(db, w['ca'], 'payme')
    _terminal(db, w['ca'], 'uzum', branch=w['a1'], active=False)
    _terminal(db, w['cb'], 'click')
    ids1 = sorted(x['id'] for x in client.login(w['cash1']).get('/api/payment-terminals/mine').json())
    ids2 = sorted(x['id'] for x in client.login(w['cash2']).get('/api/payment-terminals/mine').json())
    assert ids1 == sorted([t1.id, tw.id])
    assert ids2 == sorted([t2.id, tw.id])


# ── 6. Provayder ko'chirmasi (CSV) bilan solishtirish ────────────────────────

def _csv_post(client, user, text, **params):
    files = {'file': ('stmt.csv', io.BytesIO(text.encode('utf-8')), 'text/csv')}
    return client.login(user).post('/api/finance/reconciliation/import', params=params, files=files)


def _pay_sale(db, w, wh, branch, ptype, amount, reference, created_at, number):
    s = Sale(number=number, cashier_id=w['admin'].id, total_amount=Decimal(amount), paid_amount=Decimal(amount),
             payment_type=ptype, company_id=w['ca'].id, warehouse_id=wh.id, branch_id=branch.id,
             created_at=created_at)
    db.add(s)
    db.flush()
    db.add(SalePayment(sale_id=s.id, payment_type=ptype, amount=Decimal(amount), reference=reference))
    db.flush()
    return s


def test_reconciliation_matches_by_reference_and_time(client, db, w):
    # Ko'chirma vaqti mahalliy (UTC+5): bazadagi UTC 06:00 -> ko'chirmada 11:00
    base = datetime(2026, 9, 10, 6, 0, 0)
    s1 = _pay_sale(db, w, w['wh1'], w['a1'], 'click', 1000, 'CLK-1', base, 'S318-1')
    s2 = _pay_sale(db, w, w['wh1'], w['a1'], 'click', 2000, None, base + timedelta(minutes=10), 'S318-2')        # vaqt+summa bo'yicha
    s3 = _pay_sale(db, w, w['wh1'], w['a1'], 'click', 3000, 'CLK-3', base + timedelta(minutes=20), 'S318-3')     # faqat tizimda
    _pay_sale(db, w, w['wh1'], w['a1'], 'payme', 1000, 'PM-1', base, 'S318-4')                                   # boshqa provayder
    s5 = _pay_sale(db, w, w['wh2'], w['a2'], 'click', 5000, 'CLK-5', base + timedelta(minutes=30), 'S318-5')     # boshqa filial
    csv_text = (
        'date,amount,reference\n'
        '2026-09-10 11:00:00,1000,CLK-1\n'
        '2026-09-10 11:12:00,2000,CLK-X\n'       # reference mos emas, summa+vaqt (2 daq) mos
        '2026-09-10 11:40:00,9999,CLK-9\n'       # faqat provayderda
        '2026-09-10 11:30:00,5000,CLK-5\n'
    )
    r = _csv_post(client, w['admin'], csv_text, provider='click')
    assert r.status_code == 200, r.text
    d = r.json()
    by_type = {m['system']['sale_number']: m['match_type'] for m in d['matched']}
    assert by_type == {'S318-1': 'reference', 'S318-2': 'amount_time', 'S318-5': 'reference'}
    assert [x['sale_number'] for x in d['only_in_system']] == ['S318-3']
    assert [x['reference'] for x in d['only_in_provider']] == ['CLK-9']
    t = d['totals']
    assert t['matched_count'] == 3 and t['only_in_system_count'] == 1 and t['only_in_provider_count'] == 1
    assert t['only_in_provider_amount'] == 9999.0 and t['only_in_system_amount'] == 3000.0

    # Filial filtri: faqat a2
    r2 = _csv_post(client, w['admin'], csv_text, provider='click', branch_id=w['a2'].id)
    d2 = r2.json()
    assert [m['system']['sale_number'] for m in d2['matched']] == ['S318-5']
    assert d2['only_in_system'] == []
    assert len(d2['only_in_provider']) == 3

    # Sana filtri: boshqa kun -> hammasi bo'sh
    r3 = _csv_post(client, w['admin'], csv_text, provider='click', date_from='2026-09-11', date_to='2026-09-12')
    assert r3.status_code == 200
    assert r3.json()['totals']['provider_rows'] == 0 and r3.json()['matched'] == []


def test_reconciliation_amount_mismatch_not_matched_and_each_payment_once(client, db, w):
    base = datetime(2026, 9, 10, 6, 0, 0)
    _pay_sale(db, w, w['wh1'], w['a1'], 'click', 1000, 'DUP', base, 'S318-D1')
    csv_text = ('date,amount,reference\n2026-09-10 11:00,1000,DUP\n2026-09-10 11:01,1000,DUP\n'
                '2026-09-10 11:00,1500,DUP\n')
    d = _csv_post(client, w['admin'], csv_text, provider='click').json()
    # Bitta ichki to'lov faqat bitta ko'chirma qatoriga mos keladi
    assert d['totals']['matched_count'] == 1 and d['totals']['only_in_provider_count'] == 2


def test_reconciliation_csv_validation_and_roles(client, db, w):
    r = _csv_post(client, w['admin'], 'date,amount\n2026-09-10,100\n', provider='click')
    assert r.status_code == 400 and 'reference' in r.json()['detail']
    assert _csv_post(client, w['admin'], 'date,amount,reference\nNOT-A-DATE,100,R1\n', provider='click').status_code == 400
    assert _csv_post(client, w['admin'], 'date,amount,reference\n2026-09-10,abc,R1\n', provider='click').status_code == 400
    assert _csv_post(client, w['admin'], '', provider='click').status_code == 400
    # Nuqtali vergul va bo'sh referens ruxsat
    ok = _csv_post(client, w['admin'], 'date;amount;reference\n10.09.2026 11:00;1 000,50;\n', provider='click')
    assert ok.status_code == 200 and ok.json()['only_in_provider'][0]['amount'] == 1000.5
    # Kassir kira olmaydi; begona filial -> 404
    assert _csv_post(client, w['cash1'], 'date,amount,reference\n', provider='click').status_code == 403
    assert _csv_post(client, w['admin'], 'date,amount,reference\n', provider='click', branch_id=w['b1'].id).status_code == 404
    assert _csv_post(client, w['admin'], 'date,amount,reference\n', provider='bitcoin').status_code == 422


def test_reconciliation_company_isolation(client, db, w, mk):
    base = datetime(2026, 9, 10, 6, 0, 0)
    _pay_sale(db, w, w['wh1'], w['a1'], 'click', 1000, 'CLK-1', base, 'S318-I1')
    csv_text = 'date,amount,reference\n2026-09-10 11:00,1000,CLK-1\n'
    d = _csv_post(client, w['admin_b'], csv_text, provider='click').json()
    assert d['totals']['matched_count'] == 0 and d['totals']['system_payments'] == 0
    assert d['totals']['only_in_provider_count'] == 1


# ── Frontend i18n (pending) va migratsiya ────────────────────────────────────

def test_i18n_pending_keys_consistent():
    path = os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T3.18.json')
    assert os.path.exists(path), 'pending/T3.18.json yo\'q'
    data = json.load(open(path, encoding='utf-8'))
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en']) and data['uz']
    for lang in data.values():
        assert all(isinstance(v, str) and v for v in lang.values())


def test_frontend_keys_exist_in_pending_or_dictionary():
    """Yangi tf('kalit', ...) kalitlari pending/T3.18.json da (yoki umumiy lug'atda) bo'lishi shart."""
    import re
    pending = json.load(open(os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T3.18.json'), encoding='utf-8'))['uz']
    uz_js = open(os.path.join(ROOT, 'frontend', 'src', 'i18n', 'uz.js'), encoding='utf-8').read()
    files = ['pages/admin/PaymentReconciliation.jsx', 'pages/admin/PosKassa.jsx', 'pages/admin/Settings.jsx']
    new_prefixes = ('reconcile.', 'settings.terminals.', 'settings.fiscal.attach', 'settings.fiscal.manualId',
                    'settings.fiscal.lockedSingle', 'settings.fiscal.noAttached', 'pos.referenceRequired',
                    'pos.referencePlaceholder', 'pos.terminalSelect', 'pos.fiscalSaveFailed')
    for rel in files:
        src = open(os.path.join(ROOT, 'frontend', 'src', rel), encoding='utf-8').read()
        for key in set(re.findall(r"tf\('([A-Za-z0-9_.]+)'", src)):
            if key.startswith(new_prefixes):
                assert key in pending or f"'{key}'" in uz_js, f"{rel}: {key} pending faylda yo'q"


def test_migration_matches_models():
    path = os.path.join(ROOT, 'alembic', 'versions', 't3_18_payment_fiscal_registry.py')
    py_compile.compile(path, doraise=True)
    src = open(path, encoding='utf-8').read()
    assert "revision = 't3_18'" in src and "down_revision = 't3_17'" in src
    # 6facd10: migratsiya idempotent xom SQL ga o'tkazilgan — jadval/ustun nomlari SQL matnida (qo'shtirnoqsiz)
    for token in ('fiscal_devices', 'payment_terminals', 'reference', 'terminal_id', 'fiscal_factory_id',
                  'ix_sale_payments_reference', 'uq_fiscal_devices_company_factory'):
        assert token in src, token
    # Modellardagi ustunlar migratsiyada bor (SQL ustun nomi sifatida, butun so'z)
    for col in (FiscalDevice.__table__.columns.keys() + PaymentTerminal.__table__.columns.keys()):
        assert re.search(r"\b" + col + r"\b", src), col
