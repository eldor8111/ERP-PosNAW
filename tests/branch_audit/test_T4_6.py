"""T4.6 — Filial amallari uchun tasdiqlash (approval) jarayonlari va rol bo'yicha limitlar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T4_6.py -q -p no:cacheprovider
"""
import asyncio
import itertools
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.approval import ApprovalRequest, ApprovalRule
from app.models.audit_log import AuditLog
from app.models.inventory import StockLevel, StockMovement
from app.models.moliya import Expense, ExpenseCategory, KassaMovement, KassaSession, Transaction, Wallet
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.user import UserRole
from app.services import approval_service
from app.services.sale_helpers import price_is_override

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
AP = '/api/approvals'


# ── Yordamchilar ──────────────────────────────────────────────────────────────

class _As:
    """`client.login` umumiy (global) override o'rnatadi; bu o'ram har so'rovdan oldin shu foydalanuvchini qayta kiritadi."""

    def __init__(self, client, user):
        self._client, self._user = client, user

    def __getattr__(self, name):
        def call(*a, **k):
            return getattr(self._client.login(self._user), name)(*a, **k)
        return call


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Telegram/FCM tarmoqqa chiqmasin; chaqiruvlar ro'yxatga yoziladi."""
    calls = []

    def fake_trigger(*a, **k):
        calls.append((a, k))

    import app.admin_tg_bot.notifications as notif
    monkeypatch.setattr(notif, 'trigger_instant_notification', fake_trigger)
    for mod in ('app.routers.finance', 'app.services.sale_create'):
        m = __import__(mod, fromlist=['x'])
        monkeypatch.setattr(m, 'trigger_instant_notification', fake_trigger, raising=False)
    async def fake_notify(*a, **k):
        return None

    monkeypatch.setattr(notif, 'notify_new_sale', fake_notify)
    monkeypatch.setattr('app.routers.sales.notify_new_sale', fake_notify, raising=False)
    import app.services.mobile_service as ms
    monkeypatch.setattr(ms, 'push_to_user', lambda *a, **k: None)
    return calls


def _product(db, company, wh, sale='100000', qty=1000):
    n = next(_seq)
    p = Product(name=f'Tovar {n}', sku=f'T46-{n}', barcode=f'B46-{n}', company_id=company.id,
                cost_price=Decimal('1000'), sale_price=Decimal(sale))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


def _wallet(db, company, branch, balance='1000000'):
    w = Wallet(name=f'Kassa {next(_seq)}', type='cash', balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status='open'))
    db.flush()
    return w


def _category(db, company):
    c = ExpenseCategory(name=f'Kategoriya {next(_seq)}', company_id=company.id)
    db.add(c)
    db.flush()
    return c


def _rule(db, company, action, role=None, branch=None, pct=None, amt=None, mode='require_approval', active=True):
    r = ApprovalRule(company_id=company.id, branch_id=branch.id if branch else None, action_type=action, role=role,
                     threshold_percent=Decimal(str(pct)) if pct is not None else None,
                     threshold_amount=Decimal(str(amt)) if amt is not None else None, mode=mode, is_active=active)
    db.add(r)
    db.flush()
    return r


def _sale_body(p, wh, qty=1, price=100000, discount=0, **item):
    it = {'product_id': p.id, 'quantity': qty}
    if discount:
        it['discount'] = discount
    it.update(item)
    unit = item.get('unit_price', price)
    total = unit * qty - discount
    return {'items': [it], 'payment_type': 'cash', 'paid_amount': total, 'paid_cash': total,
            'payments': [{'type': 'cash', 'amount': total}], 'warehouse_id': wh.id}


@pytest.fixture
def world(db, mk):
    ca = mk.company()
    bs, bt = mk.branch(ca, name='Samarqand'), mk.branch(ca, name='Toshkent')
    ws, wt = mk.warehouse(ca, bs), mk.warehouse(ca, bt)
    admin = mk.user(ca, role=UserRole.admin, branch=bt)
    director = mk.user(ca, role=UserRole.director, branch=None)
    manager_s = mk.user(ca, role=UserRole.manager, branch=bs)
    manager_t = mk.user(ca, role=UserRole.manager, branch=bt)
    cashier = mk.user(ca, role=UserRole.cashier, branch=bs)
    accountant = mk.user(ca, role=UserRole.accountant, branch=bs)
    wallet = _wallet(db, ca, bs)
    p = _product(db, ca, ws)
    cb, bb, wb, admin_b = mk.tenant(UserRole.admin)
    manager_b = mk.user(cb, role=UserRole.manager, branch=bb)
    return SimpleNamespace(ca=ca, bs=bs, bt=bt, ws=ws, wt=wt, admin=admin, director=director, manager_s=manager_s,
                           manager_t=manager_t, cashier=cashier, accountant=accountant, wallet=wallet, p=p,
                           cb=cb, bb=bb, admin_b=admin_b, manager_b=manager_b)


def _counts(db):
    return (db.query(Sale).count(), db.query(StockMovement).count(), db.query(KassaMovement).count())


def _request_from_detail(cl, detail, reason='Mijoz so\'radi'):
    r = cl.post(f'{AP}/requests', json={
        'action_type': detail['request_action_type'], 'amount': detail['amount'], 'payload': detail['payload'],
        'branch_id': detail.get('branch_id'), 'reason': reason,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _approved_req(db, user, payload, action='discount', branch_id=None, amount=1):
    req = approval_service.create_request(db, user, action_type=action, branch_id=branch_id, amount=amount, payload=payload)
    req.status = 'approved'
    req.decided_at = datetime.utcnow()
    db.flush()
    return req


# ── Qabul mezoni 5: qoida yo'q korxonada regressiya yo'q ──────────────────────

def test_no_rules_sale_passes(client, db, world):
    w = world
    r = client.login(w.cashier).post('/api/sales/', json=_sale_body(w.p, w.ws, discount=18000))
    assert r.status_code == 200, r.text
    # qo'lda past narx ham o'tadi
    r = client.login(w.cashier).post('/api/sales/', json=_sale_body(w.p, w.ws, unit_price=50000, price_manual=True))
    assert r.status_code == 200, r.text
    assert db.query(ApprovalRequest).count() == 0


def test_inactive_and_other_company_rules_ignored(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10, active=False)
    _rule(db, w.cb, 'discount', role='cashier', pct=1)          # boshqa korxona qoidasi
    _rule(db, w.ca, 'discount', role='manager', pct=1)          # boshqa rol
    r = client.login(w.cashier).post('/api/sales/', json=_sale_body(w.p, w.ws, discount=18000))
    assert r.status_code == 200, r.text


# ── Qabul mezoni 1-3: chegirma tasdiqlash oqimi ───────────────────────────────

def test_discount_approval_flow(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10)
    before = _counts(db)
    cl = _As(client, w.cashier)
    body = _sale_body(w.p, w.ws, discount=18000)
    r = cl.post('/api/sales/', json=body)
    assert r.status_code == 403, r.text
    d = r.json()['detail']
    assert d['code'] == 'approval_required' and d['action_type'] == 'discount'
    assert d['limit'] == 10 and d['actual'] == 18 and d['payload']['items'][0]['product_id'] == w.p.id
    assert _counts(db) == before        # sotuv, StockMovement va KassaMovement yaratilmadi

    # so'rov yuborish (payload 403 javobidan olinadi)
    req = _request_from_detail(cl, d)
    assert req['status'] == 'pending' and req['expires_at']
    # tasdiqlanmagan so'rov bilan sotuv o'tmaydi
    r = cl.post('/api/sales/', json={**body, 'approval_id': req['id']})
    assert r.status_code == 409 and r.json()['detail']['code'] == 'approval_invalid'

    # kassir kutish holatini ko'ra oladi
    assert cl.get(f'{AP}/requests/{req["id"]}').json()['status'] == 'pending'
    # menejer tasdiqlaydi
    assert client.login(w.manager_s).post(f'{AP}/requests/{req["id"]}/approve', json={'note': 'ok'}).status_code == 200
    assert cl.get(f'{AP}/requests/{req["id"]}').json()['status'] == 'approved'

    r = cl.post('/api/sales/', json={**body, 'approval_id': req['id']})
    assert r.status_code == 200, r.text
    assert _counts(db)[0] == before[0] + 1
    got = db.get(ApprovalRequest, req['id'])
    assert got.status == 'used' and got.used_at is not None
    assert got.reference_type == 'sale' and got.reference_id == r.json()['id']

    # ikkinchi marta shu approval_id -> 409 approval_invalid
    r = cl.post('/api/sales/', json={**body, 'approval_id': req['id']})
    assert r.status_code == 409 and r.json()['detail']['code'] == 'approval_invalid'
    assert _counts(db)[0] == before[0] + 1


def test_discount_at_limit_passes_and_other_roles_not_affected(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10)
    # aynan 10% — limitdan oshmaydi
    assert client.login(w.cashier).post('/api/sales/', json=_sale_body(w.p, w.ws, discount=10000)).status_code == 200
    # qoida faqat kassirga: menejer 18% chegirma qila oladi
    assert client.login(w.manager_s).post('/api/sales/', json=_sale_body(w.p, w.ws, discount=18000)).status_code == 200


def test_approval_hash_mismatch(client, db, world):
    w = world
    p2 = _product(db, w.ca, w.ws)
    _rule(db, w.ca, 'discount', role='cashier', pct=10)
    cl = _As(client, w.cashier)
    body = _sale_body(w.p, w.ws, discount=18000)
    d = cl.post('/api/sales/', json=body).json()['detail']
    req = _request_from_detail(cl, d)
    client.login(w.manager_s).post(f'{AP}/requests/{req["id"]}/approve')
    cl = _As(client, w.cashier)
    before = _counts(db)
    # boshqa mahsulot
    other = _sale_body(p2, w.ws, discount=18000)
    r = cl.post('/api/sales/', json={**other, 'approval_id': req['id']})
    assert r.status_code == 409 and r.json()['detail']['code'] == 'approval_invalid'
    # boshqa chegirma
    r = cl.post('/api/sales/', json={**_sale_body(w.p, w.ws, discount=20000), 'approval_id': req['id']})
    assert r.status_code == 409
    # boshqa narx (qo'lda)
    r = cl.post('/api/sales/', json={**_sale_body(w.p, w.ws, discount=18000, unit_price=90000, price_manual=True),
                                     'approval_id': req['id']})
    assert r.status_code == 409
    assert _counts(db) == before
    assert db.get(ApprovalRequest, req['id']).status == 'approved'      # ishlatilmadi
    # asl tarkib bilan esa o'tadi
    assert cl.post('/api/sales/', json={**body, 'approval_id': req['id']}).status_code == 200


def test_block_mode(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10, mode='block')
    before = _counts(db)
    r = client.login(w.cashier).post('/api/sales/', json=_sale_body(w.p, w.ws, discount=18000))
    assert r.status_code == 403
    d = r.json()['detail']
    assert d['code'] == 'limit_exceeded' and d['limit'] == 10 and d['actual'] == 18
    assert _counts(db) == before


def test_header_discount_amount_counts(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10, mode='block')
    body = _sale_body(w.p, w.ws)
    body['discount_amount'] = 30000
    body['paid_amount'] = body['paid_cash'] = 70000
    body['payments'] = [{'type': 'cash', 'amount': 70000}]
    r = client.login(w.cashier).post('/api/sales/', json=body)
    assert r.status_code == 403 and r.json()['detail']['code'] == 'limit_exceeded'


def test_price_override_rule(client, db, world):
    w = world
    _rule(db, w.ca, 'price_override', role='cashier', pct=5)
    cl = _As(client, w.cashier)
    # ro'yxat narxi (qo'lda emas) — override emas
    assert cl.post('/api/sales/', json=_sale_body(w.p, w.ws)).status_code == 200
    # 3% pasaytirilgan — limit ichida
    assert cl.post('/api/sales/', json=_sale_body(w.p, w.ws, unit_price=97000, price_manual=True)).status_code == 200
    # 1 200 000 -> 900 000 stsenariysi (25%)
    p = _product(db, w.ca, w.ws, sale='1200000')
    body = _sale_body(p, w.ws, unit_price=900000, price_manual=True)
    r = cl.post('/api/sales/', json=body)
    assert r.status_code == 403
    d = r.json()['detail']
    assert d['code'] == 'approval_required' and d['action_type'] == 'price_override' and d['actual'] == 25
    req = _request_from_detail(cl, d)
    assert client.login(w.manager_s).post(f'{AP}/requests/{req["id"]}/approve').status_code == 200
    assert client.login(w.cashier).post('/api/sales/', json={**body, 'approval_id': req['id']}).status_code == 200
    item = db.query(SaleItem).filter(SaleItem.product_id == p.id).one()
    assert Decimal(str(item.unit_price)) == Decimal('900000')


def test_promotion_and_customer_discount_not_counted(db, world):
    """Chegirma hisobi: faqat kassir kiritgan chegirma limitga kiradi (formula tekshiruvi)."""
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10)
    v = approval_service.evaluate_discount(db, w.cashier, w.p, 100000, 0, 1, branch_id=w.bs.id)
    assert v == []
    v = approval_service.evaluate_discount(db, w.cashier, w.p, 100000, 18000, 1, branch_id=w.bs.id)
    assert len(v) == 1 and v[0].actual == 18.0 and v[0].limit == 10.0 and v[0].mode == 'require_approval'
    # foiz: discount / (unit_price * qty) * 100
    v = approval_service.evaluate_discount(db, w.cashier, w.p, 50000, 11000, 2, branch_id=w.bs.id)
    assert v and v[0].actual == 11.0
    assert approval_service.evaluate_discount(db, w.cashier, w.p, 50000, 10000, 2, branch_id=w.bs.id) == []


def test_price_is_override_helper(db, world):
    w = world
    it = lambda **k: SimpleNamespace(unit_price=k.get('unit_price'), price_manual=k.get('price_manual'), currency_code='UZS')
    assert price_is_override(it(), w.p, None) is None
    assert price_is_override(it(unit_price=Decimal('100000')), w.p, None) is None
    assert price_is_override(it(unit_price=Decimal('90000')), w.p, None) == Decimal('100000')
    assert price_is_override(it(unit_price=Decimal('90000'), price_manual=False), w.p, None) is None
    # individual narx ro'yxat narxi hisoblanadi
    cp = SimpleNamespace(price=Decimal('80000'))
    assert price_is_override(it(unit_price=Decimal('85000')), w.p, cp) is None
    assert price_is_override(it(unit_price=Decimal('70000')), w.p, cp) == Decimal('80000')


def test_branch_rule_beats_company_rule(db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10)
    br = _rule(db, w.ca, 'discount', role='cashier', branch=w.bs, pct=30)
    got = approval_service.get_applicable_rule(db, w.ca.id, w.bs.id, 'discount', UserRole.cashier)
    assert got.id == br.id
    assert approval_service.evaluate_discount(db, w.cashier, w.p, 100000, 18000, 1, branch_id=w.bs.id) == []
    # boshqa filialda korxona qoidasi amal qiladi
    assert approval_service.evaluate_discount(db, w.cashier, w.p, 100000, 18000, 1, branch_id=w.bt.id)


# ── consume_approval ──────────────────────────────────────────────────────────

def test_consume_approval_single_use_expiry_and_ownership(db, world):
    w = world
    payload = {'items': [{'product_id': w.p.id, 'quantity': 1}]}
    h = approval_service.compute_payload_hash(payload)
    req = _approved_req(db, w.cashier, payload, branch_id=w.bs.id)
    # boshqa xodim ishlata olmaydi
    with pytest.raises(HTTPException) as e:
        approval_service.consume_approval(db, req.id, w.manager_s, 'discount', h)
    assert e.value.status_code == 409 and e.value.detail['code'] == 'approval_invalid'
    # boshqa amal turi
    with pytest.raises(HTTPException) as e:
        approval_service.consume_approval(db, req.id, w.cashier, 'refund', h)
    assert e.value.status_code == 409
    # hash mos kelmaydi
    with pytest.raises(HTTPException) as e:
        approval_service.consume_approval(db, req.id, w.cashier, 'discount', 'x' * 64)
    assert e.value.status_code == 409
    # to'g'ri — bir marta
    got = approval_service.consume_approval(db, req.id, w.cashier, 'discount', h)
    assert got.status == 'used'
    with pytest.raises(HTTPException) as e:
        approval_service.consume_approval(db, req.id, w.cashier, 'discount', h)
    assert e.value.status_code == 409 and 'ishlatilgan' in e.value.detail['message']
    # muddati o'tgan
    old = _approved_req(db, w.cashier, payload)
    old.expires_at = datetime.utcnow() - timedelta(minutes=1)
    with pytest.raises(HTTPException) as e:
        approval_service.consume_approval(db, old.id, w.cashier, 'discount', h)
    assert e.value.status_code == 409 and e.value.detail['code'] == 'approval_invalid'
    # kutilayotgan / rad etilgan
    pend = approval_service.create_request(db, w.cashier, action_type='discount', branch_id=None, amount=1, payload=payload)
    with pytest.raises(HTTPException):
        approval_service.consume_approval(db, pend.id, w.cashier, 'discount', h)
    # mavjud bo'lmagan
    with pytest.raises(HTTPException):
        approval_service.consume_approval(db, 99999, w.cashier, 'discount', h)


def test_consume_approval_other_company(db, world):
    w = world
    payload = {'items': [{'product_id': w.p.id, 'quantity': 1}]}
    req = _approved_req(db, w.cashier, payload)
    outsider = SimpleNamespace(id=w.cashier.id, company_id=w.cb.id)
    with pytest.raises(HTTPException) as e:
        approval_service.consume_approval(db, req.id, outsider, 'discount', approval_service.compute_payload_hash(payload))
    assert e.value.status_code == 409


def test_payload_hash_canonical():
    h = approval_service.compute_payload_hash
    a = {'items': [{'product_id': 1, 'quantity': 1, 'discount': 18000.0}, {'product_id': 2, 'quantity': '2.00'}]}
    b = {'items': [{'quantity': 2, 'product_id': 2, 'variant_id': None}, {'discount': '18000', 'quantity': Decimal('1'), 'product_id': 1}]}
    assert h(a) == h(b)
    assert h(a) != h({'items': [{'product_id': 1, 'quantity': 1, 'discount': 17000}, {'product_id': 2, 'quantity': 2}]})


# ── Qabul mezoni 4: o'z so'rovini tasdiqlash va izolyatsiya ───────────────────

def test_self_approval_forbidden_and_roles(client, db, world):
    w = world
    r = client.login(w.manager_s).post(f'{AP}/requests', json={
        'action_type': 'refund', 'amount': 500, 'payload': {'sale_id': 1}, 'reason': 'x'})
    assert r.status_code == 201
    rid = r.json()['id']
    # o'z so'rovi
    assert client.login(w.manager_s).post(f'{AP}/requests/{rid}/approve').status_code == 403
    assert client.login(w.manager_s).post(f'{AP}/requests/{rid}/reject').status_code == 403
    # kassir/buxgalter tasdiqlay olmaydi
    assert client.login(w.cashier).post(f'{AP}/requests/{rid}/approve').status_code == 403
    assert client.login(w.accountant).post(f'{AP}/requests/{rid}/approve').status_code == 403
    assert db.get(ApprovalRequest, rid).status == 'pending'
    # direktor tasdiqlaydi
    assert client.login(w.director).post(f'{AP}/requests/{rid}/approve').status_code == 200
    # qayta hal qilish — 409
    assert client.login(w.director).post(f'{AP}/requests/{rid}/reject').status_code == 409


def test_cashier_cannot_approve_own_request(client, db, world):
    w = world
    r = client.login(w.cashier).post(f'{AP}/requests', json={
        'action_type': 'refund', 'amount': 500, 'payload': {'sale_id': 1}})
    rid = r.json()['id']
    assert client.login(w.cashier).post(f'{AP}/requests/{rid}/approve').status_code == 403


def test_cross_company_and_cross_branch_isolation(client, db, world):
    w = world
    r = client.login(w.cashier).post(f'{AP}/requests', json={
        'action_type': 'refund', 'amount': 500, 'payload': {'sale_id': 1}})
    rid = r.json()['id']
    # boshqa korxona: ko'rinmaydi, tasdiqlay olmaydi
    for u in (w.admin_b, w.manager_b):
        assert client.login(u).post(f'{AP}/requests/{rid}/approve').status_code == 404
        assert client.login(u).post(f'{AP}/requests/{rid}/reject').status_code == 404
        assert client.login(u).get(f'{AP}/requests/{rid}').status_code == 404
        assert all(x['id'] != rid for x in client.login(u).get(f'{AP}/requests').json())
    # boshqa filial menejeri: 403, ko'rmaydi
    assert client.login(w.manager_t).post(f'{AP}/requests/{rid}/approve').status_code == 403
    assert client.login(w.manager_t).get(f'{AP}/requests/{rid}').status_code == 404
    assert all(x['id'] != rid for x in client.login(w.manager_t).get(f'{AP}/requests').json())
    # boshqa kassir ham ko'ra olmaydi
    other = SimpleNamespace()
    assert db.get(ApprovalRequest, rid).status == 'pending'
    # o'z filiali menejeri ro'yxatda ko'radi va tasdiqlaydi
    assert any(x['id'] == rid for x in client.login(w.manager_s).get(f'{AP}/requests?status=pending').json())
    assert client.login(w.manager_s).post(f'{AP}/requests/{rid}/approve').status_code == 200
    assert db.get(ApprovalRequest, rid).decided_by == w.manager_s.id


def test_cashier_lists_only_own(client, db, world):
    w = world
    client.login(w.cashier).post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {'a': 1}})
    client.login(w.manager_s).post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {'a': 2}})
    rows = client.login(w.cashier).get(f'{AP}/requests').json()
    assert len(rows) == 1 and rows[0]['requested_by'] == w.cashier.id
    assert len(client.login(w.director).get(f'{AP}/requests').json()) == 2
    assert len(client.login(w.director).get(f'{AP}/requests?mine=true').json()) == 0


def test_request_validation_and_duplicate(client, db, world):
    w = world
    cl = _As(client, w.cashier)
    assert cl.post(f'{AP}/requests', json={'action_type': 'nope', 'amount': 1, 'payload': {}}).status_code == 422
    assert cl.post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {},
                                          'branch_id': w.bb.id}).status_code == 404       # begona filial
    a = cl.post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {'x': 1}}).json()
    b = cl.post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {'x': 1.0}}).json()
    assert a['id'] == b['id']                                  # takroriy so'rov qayta yaratilmaydi
    # admin so'rov yubormaydi (ozod)
    assert client.login(w.admin).post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {}}).status_code == 403
    row = db.get(ApprovalRequest, a['id'])
    assert row.branch_id == w.bs.id and row.payload_hash == approval_service.compute_payload_hash({'x': 1})
    assert timedelta(minutes=14) < (row.expires_at - row.created_at.replace(tzinfo=None)) <= timedelta(minutes=15, seconds=5)


def test_expired_request_410_and_audit(client, db, world):
    w = world
    r = client.login(w.cashier).post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {'z': 1}})
    rid = r.json()['id']
    db.get(ApprovalRequest, rid).expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()
    assert client.login(w.manager_s).post(f'{AP}/requests/{rid}/approve').status_code == 410
    assert db.get(ApprovalRequest, rid).status == 'expired'
    assert client.login(w.manager_s).post(f'{AP}/requests/{rid}/approve').status_code == 409
    assert db.query(AuditLog).filter(AuditLog.action == 'APPROVAL_EXPIRE', AuditLog.entity_id == rid).count() == 1
    # kassir kutib turgan so'rov muddati tugasa ham 'expired' ko'radi
    r2 = client.login(w.cashier).post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {'z': 2}})
    rid2 = r2.json()['id']
    db.get(ApprovalRequest, rid2).expires_at = datetime.utcnow() - timedelta(seconds=5)
    db.flush()
    assert client.login(w.cashier).get(f'{AP}/requests/{rid2}').json()['status'] == 'expired'


def test_reject_flow(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10)
    cl = _As(client, w.cashier)
    body = _sale_body(w.p, w.ws, discount=18000)
    req = _request_from_detail(cl, cl.post('/api/sales/', json=body).json()['detail'])
    assert client.login(w.manager_s).post(f'{AP}/requests/{req["id"]}/reject', json={'note': "Yo'q"}).status_code == 200
    got = db.get(ApprovalRequest, req['id'])
    assert got.status == 'rejected' and got.decision_note == "Yo'q"
    assert client.login(w.cashier).post('/api/sales/', json={**body, 'approval_id': req['id']}).status_code == 409


# ── Qabul mezoni 10-11: audit va ozod rollar ──────────────────────────────────

def test_audit_trail_for_decisions(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10)
    cl = _As(client, w.cashier)
    body = _sale_body(w.p, w.ws, discount=18000)
    req = _request_from_detail(cl, cl.post('/api/sales/', json=body).json()['detail'])
    client.login(w.manager_s).post(f'{AP}/requests/{req["id"]}/approve')
    assert client.login(w.cashier).post('/api/sales/', json={**body, 'approval_id': req['id']}).status_code == 200
    r2 = client.login(w.cashier).post(f'{AP}/requests', json={'action_type': 'refund', 'amount': 1, 'payload': {'q': 1}}).json()
    client.login(w.manager_s).post(f'{AP}/requests/{r2["id"]}/reject')
    actions = {(a.action, a.entity_id) for a in db.query(AuditLog).filter(AuditLog.entity_type == 'approval_request')}
    assert ('APPROVAL_REQUEST', req['id']) in actions
    assert ('APPROVAL_APPROVE', req['id']) in actions
    assert ('APPROVAL_USE', req['id']) in actions
    assert ('APPROVAL_REJECT', r2['id']) in actions
    appr = db.query(AuditLog).filter(AuditLog.action == 'APPROVAL_APPROVE', AuditLog.entity_id == req['id']).one()
    assert appr.user_id == w.manager_s.id and appr.company_id == w.ca.id and appr.branch_id == w.bs.id


def test_admin_director_exempt_but_audited(client, db, world):
    w = world
    _rule(db, w.ca, 'discount', role='cashier', pct=10, mode='block')
    for u in (w.admin, w.director):
        assert client.login(u).post('/api/sales/', json=_sale_body(w.p, w.ws, discount=18000)).status_code == 200
    rows = db.query(AuditLog).filter(AuditLog.action == 'APPROVAL_EXEMPT').all()
    assert {r.user_id for r in rows} == {w.admin.id, w.director.id}
    assert rows[0].new_values['action_type'] == 'discount' and rows[0].new_values['actual'] == 18
    # limit ichidagi amal audit'ga yozilmaydi
    n = len(rows)
    client.login(w.admin).post('/api/sales/', json=_sale_body(w.p, w.ws, discount=5000))
    assert db.query(AuditLog).filter(AuditLog.action == 'APPROVAL_EXEMPT').count() == n


# ── Qoidalar CRUD ─────────────────────────────────────────────────────────────

def test_rules_crud_and_validation(client, db, world):
    w = world
    cl = _As(client, w.admin)
    r = cl.post(f'{AP}/rules', json={'action_type': 'discount', 'role': 'cashier', 'threshold_percent': 10,
                                     'mode': 'require_approval'})
    assert r.status_code == 201, r.text
    rid = r.json()['id']
    assert r.json()['company_id'] == w.ca.id and r.json()['threshold_percent'] == 10
    assert cl.post(f'{AP}/rules', json={'action_type': 'discount', 'threshold_percent': 150}).status_code == 422
    assert cl.post(f'{AP}/rules', json={'action_type': 'discount', 'threshold_percent': -1}).status_code == 422
    assert cl.post(f'{AP}/rules', json={'action_type': 'bad'}).status_code == 422
    assert cl.post(f'{AP}/rules', json={'action_type': 'discount', 'role': 'xxx'}).status_code == 422
    assert cl.post(f'{AP}/rules', json={'action_type': 'discount', 'mode': 'x'}).status_code == 422
    assert cl.post(f'{AP}/rules', json={'action_type': 'expense', 'branch_id': w.bb.id}).status_code == 404
    assert cl.post(f'{AP}/rules', json={'action_type': 'expense', 'branch_id': w.bs.id, 'threshold_amount': 5}).status_code == 201

    assert cl.patch(f'{AP}/rules/{rid}', json={'threshold_percent': 20, 'mode': 'block'}).json()['threshold_percent'] == 20
    assert cl.patch(f'{AP}/rules/{rid}', json={'threshold_percent': 101}).status_code == 422
    assert cl.patch(f'{AP}/rules/{rid}', json={'is_active': False}).json()['is_active'] is False
    assert len(cl.get(f'{AP}/rules').json()) == 2

    # boshqa korxona qoidasiga tegib bo'lmaydi
    other = client.login(w.admin_b)
    assert other.patch(f'{AP}/rules/{rid}', json={'mode': 'block'}).status_code == 404
    assert other.delete(f'{AP}/rules/{rid}').status_code == 404
    assert other.get(f'{AP}/rules').json() == []
    # rol cheklovi
    for u in (w.cashier, w.manager_s, w.accountant):
        assert client.login(u).get(f'{AP}/rules').status_code == 403
        assert client.login(u).post(f'{AP}/rules', json={'action_type': 'discount'}).status_code == 403
    assert client.login(w.director).get(f'{AP}/rules').status_code == 200

    assert cl.delete(f'{AP}/rules/{rid}').status_code == 200
    assert db.get(ApprovalRule, rid) is None
    acts = {a.action for a in db.query(AuditLog).filter(AuditLog.entity_type == 'approval_rule')}
    assert {'APPROVAL_RULE_CREATE', 'APPROVAL_RULE_UPDATE', 'APPROVAL_RULE_DELETE'} <= acts


# ── Qaytarish va sotuvni o'chirish ────────────────────────────────────────────

def _admin_sale(client, w, qty=1):
    r = client.login(w.admin).post('/api/sales/', json=_sale_body(w.p, w.ws, qty=qty))
    assert r.status_code == 200, r.text
    return r.json()['id']


def test_partial_return_requires_approval(client, db, world):
    w = world
    sale_id = _admin_sale(client, w, qty=3)
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale_id).one()
    _rule(db, w.ca, 'refund', role='cashier', amt=50000)
    cl = _As(client, w.cashier)
    body = {'items': [{'sale_item_id': item.id, 'quantity': 1}], 'payment_type': 'cash'}
    before = db.query(Sale).count()
    r = cl.post(f'/api/sales/{sale_id}/return-items', json=body)
    assert r.status_code == 403, r.text
    d = r.json()['detail']
    assert d['code'] == 'approval_required' and d['action_type'] == 'refund' and d['actual'] == 100000
    assert db.query(Sale).count() == before and db.get(SaleItem, item.id).returned_quantity in (None, 0)
    req = _request_from_detail(cl, d)
    assert client.login(w.manager_s).post(f'{AP}/requests/{req["id"]}/approve').status_code == 200
    r = client.login(w.cashier).post(f'/api/sales/{sale_id}/return-items', json={**body, 'approval_id': req['id']})
    assert r.status_code == 200, r.text
    assert db.query(Sale).count() == before + 1
    assert db.get(ApprovalRequest, req['id']).status == 'used'
    # ikkinchi marta ishlatib bo'lmaydi
    r = client.login(w.cashier).post(f'/api/sales/{sale_id}/return-items', json={**body, 'approval_id': req['id']})
    assert r.status_code == 409 and r.json()['detail']['code'] == 'approval_invalid'


def test_partial_return_block_and_no_rule(client, db, world):
    w = world
    sale_id = _admin_sale(client, w, qty=2)
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale_id).one()
    body = {'items': [{'sale_item_id': item.id, 'quantity': 1}], 'payment_type': 'cash'}
    # qoidasiz — o'tadi
    assert client.login(w.cashier).post(f'/api/sales/{sale_id}/return-items', json=body).status_code == 200
    _rule(db, w.ca, 'refund', role='cashier', amt=50000, mode='block')
    r = client.login(w.cashier).post(f'/api/sales/{sale_id}/return-items', json=body)
    assert r.status_code == 403 and r.json()['detail']['code'] == 'limit_exceeded'
    # admin ozod
    assert client.login(w.admin).post(f'/api/sales/{sale_id}/return-items', json=body).status_code == 200


def test_return_sale_requires_approval(client, db, world):
    w = world
    _rule(db, w.ca, 'refund', role='cashier', amt=50000)
    body = {'items': [{'product_id': w.p.id, 'quantity': 1, 'unit_price': 100000}], 'payment_type': 'cash',
            'paid_amount': 100000, 'paid_cash': 100000, 'warehouse_id': w.ws.id, 'wallet_id': w.wallet.id}
    cl = _As(client, w.cashier)
    before = db.query(Sale).count()
    r = cl.post('/api/sales/return', json=body)
    assert r.status_code == 403 and r.json()['detail']['code'] == 'approval_required', r.text
    req = _request_from_detail(cl, r.json()['detail'])
    client.login(w.manager_s).post(f'{AP}/requests/{req["id"]}/approve')
    r = client.login(w.cashier).post('/api/sales/return', json={**body, 'approval_id': req['id']})
    assert r.status_code == 200, r.text
    assert db.query(Sale).count() == before + 1
    assert db.get(ApprovalRequest, req['id']).status == 'used'


def test_sale_delete_limit(client, db, world):
    w = world
    sale_id = _admin_sale(client, w)
    _rule(db, w.ca, 'sale_delete', role='manager', amt=50000, mode='block')
    r = client.login(w.manager_s).delete(f'/api/sales/{sale_id}')
    assert r.status_code == 403 and r.json()['detail']['code'] == 'limit_exceeded'
    assert db.get(Sale, sale_id) is not None
    assert client.login(w.admin).delete(f'/api/sales/{sale_id}').status_code == 200
    assert db.get(Sale, sale_id) is None


def test_sale_delete_with_consumed_approval(db, world):
    from app.services.sale_delete import delete_sale
    w = world
    s = Sale(number='S-T46', company_id=w.ca.id, branch_id=w.bs.id, warehouse_id=w.ws.id, cashier_id=w.cashier.id,
             total_amount=Decimal('100000'), paid_amount=Decimal('100000'), payment_type='cash', status='completed')
    db.add(s)
    db.flush()
    _rule(db, w.ca, 'sale_delete', role='manager', amt=50000)
    with pytest.raises(HTTPException) as e:
        delete_sale(db, s.id, w.manager_s)
    assert e.value.status_code == 403 and e.value.detail['code'] == 'approval_required'
    req = _approved_req(db, w.manager_s, approval_service.sale_delete_payload(s.id), action='sale_delete',
                        branch_id=w.bs.id)
    delete_sale(db, s.id, w.manager_s, approval_id=req.id)
    assert db.get(ApprovalRequest, req.id).status == 'used'


# ── Qabul mezoni 6-7: xarajat pending -> approved/rejected ────────────────────

def _expense(cl, w, cat, amount, **kw):
    return cl.post('/api/kassa/do-expense', json={'wallet_id': w.wallet.id, 'category_id': cat.id, 'amount': amount,
                                                  'payment_type': 'cash', 'description': 'Test', **kw})


def _exp(db, expense_id):
    """pending/rejected xarajatlar standart so'rovda ko'rinmaydi — tekshiruv uchun maxsus parametr."""
    return db.get(Expense, expense_id, execution_options={'include_unapproved_expenses': True})


def _wallet_state(db, w):
    db.refresh(w.wallet)
    return (Decimal(str(w.wallet.balance)),
            db.query(KassaMovement).filter(KassaMovement.reference_type == 'expense').count(),
            db.query(Transaction).filter(Transaction.reference_type == 'expense').count())


def test_expense_without_rule_and_created_by(client, db, world):
    w = world
    cat = _category(db, w.ca)
    r = _expense(client.login(w.accountant), w, cat, 400000)
    assert r.status_code == 200, r.text
    assert r.json() == {'ok': True, 'expense_id': r.json()['expense_id']}
    exp = _exp(db, r.json()['expense_id'])
    assert exp.status == 'approved' and exp.created_by == w.accountant.id and exp.approved_by is None
    assert _wallet_state(db, w) == (Decimal('600000'), 1, 1)
    # admin ham xuddi shunday: created_by = admin, approved_by = NULL (yaratuvchi bilan bir xil bo'lib qolmaydi)
    r = _expense(client.login(w.admin), w, cat, 1000)
    exp = _exp(db, r.json()['expense_id'])
    assert exp.created_by == w.admin.id and exp.approved_by is None


def test_expense_pending_approve_flow(client, db, world, _no_network):
    w = world
    cat = _category(db, w.ca)
    _rule(db, w.ca, 'expense', role='accountant', amt=100000)
    # limit ichida — darhol
    r = _expense(client.login(w.accountant), w, cat, 100000)
    assert r.status_code == 200 and _wallet_state(db, w) == (Decimal('900000'), 1, 1)
    # limitdan katta — pending, pul harakati yo'q
    _no_network.clear()
    r = _expense(client.login(w.accountant), w, cat, 500000)
    assert r.status_code == 202, r.text
    j = r.json()
    assert j['ok'] is True and j['status'] == 'pending' and j['expense_id'] and j['approval_request_id']
    exp = _exp(db, j['expense_id'])
    assert exp.status == 'pending' and exp.created_by == w.accountant.id and exp.approved_by is None
    assert exp.approval_request_id == j['approval_request_id']
    assert _wallet_state(db, w) == (Decimal('900000'), 1, 1)       # balans, harakat, tranzaksiya o'zgarmadi
    # Telegram: tugmali xabar yuborildi (approval turi)
    sent = [c for c in _no_network if len(c[0]) >= 3 and c[0][2] == 'approval']
    assert len(sent) == 1 and sent[0][0][0] == w.ca.id and sent[0][0][3] == w.bs.id
    kb = sent[0][1]['reply_markup'].inline_keyboard[0]
    assert [b.callback_data for b in kb] == [f'appr:ok:{j["approval_request_id"]}', f'appr:no:{j["approval_request_id"]}']
    # boshqa filial menejeri tasdiqlay olmaydi
    assert client.login(w.manager_t).post(f'{AP}/requests/{j["approval_request_id"]}/approve').status_code == 403
    assert _wallet_state(db, w)[0] == Decimal('900000')
    # menejer tasdiqlaydi -> balans BIR marta kamayadi
    assert client.login(w.manager_s).post(f'{AP}/requests/{j["approval_request_id"]}/approve').status_code == 200
    db.refresh(exp)
    assert exp.status == 'approved' and exp.approved_by == w.manager_s.id and exp.created_by == w.accountant.id
    assert _wallet_state(db, w) == (Decimal('400000'), 2, 2)
    mv = db.query(KassaMovement).filter(KassaMovement.reference_id == exp.id, KassaMovement.reference_type == 'expense').one()
    assert mv.created_by == w.accountant.id and Decimal(str(mv.amount)) == Decimal('500000')
    # ikkinchi tasdiq — 409, balans o'zgarmaydi
    assert client.login(w.director).post(f'{AP}/requests/{j["approval_request_id"]}/approve').status_code == 409
    assert _wallet_state(db, w) == (Decimal('400000'), 2, 2)
    assert db.query(AuditLog).filter(AuditLog.action == 'EXPENSE_APPROVE', AuditLog.entity_id == exp.id).count() == 1


def test_expense_pending_reject_and_expire(client, db, world):
    w = world
    cat = _category(db, w.ca)
    _rule(db, w.ca, 'expense', role='accountant', amt=100000)
    j = _expense(client.login(w.accountant), w, cat, 300000).json()
    assert client.login(w.manager_s).post(f'{AP}/requests/{j["approval_request_id"]}/reject', json={'note': 'Keraksiz'}).status_code == 200
    exp = _exp(db, j['expense_id'])
    assert exp.status == 'rejected' and exp.approved_by is None
    assert _wallet_state(db, w) == (Decimal('1000000'), 0, 0)
    # rad etilgan so'rovni tasdiqlab bo'lmaydi
    assert client.login(w.director).post(f'{AP}/requests/{j["approval_request_id"]}/approve').status_code == 409
    # muddati o'tgan xarajat so'rovi -> xarajat rad etiladi
    j2 = _expense(client.login(w.accountant), w, cat, 300000).json()
    db.get(ApprovalRequest, j2['approval_request_id']).expires_at = datetime.utcnow() - timedelta(minutes=1)
    db.flush()
    assert client.login(w.director).post(f'{AP}/requests/{j2["approval_request_id"]}/approve').status_code == 410
    assert _exp(db, j2['expense_id']).status == 'rejected'
    assert _wallet_state(db, w) == (Decimal('1000000'), 0, 0)


def test_expense_block_mode_and_exempt(client, db, world):
    w = world
    cat = _category(db, w.ca)
    _rule(db, w.ca, 'expense', amt=100000, mode='block')          # barcha rollar (admin/director ozod)
    r = _expense(client.login(w.accountant), w, cat, 500000)
    assert r.status_code == 403 and r.json()['detail']['code'] == 'limit_exceeded'
    assert db.query(Expense).count() == 0 and _wallet_state(db, w) == (Decimal('1000000'), 0, 0)
    assert _expense(client.login(w.admin), w, cat, 500000).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.action == 'APPROVAL_EXEMPT', AuditLog.user_id == w.admin.id).count() == 1


def test_finance_expense_pending_and_listing(client, db, world):
    w = world
    cat = _category(db, w.ca)
    _rule(db, w.ca, 'expense', role='manager', amt=100000)
    cl = _As(client, w.manager_s)
    body = {'category_id': cat.id, 'amount': 500000, 'wallet_id': w.wallet.id, 'description': 'Moliya'}
    r = cl.post('/api/finance/expenses', json=body)
    assert r.status_code == 201, r.text
    eid = r.json()['id']
    exp = _exp(db, eid)
    assert exp.status == 'pending' and exp.created_by == w.manager_s.id and exp.approved_by is None
    assert _wallet_state(db, w) == (Decimal('1000000'), 0, 0)
    # standart ro'yxatda yo'q (P&L/kassaga o'xshab), status=pending bilan bor
    ids = [e['id'] for e in cl.get('/api/finance/expenses').json()]
    assert eid not in ids
    rows = cl.get('/api/finance/expenses?status=pending').json()
    assert [e['id'] for e in rows] == [eid] and rows[0]['status'] == 'pending' and rows[0]['created_by'] == w.manager_s.id
    assert eid in [e['id'] for e in cl.get('/api/finance/expenses?status=all').json()]
    # boshqa menejer (bu filial) tasdiqlaydi
    other = client.login(w.director)
    assert other.post(f'{AP}/requests/{exp.approval_request_id}/approve').status_code == 200
    rows = {e['id']: e for e in cl.get('/api/finance/expenses').json()}
    assert rows[eid]['status'] == 'approved' and rows[eid]['approved_by'] == w.director.id
    assert rows[eid]['created_by'] == w.manager_s.id
    assert _wallet_state(db, w) == (Decimal('500000'), 1, 1)


def test_finance_expense_within_limit_has_no_approver(client, db, world):
    w = world
    cat = _category(db, w.ca)
    r = client.login(w.admin).post('/api/finance/expenses', json={
        'category_id': cat.id, 'amount': 1000, 'wallet_id': w.wallet.id})
    assert r.status_code == 201, r.text
    exp = _exp(db, r.json()['id'])
    assert exp.status == 'approved' and exp.created_by == w.admin.id and exp.approved_by is None


def test_void_pending_expense_does_not_touch_balance(client, db, world):
    w = world
    cat = _category(db, w.ca)
    _rule(db, w.ca, 'expense', role='accountant', amt=100000)
    j = _expense(client.login(w.accountant), w, cat, 300000).json()
    assert client.login(w.admin).delete(f'/api/kassa/expense/{j["expense_id"]}').status_code == 200
    exp = _exp(db, j['expense_id'])
    assert exp.voided_at is not None and exp.status == 'rejected'
    assert _wallet_state(db, w) == (Decimal('1000000'), 0, 0)                 # balans oshib ketmadi
    assert db.get(ApprovalRequest, j['approval_request_id']).status == 'rejected'
    # tasdiq kutayotgan xarajatni tahrirlab bo'lmaydi
    j2 = _expense(client.login(w.accountant), w, cat, 300000).json()
    r = client.login(w.admin).put(f'/api/kassa/expense/{j2["expense_id"]}', json={'amount': 1000})
    assert r.status_code == 409


def test_update_expense_checks_limit_for_non_exempt(db, world):
    """summa oshirilsa limit qayta tekshiriladi (servis darajasida: block rejimida 403)."""
    w = world
    _rule(db, w.ca, 'expense', role='accountant', amt=100000, mode='block')
    v = approval_service.evaluate_expense(db, w.accountant, w.bs.id, Decimal('150000'))
    assert v is not None and v.mode == 'block' and v.limit == 100000 and v.actual == 150000
    assert approval_service.evaluate_expense(db, w.accountant, w.bs.id, Decimal('100000')) is None


def test_pending_and_rejected_expenses_excluded_from_reports(client, db, world):
    """Qabul mezoni 8: pending/rejected xarajat P&L, filial xulosasi va kassa balansiga kirmaydi; tasdiqdan keyin kiradi."""
    from app.services.pnl_service import compute_pnl
    w = world
    cat = _category(db, w.ca)
    _rule(db, w.ca, 'expense', role='accountant', amt=100000)
    now = datetime.utcnow()

    def pnl_total():
        return float(compute_pnl(db, w.ca.id, now - timedelta(days=1), now + timedelta(days=1), None)['expenses']['total'])

    j = _expense(client.login(w.accountant), w, cat, 300000).json()
    assert pnl_total() == 0
    assert db.query(Expense).execution_options(include_unapproved_expenses=True).count() == 1   # qator bazada bor
    assert db.query(Expense).count() == 0                                                         # lekin standart so'rovda yo'q
    # rad etilgan ham kirmaydi
    client.login(w.manager_s).post(f'{AP}/requests/{j["approval_request_id"]}/reject')
    assert pnl_total() == 0
    # yangi pending -> tasdiq -> kiradi (aynan bir marta)
    j2 = _expense(client.login(w.accountant), w, cat, 200000).json()
    assert pnl_total() == 0
    client.login(w.manager_s).post(f'{AP}/requests/{j2["approval_request_id"]}/approve')
    assert pnl_total() == 200000
    # kassa balansi (Moliya) faqat tasdiqlangan xarajatni ko'radi
    r = client.login(w.admin).get('/api/finance/cash-balance')
    assert r.status_code == 200 and r.json()['total_expense'] == 200000


# ── Qabul mezoni 9: Telegram ──────────────────────────────────────────────────

def test_approval_keyboard_buttons():
    from app.admin_tg_bot.notifications import approval_keyboard
    kb = approval_keyboard(42).inline_keyboard[0]
    assert [b.callback_data for b in kb] == ['appr:ok:42', 'appr:no:42']


def test_notify_approvers_sends_button_message(db, world, _no_network):
    w = world
    req = approval_service.create_request(db, w.cashier, action_type='refund', branch_id=w.bs.id, amount=1234,
                                          payload={'a': 1}, reason='Sabab')
    _no_network.clear()
    approval_service.notify_approvers(db, req)
    assert len(_no_network) == 1
    args, kwargs = _no_network[0]
    assert args[0] == w.ca.id and args[2] == 'approval' and args[3] == w.bs.id
    assert 'Qaytarish' in args[1] and 'Sabab' in args[1] and 'Samarqand' in args[1]
    assert kwargs['reply_markup'].inline_keyboard[0][0].callback_data == f'appr:ok:{req.id}'


def test_prepare_send_approval_recipients(db, world, monkeypatch):
    import app.database as app_database
    from app.admin_tg_bot import notifications as notif
    from app.admin_tg_bot.models import CompanyBot
    w = world
    for i, u in enumerate((w.admin, w.director, w.manager_s, w.manager_t, w.cashier), start=1):
        u.tg_chat_id = f'tg{i}'
    db.add(CompanyBot(company_id=w.ca.id, bot_type='admin', bot_token='123:abc', is_active=True,
                      notify_instant_finance=False, notify_instant_sales=False))
    db.flush()
    monkeypatch.setattr(notif, 'SessionLocal', app_database.SessionLocal)
    # moliya xabarnomasi o'chiq, lekin tasdiq so'rovi baribir yuboriladi
    assert notif._prepare_send(w.ca.id, 'finance', w.bs.id) is None
    token, chats = notif._prepare_send(w.ca.id, 'approval', w.bs.id)
    assert token == '123:abc'
    assert set(chats) == {'tg1', 'tg2', 'tg3'}        # admin, director, SHU filial menejeri (boshqa filial/kassir yo'q)


def _fake_callback(tg_id, data):
    answers = []

    async def answer(text=None, show_alert=False):
        answers.append(text)

    return SimpleNamespace(data=data, from_user=SimpleNamespace(id=tg_id), answer=answer, message=None), answers


def test_telegram_callback_approves_and_isolates_companies(db, world, monkeypatch):
    import app.database as app_database
    from app.admin_tg_bot import bot_manager
    w = world
    monkeypatch.setattr(bot_manager, 'SessionLocal', app_database.SessionLocal)
    w.manager_s.tg_chat_id = '7001'
    w.manager_b.tg_chat_id = '7002'
    w.cashier.tg_chat_id = '7003'
    w.manager_t.tg_chat_id = '7004'
    req = approval_service.create_request(db, w.cashier, action_type='refund', branch_id=w.bs.id, amount=10, payload={'a': 1})
    db.commit()

    def click(tg_id, data, company_id):
        cb, answers = _fake_callback(tg_id, data)
        asyncio.run(bot_manager.handle_approval_callback(cb, company_id))
        return answers[-1] if answers else None

    # boshqa korxona boti / boshqa korxona xodimi: rad etiladi
    assert 'ro\'yxatdan o\'tmagansiz' in click(7002, f'appr:ok:{req.id}', w.ca.id)
    assert 'topilmadi' in click(7002, f'appr:ok:{req.id}', w.cb.id)
    # so'rovchining o'zi (kassir) bot a'zosi emas
    assert 'ro\'yxatdan o\'tmagansiz' in click(7003, f'appr:ok:{req.id}', w.ca.id)
    # boshqa filial menejeri
    assert 'boshqa filialga' in click(7004, f'appr:ok:{req.id}', w.ca.id)
    db.refresh(req)
    assert req.status == 'pending'
    # soxta callback
    assert click(7001, 'appr:ok:abc', w.ca.id) is None
    # o'z filiali menejeri tasdiqlaydi
    assert 'Tasdiqlandi' in click(7001, f'appr:ok:{req.id}', w.ca.id)
    db.refresh(req)
    assert req.status == 'approved' and req.decided_by == w.manager_s.id
    # qayta bosish — allaqachon hal qilingan
    assert 'allaqachon' in click(7001, f'appr:no:{req.id}', w.ca.id)
    assert db.query(AuditLog).filter(AuditLog.action == 'APPROVAL_APPROVE', AuditLog.entity_id == req.id).count() == 1


def test_telegram_callback_reject(db, world, monkeypatch):
    import app.database as app_database
    from app.admin_tg_bot import bot_manager
    w = world
    monkeypatch.setattr(bot_manager, 'SessionLocal', app_database.SessionLocal)
    w.director.tg_chat_id = '7010'
    req = approval_service.create_request(db, w.cashier, action_type='refund', branch_id=w.bs.id, amount=10, payload={'a': 2})
    db.commit()
    cb, answers = _fake_callback(7010, f'appr:no:{req.id}')
    asyncio.run(bot_manager.handle_approval_callback(cb, w.ca.id))
    db.refresh(req)
    assert req.status == 'rejected' and 'Rad etildi' in answers[-1]


def test_callback_registered_in_dispatcher():
    from aiogram import Dispatcher
    from app.admin_tg_bot import bot_manager
    dp = Dispatcher()
    bot_manager.register_handlers(dp, 1)
    handlers = dp.callback_query.handlers
    assert len(handlers) >= 2          # rep: va appr:


# ── i18n kalitlari ────────────────────────────────────────────────────────────

def test_i18n_pending_file_has_same_keys_in_all_languages():
    path = os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T4.6.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    assert len(data['uz']) >= 20
    assert all(v.strip() for lang in data.values() for v in lang.values())
