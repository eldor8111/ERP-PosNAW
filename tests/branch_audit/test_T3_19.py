"""T3.19 — Aksiyalar (qamrov, rol, validatsiya) va mijozning individual narxi / chegirmasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_19.py -q -p no:cacheprovider
"""
import itertools
import json
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.customer import Customer
from app.models.customer_prices import CustomerPrice
from app.models.product import Product
from app.models.promotion import Promotion, PromotionProduct
from app.models.sale import SaleItem
from app.models.user import UserRole
from app.schemas.promotion import PromotionCreate, PromotionUpdate
from app.schemas.sale import SaleItemCreate
from app.services.sale_helpers import resolve_item_pricing

_seq = itertools.count(1)
P = '/api/promotions/'


def _product(db, company, price='7500', **kw):
    n = next(_seq)
    p = Product(name=kw.pop('name', f'Tovar {n}'), sku=f'T319-{n}', barcode=f'B319-{n}', company_id=company.id,
                sale_price=Decimal(price), **kw)
    db.add(p)
    db.flush()
    return p


def _customer(db, company, **kw):
    n = next(_seq)
    c = Customer(name=f'Mijoz {n}', company_id=company.id, phone=f'99893{n:07d}',
                 debt_balance=Decimal('0'), debt_balances={}, **kw)
    db.add(c)
    db.flush()
    return c


def _cprice(db, company, customer, product, price):
    cp = CustomerPrice(company_id=company.id, customer_id=customer.id, product_id=product.id, price=Decimal(price))
    db.add(cp)
    db.flush()
    return cp


def _item(**kw):
    kw.setdefault('product_id', 1)
    kw.setdefault('quantity', Decimal('1'))
    return SaleItemCreate(**kw)


@pytest.fixture
def world(db, mk):
    ca, ba, wa, admin = mk.tenant(UserRole.admin)
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba)
    manager = mk.user(ca, role=UserRole.manager, branch=ba)
    storekeeper = mk.user(ca, role=UserRole.warehouse, branch=ba)
    cb, bb, wb, admin_b = mk.tenant(UserRole.admin)
    return SimpleNamespace(ca=ca, ba=ba, wa=wa, admin=admin, cashier=cashier, manager=manager,
                           storekeeper=storekeeper, cb=cb, admin_b=admin_b)


# ── Aksiya sxemasi (2, 3-mezonlar) ────────────────────────────────────────────

def test_schema_percent_over_100_rejected():
    with pytest.raises(ValidationError):
        PromotionCreate(name='x', discount_type='percent', discount_value=Decimal('150'))
    with pytest.raises(ValidationError):
        PromotionCreate(name='x', discount_type='percent', discount_value=Decimal('0'))
    ok = PromotionCreate(name='x', discount_type='percent', discount_value=Decimal('100'))
    assert ok.applies_to == 'all'


def test_schema_amount_and_type_literal():
    assert PromotionCreate(name='x', discount_type='amount', discount_value=Decimal('5000000')).discount_value
    with pytest.raises(ValidationError):
        PromotionCreate(name='x', discount_type='amount', discount_value=Decimal('-1'))
    with pytest.raises(ValidationError):
        PromotionCreate(name='x', discount_type='bepul', discount_value=Decimal('5'))


def test_schema_dates_and_applies_to():
    with pytest.raises(ValidationError):
        PromotionCreate(name='x', discount_value=Decimal('5'),
                        start_date='2026-02-10T00:00:00', end_date='2026-02-01T00:00:00')
    p = PromotionCreate(name='x', discount_value=Decimal('5'), products=[{'product_id': 3}])
    assert p.applies_to == 'products'                      # berilmasa: products bo'sh emas -> products
    with pytest.raises(ValidationError):
        PromotionCreate(name='x', discount_value=Decimal('5'), applies_to='products', products=[])
    with pytest.raises(ValidationError):
        PromotionUpdate(applies_to='products', products=[])
    assert PromotionUpdate(end_date=None).model_fields_set == {'end_date'}


# ── Aksiya router (3, 1, 2-mezonlar) ──────────────────────────────────────────

def test_cashier_and_storekeeper_cannot_write_promotions(client, db, world):
    w = world
    body = {'name': 'Bepul', 'discount_type': 'amount', 'discount_value': 100}
    assert client.login(w.cashier).post(P, json=body).status_code == 403
    assert client.login(w.storekeeper).post(P, json=body).status_code == 403
    promo = Promotion(company_id=w.ca.id, name='A', discount_value=Decimal('5'))
    db.add(promo)
    db.flush()
    assert client.login(w.cashier).put(f'{P}{promo.id}', json={'name': 'B'}).status_code == 403
    assert client.login(w.cashier).delete(f'{P}{promo.id}').status_code == 403
    assert db.query(Promotion).filter(Promotion.id == promo.id).first() is not None
    # kassir o'qiy oladi (Ulgurji uchun)
    r = client.login(w.cashier).get(P)
    assert r.status_code == 200 and len(r.json()) == 1


def test_percent_150_returns_422(client, world):
    r = client.login(world.admin).post(P, json={'name': 'X', 'discount_type': 'percent', 'discount_value': 150})
    assert r.status_code == 422


def test_create_with_products_and_names(client, db, world):
    w = world
    p1, p2 = _product(db, w.ca, name='Shokolad'), _product(db, w.ca, name='Un')
    r = client.login(w.manager).post(P, json={
        'name': 'Shokolad 10%', 'discount_type': 'percent', 'discount_value': 10,
        'start_date': None, 'end_date': None, 'applies_to': 'products',
        'products': [{'product_id': p1.id}, {'product_id': p2.id}]})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d['applies_to'] == 'products' and len(d['products']) == 2
    assert {x['product_name'] for x in d['products']} == {'Shokolad', 'Un'}
    assert d['start_date'] is None
    lst = client.login(w.cashier).get(P).json()
    assert lst[0]['applies_to'] == 'products' and len(lst[0]['products']) == 2


def test_create_all_scope_without_products(client, world):
    r = client.login(world.admin).post(P, json={'name': 'Hammasi', 'discount_value': 5, 'applies_to': 'all'})
    assert r.status_code == 201, r.text
    assert r.json()['applies_to'] == 'all' and r.json()['products'] == []


def test_products_scope_empty_is_422(client, world):
    r = client.login(world.admin).post(P, json={'name': 'X', 'discount_value': 5, 'applies_to': 'products',
                                                 'products': []})
    assert r.status_code == 422


def test_foreign_or_deleted_product_is_400_and_nothing_created(client, db, world):
    w = world
    foreign = _product(db, w.cb)
    deleted = _product(db, w.ca, is_deleted=True)
    for pid in (foreign.id, deleted.id, 99999999):
        r = client.login(w.admin).post(P, json={'name': 'X', 'discount_value': 5, 'products': [{'product_id': pid}]})
        assert r.status_code == 400, r.text
        assert 'topilmadi' in r.text
    assert db.query(Promotion).count() == 0
    own = _product(db, w.ca)
    promo = client.login(w.admin).post(P, json={'name': 'X', 'discount_value': 5,
                                                 'products': [{'product_id': own.id}]}).json()
    r = client.login(w.admin).put(f"{P}{promo['id']}", json={'products': [{'product_id': foreign.id}]})
    assert r.status_code == 400
    assert db.query(PromotionProduct).filter(PromotionProduct.promotion_id == promo['id']).count() == 1


def test_update_clears_dates_and_scope(client, db, world):
    w = world
    own = _product(db, w.ca)
    cl = client.login(w.admin)
    promo = cl.post(P, json={'name': 'X', 'discount_value': 5, 'start_date': '2026-01-01T00:00:00',
                             'end_date': '2026-02-01T23:59:59', 'products': [{'product_id': own.id}]}).json()
    assert promo['start_date'] and promo['end_date']
    r = cl.put(f"{P}{promo['id']}", json={'start_date': None, 'end_date': None})
    assert r.status_code == 200, r.text
    assert r.json()['start_date'] is None and r.json()['end_date'] is None
    assert len(r.json()['products']) == 1                      # qamrov o'zgarmadi
    r = cl.put(f"{P}{promo['id']}", json={'applies_to': 'all'})
    assert r.status_code == 200 and r.json()['applies_to'] == 'all' and r.json()['products'] == []
    assert cl.put(f"{P}{promo['id']}", json={'applies_to': 'products'}).status_code == 422
    assert cl.put(f"{P}{promo['id']}", json={'discount_value': 150}).status_code == 422


def test_other_company_cannot_touch_promotion(client, db, world):
    w = world
    promo = Promotion(company_id=w.ca.id, name='A', discount_value=Decimal('5'))
    db.add(promo)
    db.flush()
    cl = client.login(w.admin_b)
    assert cl.get(f'{P}{promo.id}').status_code == 404
    assert cl.put(f'{P}{promo.id}', json={'name': 'Z'}).status_code == 404
    assert cl.delete(f'{P}{promo.id}').status_code == 404
    assert cl.get(P).json() == []


def test_model_applies_to_default(db, world):
    promo = Promotion(company_id=world.ca.id, name='A', discount_value=Decimal('5'))
    db.add(promo)
    db.flush()
    assert promo.applies_to == 'all'


# ── resolve_item_pricing (5, 6-mezonlar) ──────────────────────────────────────

def test_pricing_old_client_gets_customer_price(db, world):
    w = world
    prod = _product(db, w.ca, price='7500')
    cust = _customer(db, w.ca)
    cp = _cprice(db, w.ca, cust, prod, '6500')
    u, d, src = resolve_item_pricing(_item(unit_price=Decimal('7500')), prod, cp, cust, w.cashier)
    assert (u, d, src) == (Decimal('6500'), Decimal('0'), 'customer_price')
    assert resolve_item_pricing(_item(), prod, cp, cust, w.cashier)[0] == Decimal('6500')
    u, _, src = resolve_item_pricing(_item(unit_price=Decimal('6000'), price_manual=True), prod, cp, cust, w.cashier)
    assert u == Decimal('6000') and src == 'manual'
    assert resolve_item_pricing(_item(unit_price=Decimal('6000'), price_manual=False), prod, cp, cust)[0] == Decimal('6500')
    assert resolve_item_pricing(_item(unit_price=Decimal('6000')), prod, cp, cust)[0] == Decimal('6000')


def test_pricing_currency_mismatch_not_treated_as_list_price(db, world):
    w = world
    prod = _product(db, w.ca, price='7500')
    cust = _customer(db, w.ca)
    cp = _cprice(db, w.ca, cust, prod, '6500')
    u, _, src = resolve_item_pricing(_item(unit_price=Decimal('7500'), currency_code='USD'), prod, cp, cust)
    assert u == Decimal('7500') and src == 'manual'


def test_pricing_price_type_and_no_customer(db, world):
    w = world
    prod = _product(db, w.ca, price='7500', wholesale_price=Decimal('7000'), cost_price=Decimal('5000'))
    whole = _customer(db, w.ca, price_type='wholesale')
    cost = _customer(db, w.ca, price_type='cost')
    plain = _customer(db, w.ca, price_type='sale')
    assert resolve_item_pricing(_item(), prod, None, whole)[0] == Decimal('7000')
    assert resolve_item_pricing(_item(), prod, None, cost)[0] == Decimal('5000')
    assert resolve_item_pricing(_item(), prod, None, plain)[0] == Decimal('7500')
    assert resolve_item_pricing(_item(), prod, None, None)[0] == Decimal('7500')
    assert resolve_item_pricing(_item(unit_price=Decimal('7500')), prod, None, whole)[0] == Decimal('7500')


def test_pricing_change_price_permission(db, world):
    w = world
    prod = _product(db, w.ca, price='7500')
    w.cashier.permissions = {'sales': {'change_price': False}}
    with pytest.raises(HTTPException) as e:
        resolve_item_pricing(_item(unit_price=Decimal('6000'), price_manual=True), prod, None, None, w.cashier)
    assert e.value.status_code == 403
    w.cashier.permissions = {}
    assert resolve_item_pricing(_item(unit_price=Decimal('6000'), price_manual=True), prod, None, None, w.cashier)[0] == Decimal('6000')
    w.cashier.permissions = None
    assert resolve_item_pricing(_item(unit_price=Decimal('6000'), price_manual=True), prod, None, None, w.cashier)[0] == Decimal('6000')


def test_pricing_discount_percent_rules(db, world):
    w = world
    prod = _product(db, w.ca, price='7500')
    cust = _customer(db, w.ca, discount_percent=Decimal('5'))
    u, d, _ = resolve_item_pricing(_item(unit_price=Decimal('7500'), quantity=Decimal('3')), prod, None, cust)
    assert u == Decimal('7500') and d == Decimal('1125.00')       # 22500 * 5%
    _, d, _ = resolve_item_pricing(_item(unit_price=Decimal('7500'), discount=Decimal('100')), prod, None, cust)
    assert d == Decimal('100')
    zero = _customer(db, w.ca, discount_percent=Decimal('0'))
    assert resolve_item_pricing(_item(), prod, None, zero)[1] == Decimal('0')
    assert resolve_item_pricing(_item(), prod, None, None)[1] == Decimal('0')


# ── Sotuv endpointi orqali (5, 6-mezonlar) ────────────────────────────────────

def _pending_body(w, prod, cust, **item):
    it = {'product_id': prod.id, 'quantity': 2}
    it.update(item)
    return {'items': [it], 'payment_type': 'debt', 'paid_amount': 0, 'customer_id': cust.id,
            'warehouse_id': w.wa.id}


def test_pending_sale_applies_customer_price_and_discount(client, db, world):
    w = world
    prod = _product(db, w.ca, price='7500')
    cust = _customer(db, w.ca, discount_percent=Decimal('5'))
    _cprice(db, w.ca, cust, prod, '6500')
    cl = client.login(w.cashier)
    r = cl.post('/api/sales/pending', json=_pending_body(w, prod, cust, unit_price=7500))
    assert r.status_code == 200, r.text
    it = db.query(SaleItem).filter(SaleItem.sale_id == r.json()['id']).one()
    assert Decimal(str(it.unit_price)) == Decimal('6500')
    assert Decimal(str(it.discount)) == Decimal('650.00')        # 13000 * 5%
    assert Decimal(str(it.subtotal)) == Decimal('12350.00')
    r = cl.post('/api/sales/pending', json=_pending_body(w, prod, cust, unit_price=6000, price_manual=True, discount=100))
    assert r.status_code == 200, r.text
    it = db.query(SaleItem).filter(SaleItem.sale_id == r.json()['id']).one()
    assert Decimal(str(it.unit_price)) == Decimal('6000') and Decimal(str(it.discount)) == Decimal('100')


def test_pending_sale_forbidden_manual_price(client, db, world):
    w = world
    prod = _product(db, w.ca, price='7500')
    cust = _customer(db, w.ca)
    w.cashier.permissions = {'sales': {'change_price': False}}
    db.flush()
    r = client.login(w.cashier).post('/api/sales/pending',
                                      json=_pending_body(w, prod, cust, unit_price=1, price_manual=True))
    assert r.status_code == 403, r.text
    r = client.login(w.cashier).post('/api/sales/pending', json=_pending_body(w, prod, cust))
    assert r.status_code == 200, r.text


# ── Mijoz narxlari endpointlari (7-mezon) ─────────────────────────────────────

def test_customer_price_post_foreign_product_404_and_role_403(client, db, world):
    w = world
    own = _product(db, w.ca, name='Coca-Cola 0.5', price='7500')
    foreign = _product(db, w.cb)
    cust = _customer(db, w.ca)
    url = f'/api/customers/{cust.id}/prices'
    cl = client.login(w.admin)
    assert cl.post(url, json={'product_id': foreign.id, 'price': 100}).status_code == 404
    assert db.query(CustomerPrice).count() == 0
    assert client.login(w.cashier).post(url, json={'product_id': own.id, 'price': 6500}).status_code == 403
    assert client.login(w.cashier).delete(f'{url}/{own.id}').status_code == 403
    cl = client.login(w.admin)
    assert cl.post(url, json={'product_id': own.id, 'price': 0}).status_code == 422
    assert cl.post(url, json={'product_id': own.id, 'price': -5}).status_code == 422
    r = cl.post(url, json={'product_id': own.id, 'price': 6500})
    assert r.status_code == 201, r.text
    r = cl.post(url, json={'product_id': own.id, 'price': 6400})        # yangilash
    assert r.status_code == 201 and r.json()['price'] == 6400
    rows = client.login(w.cashier).get(url).json()                     # kassir o'qiydi
    cl = client.login(w.admin)
    assert rows == [{'id': rows[0]['id'], 'product_id': own.id, 'product_name': 'Coca-Cola 0.5',
                     'sku': own.sku, 'price': 6400.0, 'sale_price': 7500.0}]
    assert cl.delete(f'{url}/{own.id}').status_code == 204
    assert cl.get(url).json() == []


def test_customer_prices_foreign_customer_404(client, db, world):
    w = world
    own = _product(db, w.ca)
    cust_b = _customer(db, w.cb)
    cl = client.login(w.admin)
    assert cl.get(f'/api/customers/{cust_b.id}/prices').status_code == 404
    assert cl.post(f'/api/customers/{cust_b.id}/prices', json={'product_id': own.id, 'price': 5}).status_code == 404


def test_customer_price_type_retail_normalized(client, db, world):
    r = client.login(world.admin).post('/api/customers/', json={'name': 'Yangi', 'phone': '998901112233',
                                                                  'price_type': 'retail'})
    assert r.status_code in (200, 201), r.text
    assert r.json()['price_type'] == 'sale'


# ── Frontend: i18n kalitlari va UI mantiqi ────────────────────────────────────

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def test_pending_i18n_keys_in_all_languages():
    with open(os.path.join(ROOT, 'tests/branch_audit/i18n_pending/T3.19.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    for k in ('promotion.appliesAll', 'promotion.appliesProducts', 'promotion.pickProducts', 'customer.specialPrices'):
        assert k in data['uz']


def test_frontend_ulgurji_promo_logic_fixed():
    src = _read('frontend/src/pages/admin/UlgurjiSotuv.jsx')
    assert 'pp.id === productId' not in src
    assert "applies_to === 'all'" in src
    assert 'Math.min(disc' in src
    assert 'price_manual' in src


def test_frontend_promotions_form_has_scope_and_null_dates():
    src = _read('frontend/src/pages/admin/Promotions.jsx')
    assert 'applies_to' in src and 'T00:00:00' in src and ': null' in src


def test_frontend_customers_default_price_type_sale():
    src = _read('frontend/src/pages/admin/Customers.jsx')
    assert "price_type: 'retail'" not in src
    assert 'CustomerPricesSection' in src
    assert os.path.exists(os.path.join(ROOT, 'frontend/src/components/customer/CustomerPricesSection.jsx'))
