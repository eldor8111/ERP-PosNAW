"""T3.17 — Marketplace: tasdiqlash (ombor tanlash, PO, ledger), agent to'lovi (kassa), login roli, modul yopig'i.

Qamrov (qabul mezonlari 1-8): approve PO + Batch + qoldiq yaratadi; qarz ledger orqali qo'shiladi;
xatoda hammasi orqaga qaytadi (status review); ombor tanlash (404/403/409); payout Transaction +
KassaMovement + kassa balansi; role=agent loginda 403 va rol o'zgarmaydi; modul o'chiq korxona 403;
agent ilovasi uchun warehouse_name va /warehouses.
"""
import itertools
import json
import os
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models.batch import Batch
from app.models.inventory import StockLevel
from app.models.marketplace import (
    MarketplaceAgentTransaction, MarketplaceProduct, MarketplaceProductStatus, MarketplaceTransactionType,
)
from app.models.moliya import KassaMovement, Transaction, Wallet
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, POStatus
from app.models.supplier import Supplier
from app.models.user import User, UserRole, UserStatus
from app.services import marketplace_service as mp

_seq = itertools.count(1)
A = '/api/marketplace-agents'


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Mir-maza (tashqi) chaqiruvlari testda ishlamasin."""
    monkeypatch.setattr(mp, 'push_product_to_mirmaza', lambda *a, **k: True)
    monkeypatch.setattr(mp, 'category_name_map', lambda: {1: 'Kategoriya'})


def _enable(db, company):
    company.marketplace_agents_enabled = True
    db.flush()


def _agent(db, mk, company, **kw):
    return mk.user(company, role=UserRole.marketplace_agent, **kw)


def _mp_product(db, company, agent, qty=10, price=500, status=MarketplaceProductStatus.review, **kw):
    n = next(_seq)
    p = MarketplaceProduct(
        company_id=company.id, agent_id=agent.id, name=kw.pop('name', f'Agent tovari {n}'),
        price=Decimal(price), qty=Decimal(qty), category_id=1, barcode=kw.pop('barcode', f'MPBC{n:06d}'),
        status=status, **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product_id, warehouse_id):
    sl = db.query(StockLevel).filter(
        StockLevel.product_id == product_id, StockLevel.warehouse_id == warehouse_id).first()
    return Decimal(str(sl.quantity)) if sl else Decimal(0)


def _setup(db, mk):
    """Yoqilgan modulli korxona: admin, ombor, faol agent."""
    c, b, w, admin = mk.tenant()
    _enable(db, c)
    agent = _agent(db, mk, c)
    return c, b, w, admin, agent


# ─── 1. approve PO + ombor + Batch yaratadi ───

def test_approve_creates_po_stock_and_batch(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    p = _mp_product(db, c, agent, qty=10, price=500)
    r = client.login(admin).post(f'{A}/products/{p.id}/approve', json={'warehouse_id': w.id})
    assert r.status_code == 200, r.text
    assert r.json()['status'] == 'approved'
    db.refresh(p)
    assert p.status == MarketplaceProductStatus.approved
    assert p.warehouse_id == w.id and p.purchase_order_id
    po = db.get(PurchaseOrder, p.purchase_order_id)
    assert po.status == POStatus.received and po.warehouse_id == w.id
    assert po.number.startswith('PO') and 'PO-AG-' not in po.number
    prod = db.query(Product).filter(Product.company_id == c.id, Product.barcode == p.barcode).one()
    assert _stock(db, prod.id, w.id) == Decimal(10)
    batch = db.query(Batch).filter(Batch.po_id == po.id).one()
    assert batch.warehouse_id == w.id and Decimal(str(batch.quantity)) == Decimal(10)


def test_approve_without_body_uses_default_warehouse(db, mk, client):
    """Tanasiz chaqiruv ishlaydi: filialning standart (main/shop) ombori tanlanadi."""
    c, b, w, admin, agent = _setup(db, mk)
    other = mk.warehouse(c, b, name='Boshqa', type='transit')
    p = _mp_product(db, c, agent)
    r = client.login(admin).post(f'{A}/products/{p.id}/approve')
    assert r.status_code == 200, r.text
    db.refresh(p)
    assert p.warehouse_id == w.id != other.id
    assert r.json()['warehouse_name'] == w.name


def test_preferred_warehouse_is_used_when_no_explicit(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    w2 = mk.warehouse(c, b, name='Agent ombori')
    p = _mp_product(db, c, agent, preferred_warehouse_id=w2.id)
    r = client.login(admin).post(f'{A}/products/{p.id}/approve', json={})
    assert r.status_code == 200, r.text
    db.refresh(p)
    assert p.warehouse_id == w2.id


# ─── 2. ta'minotchi qarzi ledger orqali ───

def test_supplier_debt_goes_through_ledger(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    sup = Supplier(company_id=c.id, name='Agent: eski', phone=agent.phone, is_active=True,
                   debt_balances={'UZS': 2000000}, debt_balance=Decimal(2000000))
    db.add(sup)
    db.flush()
    p = _mp_product(db, c, agent, qty=10, price=500000)  # 5 000 000
    r = client.login(admin).post(f'{A}/products/{p.id}/approve', json={'warehouse_id': w.id})
    assert r.status_code == 200, r.text
    db.refresh(sup)
    assert Decimal(str(sup.debt_balances['UZS'])) == Decimal(7000000)
    assert Decimal(str(sup.debt_balance)) == Decimal(7000000)
    # keyingi ledger amali qarzni yo'qotmaydi
    from app.services import supplier_ledger as ledger
    ledger.add(db, sup, 'UZS', 0)
    ledger.apply_payment(db, sup, 1000000, 'UZS')
    assert Decimal(str(sup.debt_balance)) == Decimal(6000000)


# ─── 3. xatoda orqaga qaytadi ───

def test_failure_rolls_back_everything(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    # shu shtrix-kodli mahsulot 'sell' turida — kirim qilib bo'lmaydi (400)
    existing = Product(name='Tarkibiy', sku='SELL-1', barcode='SELLBC1', company_id=c.id,
                       cost_price=1, sale_price=2, product_type='sell')
    db.add(existing)
    db.flush()
    p = _mp_product(db, c, agent, qty=5, price=100, barcode='SELLBC1')
    n_po = db.query(PurchaseOrder).count()
    r = client.login(admin).post(f'{A}/products/{p.id}/approve', json={'warehouse_id': w.id})
    assert r.status_code == 400, r.text
    db.refresh(p)
    assert p.status == MarketplaceProductStatus.review
    assert p.purchase_order_id is None and p.warehouse_id is None
    assert db.query(PurchaseOrder).count() == n_po
    assert _stock(db, existing.id, w.id) == 0
    # savepoint ichida yaratilgan ta'minotchi ham qaytadi
    assert db.query(Supplier).filter(Supplier.company_id == c.id, Supplier.phone == agent.phone).count() == 0


def test_approve_wrong_status_409_and_inactive_agent_409(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    done = _mp_product(db, c, agent, status=MarketplaceProductStatus.approved)
    assert client.login(admin).post(f'{A}/products/{done.id}/approve').status_code == 409
    blocked = _agent(db, mk, c, status=UserStatus.blocked)
    p = _mp_product(db, c, blocked)
    assert client.login(admin).post(f'{A}/products/{p.id}/approve').status_code == 409


# ─── 4. ombor tanlash qoidalari ───

def test_other_company_warehouse_404(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    c2, b2, w2, _admin2 = mk.tenant()
    p = _mp_product(db, c, agent)
    r = client.login(admin).post(f'{A}/products/{p.id}/approve', json={'warehouse_id': w2.id})
    assert r.status_code == 404
    db.refresh(p)
    assert p.status == MarketplaceProductStatus.review


def test_other_company_product_404(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    c2, b2, w2, admin2 = mk.tenant()
    _enable(db, c2)
    p = _mp_product(db, c, agent)
    assert client.login(admin2).post(f'{A}/products/{p.id}/approve').status_code == 404


def test_manager_cannot_pick_other_branch_warehouse(db, mk, client):
    c, b, w, _admin, agent = _setup(db, mk)
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    manager = mk.user(c, role=UserRole.manager, branch=b)
    p = _mp_product(db, c, agent)
    r = client.login(manager).post(f'{A}/products/{p.id}/approve', json={'warehouse_id': w2.id})
    assert r.status_code == 403, r.text
    ok = client.login(manager).post(f'{A}/products/{p.id}/approve', json={'warehouse_id': w.id})
    assert ok.status_code == 200, ok.text


def test_no_warehouse_available_409(db, mk, client):
    c = mk.company()
    _enable(db, c)
    admin = mk.user(c)
    agent = _agent(db, mk, c)
    p = _mp_product(db, c, agent, qty=3)
    r = client.login(admin).post(f'{A}/products/{p.id}/approve')
    assert r.status_code == 409
    assert 'ombor' in r.json()['detail'].lower()
    db.refresh(p)
    assert p.status == MarketplaceProductStatus.review


def test_approve_without_receive_stock_skips_po(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    p = _mp_product(db, c, agent)
    r = client.login(admin).post(f'{A}/products/{p.id}/approve', json={'receive_stock': False})
    assert r.status_code == 200, r.text
    db.refresh(p)
    assert p.status == MarketplaceProductStatus.approved and p.purchase_order_id is None


def test_receive_endpoint_for_unreceived_approved(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    p = _mp_product(db, c, agent, status=MarketplaceProductStatus.approved, qty=4, price=100)
    r = client.login(admin).post(f'{A}/products/{p.id}/receive', json={'warehouse_id': w.id})
    assert r.status_code == 200, r.text
    db.refresh(p)
    assert p.purchase_order_id and p.warehouse_id == w.id
    prod = db.query(Product).filter(Product.company_id == c.id, Product.barcode == p.barcode).one()
    assert _stock(db, prod.id, w.id) == Decimal(4)
    # ikkinchi marta — 409
    assert client.login(admin).post(f'{A}/products/{p.id}/receive', json={'warehouse_id': w.id}).status_code == 409
    # begona korxona ombori — 404
    c2, b2, w2, _ = mk.tenant()
    q = _mp_product(db, c, agent, status=MarketplaceProductStatus.approved)
    assert client.login(admin).post(f'{A}/products/{q.id}/receive', json={'warehouse_id': w2.id}).status_code == 404


# ─── 5. payout: kassa, tranzaksiya, filial ───

def _income(db, c, agent, amount):
    db.add(MarketplaceAgentTransaction(
        agent_id=agent.id, company_id=c.id, transaction_type=MarketplaceTransactionType.income,
        amount=Decimal(amount)))
    db.flush()


def _wallet(db, c, b, balance):
    w = Wallet(name='Kassa', company_id=c.id, branch_id=b.id, balance=Decimal(balance), is_active=True)
    db.add(w)
    db.flush()
    return w


def test_payout_records_cash_transaction(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    _income(db, c, agent, 3000000)
    wallet = _wallet(db, c, b, 5000000)
    r = client.login(admin).post(f'{A}/{agent.id}/payouts', json={
        'amount': 3000000, 'wallet_id': wallet.id, 'payment_type': 'cash', 'note': 'oylik'})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body['wallet_id'] == wallet.id and body['balance'] == 0
    db.refresh(wallet)
    assert Decimal(str(wallet.balance)) == Decimal(2000000)
    t = db.get(MarketplaceAgentTransaction, body['id'])
    assert t.wallet_id == wallet.id and t.branch_id == b.id and t.finance_transaction_id
    tx = db.get(Transaction, t.finance_transaction_id)
    assert tx.type == 'expense' and tx.reference_type == 'marketplace_payout' and tx.reference_id == t.id
    assert tx.branch_id == b.id and tx.wallet_id == wallet.id
    mv = db.query(KassaMovement).filter(
        KassaMovement.reference_type == 'marketplace_payout', KassaMovement.reference_id == t.id).one()
    assert mv.direction == 'out' and Decimal(str(mv.amount)) == Decimal(3000000)


def test_payout_insufficient_cash_400(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    _income(db, c, agent, 3000000)
    wallet = _wallet(db, c, b, 1000)
    r = client.login(admin).post(f'{A}/{agent.id}/payouts', json={'amount': 3000000, 'wallet_id': wallet.id})
    assert r.status_code == 400
    assert 'Kassada' in r.json()['detail']
    db.refresh(wallet)
    assert Decimal(str(wallet.balance)) == Decimal(1000)
    assert db.query(MarketplaceAgentTransaction).filter(
        MarketplaceAgentTransaction.transaction_type == MarketplaceTransactionType.payout).count() == 0


def test_payout_wallet_required_other_company_wallet_and_role(db, mk, client):
    c, b, w, admin, agent = _setup(db, mk)
    _income(db, c, agent, 1000)
    c2, b2, w2, _ = mk.tenant()
    foreign = _wallet(db, c2, b2, 100000)
    assert client.login(admin).post(f'{A}/{agent.id}/payouts', json={'amount': 100}).status_code == 422
    assert client.login(admin).post(
        f'{A}/{agent.id}/payouts', json={'amount': 100, 'wallet_id': foreign.id}).status_code == 404
    manager = mk.user(c, role=UserRole.manager, branch=b)
    own = _wallet(db, c, b, 100000)
    assert client.login(manager).post(
        f'{A}/{agent.id}/payouts', json={'amount': 100, 'wallet_id': own.id}).status_code == 403
    # boshqa korxona agenti — 404
    c3, b3, w3, admin3 = mk.tenant()
    _enable(db, c3)
    assert client.login(admin3).post(
        f'{A}/{agent.id}/payouts', json={'amount': 100, 'wallet_id': own.id}).status_code == 404


# ─── 6. login: dala agenti roli o'zgarmaydi ───

def _login_body(phone, password='parol123'):
    return {'phone': phone, 'password': password, 'device_id': 'device-12345678'}


def test_login_field_agent_gets_403_and_role_unchanged(db, mk, client):
    c, b, w, admin = mk.tenant()
    _enable(db, c)
    field = mk.user(c, role=UserRole.agent, hashed_password=hash_password('parol123'))
    r = client.post('/api/mobile/marketplace/auth/login', json=_login_body(field.phone))
    assert r.status_code == 403, r.text
    assert 'marketplace agentlari uchun' in r.json()['detail']
    db.expire_all()
    assert db.get(User, field.id).role == UserRole.agent
    # noto'g'ri parol — 401 (xabar o'zgarishsiz)
    r2 = client.post('/api/mobile/marketplace/auth/login', json=_login_body(field.phone, 'xato-parol'))
    assert r2.status_code == 401


def test_login_marketplace_agent_ok(db, mk, client):
    c, b, w, admin = mk.tenant()
    _enable(db, c)
    ag = _agent(db, mk, c, hashed_password=hash_password('parol123'))
    r = client.post('/api/mobile/marketplace/auth/login', json=_login_body(ag.phone))
    assert r.status_code == 200, r.text
    assert r.json()['user']['id'] == ag.id


# ─── 7. modul o'chiq korxona ───

def test_feature_gate_blocks_whole_router(db, mk, client):
    c, b, w, admin = mk.tenant()          # marketplace_agents_enabled = False
    cl = client.login(admin)
    for path in ('', '/products', '/stats/summary'):
        r = cl.get(A + path)
        assert r.status_code == 403, (path, r.text)
        assert 'yoqilmagan' in r.json()['detail']
    assert cl.post(f'{A}/products/1/approve').status_code == 403
    _enable(db, c)
    assert cl.get(A).status_code == 200


# ─── 8. agent ilovasi: warehouse_name va /warehouses ───

def test_agent_sees_warehouse_name_and_warehouse_list(db, mk, client):
    c, b, w, admin = mk.tenant()
    _enable(db, c)
    ag = _agent(db, mk, c, hashed_password=hash_password('parol123'))
    tok = client.post('/api/mobile/marketplace/auth/login', json=_login_body(ag.phone)).json()['access_token']
    h = {'Authorization': f'Bearer {tok}'}
    # bitta filial — ro'yxat bo'sh
    assert client.get('/api/mobile/marketplace/warehouses', headers=h).json() == []
    b2 = mk.branch(c, name='Samarqand')
    w2 = mk.warehouse(c, b2, name='Samarqand ombori')
    lst = client.get('/api/mobile/marketplace/warehouses', headers=h).json()
    assert {x['id'] for x in lst} == {w.id, w2.id}
    assert next(x for x in lst if x['id'] == w2.id)['branch_name'] == 'Samarqand'

    # begona korxona omborini tanlab bo'lmaydi
    c2, b3, w3, _ = mk.tenant()
    base = {'name': 'Tovar', 'price': 100, 'qty': 2, 'category_id': 1}
    from app.models.marketplace import MarketplaceAgentCategory
    db.add(MarketplaceAgentCategory(user_id=ag.id, category_id=1, company_id=c.id))
    db.flush()
    bad = client.post('/api/mobile/marketplace/products', headers=h, json={**base, 'preferred_warehouse_id': w3.id})
    assert bad.status_code == 404
    ok = client.post('/api/mobile/marketplace/products', headers=h, json={**base, 'preferred_warehouse_id': w2.id})
    assert ok.status_code == 201, ok.text
    pid = ok.json()['id']
    assert ok.json()['preferred_warehouse_id'] == w2.id

    # admin tasdiqlaydi (ombor ko'rsatmasdan) — agent tanlagan omborga tushadi
    r = client.login(admin).post(f'{A}/products/{pid}/approve')
    assert r.status_code == 200, r.text
    mine = client.get('/api/mobile/marketplace/products', headers=h).json()['items'][0]
    assert mine['warehouse_name'] == 'Samarqand ombori'


# ─── i18n pending fayli (frontend) ───

def test_pending_i18n_keys_consistent():
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'tests', 'branch_audit', 'i18n_pending', 'T3.17.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    assert len(data['uz']) >= 10
