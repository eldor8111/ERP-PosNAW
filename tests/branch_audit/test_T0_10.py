"""T0.10 — Eski /orders endpointlarida (pending/confirm/delete) korxona va rol tekshiruvi."""
import itertools

import pytest

from app.models.customer import Customer
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.user import UserRole

_n = itertools.count(1)


def _order(db, company, branch, name_suffix=''):
    n = next(_n)
    cust = Customer(name=f'Mijoz{name_suffix}{n}', phone=f'9019{n:07d}', company_id=company.id, branch_id=branch.id)
    prod = Product(company_id=company.id, sku=f'SKU{n}', barcode=f'BC{n:08d}', name=f'Mahsulot{name_suffix}{n}',
                   sale_price=1000)
    db.add_all([cust, prod])
    db.flush()
    order = Order(customer_id=cust.id, branch_id=branch.id, product_id=prod.id, quantity=2,
                  unit_price=1000, total_amount=2000, status=OrderStatus.pending, payment_type='cash')
    db.add(order)
    db.flush()
    return cust, prod, order


@pytest.fixture
def two(db, mk):
    ca, ba, _, ua = mk.tenant()
    cb, bb, _, ub = mk.tenant()
    return {
        'a': (ca, ba, ua) + _order(db, ca, ba, 'A'),
        'b': (cb, bb, ub) + _order(db, cb, bb, 'B'),
    }


def test_pending_boshqa_korxona_filiali_404(client, two):
    _, _, ua, *_ = two['a']
    _, bb, _, custb, _, _ = two['b']
    r = client.login(ua).get(f'/api/orders/branch/{bb.id}/pending')
    assert r.status_code == 404
    assert r.json()['detail'] == 'Filial topilmadi'
    assert custb.name not in r.text and custb.phone not in r.text


def test_pending_mavjud_bolmagan_filial_404(client, two):
    _, _, ua, *_ = two['a']
    assert client.login(ua).get('/api/orders/branch/999999/pending').status_code == 404


def test_pending_oz_filiali_200(client, two):
    ca, ba, ua, cust, prod, order = two['a']
    r = client.login(ua).get(f'/api/orders/branch/{ba.id}/pending')
    assert r.status_code == 200
    rows = r.json()
    assert [x['id'] for x in rows] == [order.id]
    row = rows[0]
    assert set(row) == {'id', 'customer_name', 'customer_phone', 'product_name', 'quantity', 'unit_price',
                        'total_amount', 'payment_type', 'status', 'created_at', 'notes'}
    assert row['customer_name'] == cust.name and row['product_name'] == prod.name


def test_pending_begona_mahsulot_nomi_chiqmaydi(client, db, two):
    """A buyurtmasi B korxonasining mahsulotiga ulangan bo'lsa ham nomi A ga chiqmaydi."""
    ca, ba, ua, cust, prod, order = two['a']
    _, _, _, _, prod_b, _ = two['b']
    order.product_id = prod_b.id
    db.flush()
    r = client.login(ua).get(f'/api/orders/branch/{ba.id}/pending')
    assert r.status_code == 200
    assert prod_b.name not in r.text
    assert r.json()[0]['product_name'] == '—'


def test_pending_begona_mijoz_buyurtmasi_korinmaydi(client, db, two):
    """A filialidagi buyurtma B korxonasi mijoziga tegishli bo'lsa ham ko'rinmaydi."""
    ca, ba, ua, cust, prod, order = two['a']
    _, _, _, custb, _, _ = two['b']
    order.customer_id = custb.id
    db.flush()
    r = client.login(ua).get(f'/api/orders/branch/{ba.id}/pending')
    assert r.status_code == 200
    assert r.json() == []
    assert custb.name not in r.text


def test_confirm_begona_buyurtma_404_status_ozgarmaydi(client, db, two):
    _, _, ua, *_ = two['a']
    _, _, _, _, _, order_b = two['b']
    r = client.login(ua).put(f'/api/orders/{order_b.id}/confirm')
    assert r.status_code == 404
    assert r.json()['detail'] == 'Buyurtma topilmadi'
    db.refresh(order_b)
    assert order_b.status == OrderStatus.pending


def test_confirm_begona_buyurtma_bekor_statusi_bilan_ham_404(client, db, two):
    _, _, ua, *_ = two['a']
    _, _, _, _, _, order_b = two['b']
    r = client.login(ua).put(f'/api/orders/{order_b.id}/confirm', json={'status': 'cancelled'})
    assert r.status_code == 404
    db.refresh(order_b)
    assert order_b.status == OrderStatus.pending


def test_delete_begona_buyurtma_404_status_ozgarmaydi(client, db, two):
    _, _, ua, *_ = two['a']
    _, _, _, _, _, order_b = two['b']
    r = client.login(ua).delete(f'/api/orders/{order_b.id}')
    assert r.status_code == 404
    assert r.json()['detail'] == 'Buyurtma topilmadi'
    db.refresh(order_b)
    assert order_b.status == OrderStatus.pending


def test_confirm_oz_buyurtmasi_200(client, db, two):
    _, _, ua, _, _, order = two['a']
    r = client.login(ua).put(f'/api/orders/{order.id}/confirm')
    assert r.status_code == 200
    assert r.json()['message'] == 'Buyurtma yangilandi'
    db.refresh(order)
    assert order.status == OrderStatus.confirmed and order.confirmed_at is not None


def test_delete_oz_buyurtmasi_200(client, db, two):
    _, _, ua, _, _, order = two['a']
    r = client.login(ua).delete(f'/api/orders/{order.id}')
    assert r.status_code == 200
    assert r.json()['message'] == 'Buyurtma bekor qilindi'
    db.refresh(order)
    assert order.status == OrderStatus.cancelled


@pytest.mark.parametrize('role', [UserRole.courier, UserRole.agent, UserRole.marketplace_agent])
def test_mobil_rollar_uchala_endpointdan_403(client, db, mk, two, role):
    ca, ba, _, _, _, order = two['a']
    u = mk.user(ca, role=role, branch=ba)
    c = client.login(u)
    assert c.get(f'/api/orders/branch/{ba.id}/pending').status_code == 403
    assert c.put(f'/api/orders/{order.id}/confirm').status_code == 403
    assert c.delete(f'/api/orders/{order.id}').status_code == 403
    db.refresh(order)
    assert order.status == OrderStatus.pending


@pytest.mark.parametrize('role', [UserRole.admin, UserRole.director, UserRole.manager, UserRole.cashier])
def test_dokon_rollari_pending_200(client, mk, two, role):
    ca, ba, _, *_ = two['a']
    u = mk.user(ca, role=role, branch=ba)
    assert client.login(u).get(f'/api/orders/branch/{ba.id}/pending').status_code == 200
