"""T0.34 — Mahsulot tahriri va importi qoldiqni noto'g'ri ustidan yozmasligi.

Mezonlar: 1, 2, 4, 5, 6, 7 (+ korxona izolyatsiyasi).
"""
import sqlite3
from decimal import Decimal

from app.models.batch import Batch
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import UserRole

PUT_URL = '/api/products/{}'
IMPORT_URL = '/api/products/bulk-import'

# SQLite Integer ustuniga (products.min_stock) Decimal bog'lab bo'lmaydi — Postgres buni
# o'zi keltiradi. Faqat test muhiti uchun adapter.
sqlite3.register_adapter(Decimal, lambda d: int(d) if d == d.to_integral_value() else float(d))


def _product(db, company, name, sku=None, barcode=None, product_type='simple'):
    p = Product(
        name=name, sku=sku or f'SKU-{name}', barcode=barcode or f'BC-{name}',
        company_id=company.id, cost_price=Decimal('1000'), sale_price=Decimal('1500'),
        product_type=product_type, images='[]',
    )
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal(str(qty)))
    db.add(sl)
    db.flush()
    return sl


def _levels(db, product):
    """{warehouse_id: quantity} — mahsulotning barcha ombor qatorlari."""
    rows = db.query(StockLevel).filter(StockLevel.product_id == product.id).all()
    return {r.warehouse_id: Decimal(str(r.quantity)) for r in rows}


def _movements(db, product):
    return db.query(StockMovement).filter(StockMovement.product_id == product.id).all()


# ── 1-mezon: faqat narx o'zgarsa qoldiqlar o'zgarmaydi ───────────────────────
def test_put_price_only_keeps_per_warehouse_stock(db, mk, client):
    c, b, w1, u = mk.tenant()
    w2 = mk.warehouse(c, b, name='Yunusobod')
    cola = _product(db, c, 'Cola')
    _stock(db, cola, w1, 10)
    _stock(db, cola, w2, 5)

    r = client.login(u).put(PUT_URL.format(cola.id), json={'sale_price': 2000})
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()['stock_quantity'])) == Decimal('15')

    assert _levels(db, cola) == {w1.id: Decimal('10'), w2.id: Decimal('5')}
    assert _movements(db, cola) == []
    db.refresh(cola)
    assert cola.sale_price == Decimal('2000')


# ── 2-mezon: initial_stock yuborilsa ham e'tiborsiz, warehouse roli ham aylanib o'tolmaydi ──
def test_put_initial_stock_ignored_even_for_warehouse_role(db, mk, client):
    c, b, w1, admin = mk.tenant()
    w2 = mk.warehouse(c, b)
    wh_user = mk.user(c, role=UserRole.warehouse, branch=b)
    cola = _product(db, c, 'Cola')
    _stock(db, cola, w1, 10)
    _stock(db, cola, w2, 5)

    for user in (wh_user, admin):
        r = client.login(user).put(
            PUT_URL.format(cola.id),
            json={'initial_stock': 999, 'initial_warehouse_id': w1.id, 'name': 'Cola'},
        )
        assert r.status_code == 200, r.text  # 4xx emas — eski klientlar buzilmaydi
        assert _levels(db, cola) == {w1.id: Decimal('10'), w2.id: Decimal('5')}
        assert _movements(db, cola) == []

    # Qoldiq qatori yo'q mahsulot uchun ham yangi StockLevel yaratilmaydi
    bo_sh = _product(db, c, 'Bosh')
    r = client.login(admin).put(PUT_URL.format(bo_sh.id), json={'initial_stock': 50, 'initial_warehouse_id': w1.id})
    assert r.status_code == 200, r.text
    assert _levels(db, bo_sh) == {}


# ── Izolyatsiya: boshqa korxona mahsuloti PUT → 404 ──────────────────────────
def test_put_other_company_product_404(db, mk, client):
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    pb = _product(db, cb, 'B-tovar')
    _stock(db, pb, wb, 7)

    r = client.login(ua).put(PUT_URL.format(pb.id), json={'sale_price': 1, 'initial_stock': 999})
    assert r.status_code == 404
    assert _levels(db, pb) == {wb.id: Decimal('7')}


# ── 4-mezon: import tanlangan omborga yozadi, boshqa ombor o'zgarmaydi ───────
def test_import_existing_product_writes_to_selected_warehouse(db, mk, client):
    c, b, b1, u = mk.tenant()
    b2 = mk.warehouse(c, b, name='B2')
    p = _product(db, c, 'Tovar')
    _stock(db, p, b1, 40)

    r = client.login(u).post(
        f'{IMPORT_URL}?allow_update=true&warehouse_id={b2.id}',
        json=[{'Nomi': 'Tovar', 'Qoldiq': 100}],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['updated'] == 1 and body['created'] == 0, body
    assert body['warehouse_id'] == b2.id
    assert body['warehouse_name'] == 'B2'
    assert body['warnings'] == []

    assert _levels(db, p) == {b1.id: Decimal('40'), b2.id: Decimal('100')}
    mv = _movements(db, p)
    assert len(mv) == 1
    m = mv[0]
    assert m.type == MovementType.ADJUST
    assert m.warehouse_id == b2.id
    assert m.reference_type == 'product_import'
    assert Decimal(str(m.qty_before)) == Decimal('0')
    assert Decimal(str(m.qty_after)) == Decimal('100')
    assert Decimal(str(m.quantity)) == Decimal('100')
    assert m.user_id == u.id

    # Xuddi shu qoldiq qayta importda yangi harakat yozilmaydi (delta = 0)
    r = client.login(u).post(
        f'{IMPORT_URL}?allow_update=true&warehouse_id={b2.id}',
        json=[{'Nomi': 'Tovar', 'Qoldiq': 100}],
    )
    assert r.status_code == 200, r.text
    assert len(_movements(db, p)) == 1
    assert _levels(db, p) == {b1.id: Decimal('40'), b2.id: Decimal('100')}


# ── 5-mezon: boshqa korxona ombori yoki nofaol ombor → 400, hech narsa saqlanmaydi ──
def test_import_foreign_or_inactive_warehouse_400(db, mk, client):
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    inactive = mk.warehouse(ca, ba, is_active=False)
    before = db.query(Product).filter(Product.company_id == ca.id).count()

    for bad_wh in (wb.id, inactive.id, 999999):
        r = client.login(ua).post(
            f'{IMPORT_URL}?warehouse_id={bad_wh}',
            json=[{'Nomi': 'Yangi tovar', 'Qoldiq': 5}],
        )
        assert r.status_code == 400, r.text
        assert r.json()['detail'] == 'Tanlangan ombor topilmadi'

    assert db.query(Product).filter(Product.company_id == ca.id).count() == before
    assert db.query(Product).filter(Product.name == 'Yangi tovar').count() == 0

    # Ijobiy yo'l: o'z ombori ishlaydi
    r = client.login(ua).post(f'{IMPORT_URL}?warehouse_id={wa.id}', json=[{'Nomi': 'Yangi tovar', 'Qoldiq': 5}])
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 1


# ── 6-mezon: yangi mahsulot — qoldiq tanlangan omborga, Batch + IN harakati ──
def test_import_new_product_stock_goes_to_selected_warehouse(db, mk, client):
    c, b, w1, u = mk.tenant()
    w2 = mk.warehouse(c, b, name='Tanlangan')

    r = client.login(u).post(
        f'{IMPORT_URL}?warehouse_id={w2.id}',
        json=[{'Nomi': 'Yangi', 'Qoldiq': 7, 'Tan narxi': 1200, 'Chakana narxi': 1500}],
    )
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 1, r.json()

    p = db.query(Product).filter(Product.name == 'Yangi', Product.company_id == c.id).one()
    assert _levels(db, p) == {w2.id: Decimal('7')}
    assert db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id.is_(None)).count() == 0

    mv = _movements(db, p)
    assert len(mv) == 1
    assert mv[0].type == MovementType.IN
    assert mv[0].warehouse_id == w2.id
    assert mv[0].reference_type == 'product_import'
    assert Decimal(str(mv[0].quantity)) == Decimal('7')

    batches = db.query(Batch).filter(Batch.product_id == p.id).all()
    assert len(batches) == 1
    assert batches[0].warehouse_id == w2.id
    assert Decimal(str(batches[0].quantity)) == Decimal('7')
    assert Decimal(str(batches[0].purchase_price)) == Decimal('1200')
    assert batches[0].company_id == c.id

    # Qoldiq 0 bo'lsa StockLevel/harakat yaratilmaydi (ombor berilmasa ham xato emas)
    r = client.login(u).post(IMPORT_URL, json=[{'Nomi': 'Nol', 'Qoldiq': 0}])
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 1
    assert r.json()['warehouse_id'] == w1.id  # korxonaning birinchi ombori
    p0 = db.query(Product).filter(Product.name == 'Nol', Product.company_id == c.id).one()
    assert _levels(db, p0) == {}
    assert _movements(db, p0) == []

    # Manfiy qoldiq → qator xatosi
    r = client.login(u).post(IMPORT_URL, json=[{'Nomi': 'Manfiy', 'Qoldiq': -3}])
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 0
    assert any('manfiy' in e['error'].lower() for e in r.json()['errors'])


def test_import_new_product_without_any_warehouse_is_row_error(db, mk, client):
    c = mk.company()
    u = mk.user(c)  # korxonada ombor yo'q
    r = client.login(u).post(IMPORT_URL, json=[{'Nomi': 'Omborsiz', 'Qoldiq': 3}])
    assert r.status_code == 200, r.text
    assert r.json()['created'] == 0
    assert r.json()['warehouse_id'] is None
    assert len(r.json()['errors']) == 1
    assert db.query(Product).filter(Product.name == 'Omborsiz').count() == 0


# ── 7-mezon: variantli yoki sell/service mahsulot — qoldiq o'zgarmaydi, warnings ──
def test_import_variant_and_sell_products_not_adjusted(db, mk, client):
    c, b, w, u = mk.tenant()
    parent = _product(db, c, 'Variantli', product_type='parent')
    v = ProductVariant(product_id=parent.id, name='XL', sku='V-XL', barcode='BC-V-XL')
    db.add(v)
    db.flush()
    db.add(StockLevel(product_id=parent.id, variant_id=v.id, warehouse_id=w.id, quantity=Decimal('3')))
    sell = _product(db, c, 'Tarkibiy', product_type='sell')
    service = _product(db, c, 'Xizmat', product_type='service')
    oddiy = _product(db, c, 'Oddiy')
    db.flush()

    r = client.login(u).post(
        f'{IMPORT_URL}?allow_update=true&warehouse_id={w.id}',
        json=[
            {'Nomi': 'Variantli', 'Qoldiq': 50},
            {'Nomi': 'Tarkibiy', 'Qoldiq': 50},
            {'Nomi': 'Xizmat', 'Qoldiq': 50},
            {'Nomi': 'Oddiy', 'Qoldiq': 50},
        ],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['updated'] == 4, body
    warned = {wn['name'] for wn in body['warnings']}
    assert warned == {'Variantli', 'Tarkibiy', 'Xizmat'}
    assert all(wn['row'] for wn in body['warnings'])

    # Variantli: faqat variant qatori qoladi, NULL-variant qatori paydo bo'lmaydi
    rows = db.query(StockLevel).filter(StockLevel.product_id == parent.id).all()
    assert [(r_.variant_id, Decimal(str(r_.quantity))) for r_ in rows] == [(v.id, Decimal('3'))]
    assert _movements(db, parent) == []
    assert _levels(db, sell) == {} and _movements(db, sell) == []
    assert _levels(db, service) == {} and _movements(db, service) == []
    # Oddiy mahsulot yangilanadi
    assert _levels(db, oddiy) == {w.id: Decimal('50')}
    assert len(_movements(db, oddiy)) == 1


# ── adjust_stock harakatga warehouse_id yozadi ───────────────────────────────
def test_adjust_stock_movement_has_warehouse_id(db, mk):
    from app.services.inventory_service import adjust_stock

    c, b, w, u = mk.tenant()
    p = _product(db, c, 'Adj')
    _stock(db, p, w, 4)
    m = adjust_stock(db, p.id, Decimal('9'), u.id, reason='test', warehouse_id=w.id, company_id=c.id)
    assert m.warehouse_id == w.id
    assert m.type == MovementType.ADJUST
    assert _levels(db, p) == {w.id: Decimal('9')}
