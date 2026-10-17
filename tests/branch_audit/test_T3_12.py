"""T3.12 — Tarozi eksporti: PLU moslik, 50 ta cheklov, filial kesimi.

Qamrov (qabul mezonlari):
  1  migratsiya: SKU 'KG-0123' kg mahsulotga plu_code=123, to'qnashuv/0 bo'lsa eng kichik bo'sh raqam;
     POS skaneri (barcode/PLU) shu mahsulotni topadi;
  2  uchala eksport formati bir xil PLU ni ishlatadi (frontend fayllari statik tekshiriladi);
  3  120 ta kg mahsuloti bor korxonada /export/scale 120 ta qator beradi (50 da kesilmaydi);
  4  branch_id bo'yicha faqat shu filial qoldig'i; boshqa korxona filiali 404; rol 403;
  5  band PLU -> 409; yangi kg mahsulotga PLU avtomatik;
  6  /export/rongta kg mahsuloti bor korxonada 200 (AttributeError yo'q);
  7  /barcode/00123 indeksli PLU so'rovi bilan topadi (butun SKU ro'yxati aylanmaydi).
Har joyda ikki korxona izolyatsiyasi va ijobiy yo'l tekshiriladi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_12.py -q -p no:cacheprovider
"""
import importlib.util
import itertools
import json
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from app.models.inventory import StockLevel
from app.models.product import Product, ProductStatus
from app.models.user import UserRole
from app.routers.products import _assign_plu


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_n = itertools.count(1)


def _prod(db, company, sku=None, unit='kg', plu=None, name=None, price=1000, **kw):
    n = next(_n)
    p = Product(
        sku=sku or f'T312-{n:05d}', barcode=kw.pop('barcode', f'2999{n:09d}'),
        name=name or f'Tovar {n}', company_id=company.id, unit=unit, plu_code=plu,
        sale_price=Decimal(price), cost_price=Decimal(0), **kw,
    )
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty):
    db.add(StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal(qty)))
    db.flush()


def _read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f:
        return f.read()


# ───────────────────────── _assign_plu ─────────────────────────

def test_assign_plu_finds_smallest_free(db, mk):
    c = mk.company()
    _prod(db, c, plu=1)
    _prod(db, c, plu=2)
    _prod(db, c, plu=4)
    new = Product(sku='X-1', barcode='b-1', name='Yangi', company_id=c.id, unit='kg')
    assert _assign_plu(db, c.id, new) == 3
    assert new.plu_code == 3


def test_assign_plu_skips_non_scale_units(db, mk):
    c = mk.company()
    new = Product(sku='X-2', barcode='b-2', name='Dona', company_id=c.id, unit='dona')
    assert _assign_plu(db, c.id, new) is None
    assert new.plu_code is None


def test_assign_plu_busy_requested_409(db, mk):
    c = mk.company()
    _prod(db, c, plu=77, name='Olma')
    new = Product(sku='X-3', barcode='b-3', name='Nok', company_id=c.id, unit='kg')
    with pytest.raises(HTTPException) as e:
        _assign_plu(db, c.id, new, 77)
    assert e.value.status_code == 409
    assert 'PLU kodi band' in e.value.detail and 'Olma' in e.value.detail


def test_assign_plu_other_company_does_not_collide(db, mk):
    a, b = mk.company(), mk.company()
    _prod(db, a, plu=5)
    new = Product(sku='X-4', barcode='b-4', name='B tovar', company_id=b.id, unit='kg')
    assert _assign_plu(db, b.id, new, 5) == 5          # boshqa korxonada 5 band emas
    auto = Product(sku='X-5', barcode='b-5', name='B tovar 2', company_id=b.id, unit='kg')
    assert _assign_plu(db, b.id, auto) == 1            # A ning 5 i B ning bo'sh joyini siljitmaydi


def test_assign_plu_deleted_product_does_not_hold_code(db, mk):
    c = mk.company()
    _prod(db, c, plu=1, is_deleted=True)
    new = Product(sku='X-6', barcode='b-6', name='Yangi', company_id=c.id, unit='kg')
    # o'chirilgan mahsulot kodni band qilmaydi (flush qilinmaydi: SQLite da indeks to'liq)
    assert _assign_plu(db, c.id, new, 1) == 1


def test_assign_plu_update_keeps_own_code(db, mk):
    c = mk.company()
    p = _prod(db, c, plu=9)
    assert _assign_plu(db, c.id, p, 9) == 9            # o'z kodi o'zini band qilmaydi
    assert _assign_plu(db, c.id, p) == 9               # allaqachon bor — o'zgarmaydi


def test_plu_schema_range():
    from pydantic import ValidationError
    from app.schemas.product import ProductCreate, ProductUpdate
    ProductUpdate(plu_code=99999)
    for bad in (0, 100000, -1):
        with pytest.raises(ValidationError):
            ProductUpdate(plu_code=bad)
    with pytest.raises(ValidationError):
        ProductCreate(name='x', barcode='1', sale_price=1, plu_code=0)


def test_model_has_plu_constraints():
    names = {getattr(a, 'name', None) for a in Product.__table_args__}
    assert 'uq_products_plu_active' in names and 'ck_products_plu_range' in names


# ───────────────────────── POST / PUT ─────────────────────────

def _payload(**kw):
    n = next(_n)
    d = {'name': f'Mahsulot {n}', 'barcode': f'4000{n:09d}', 'sale_price': 100, 'unit': 'kg'}
    d.update(kw)
    return d


def test_create_kg_product_gets_auto_plu(db, mk, client):
    c, b, w, u = mk.tenant()
    client.login(u)
    r1 = client.post('/api/products/', json=_payload())
    r2 = client.post('/api/products/', json=_payload())
    assert r1.status_code == 201, r1.text
    assert r1.json()['plu_code'] == 1 and r2.json()['plu_code'] == 2
    dona = client.post('/api/products/', json=_payload(unit='dona'))
    assert dona.status_code == 201 and dona.json()['plu_code'] is None


def test_create_with_busy_plu_409_and_free_plu_ok(db, mk, client):
    c, b, w, u = mk.tenant()
    client.login(u)
    ok = client.post('/api/products/', json=_payload(plu_code=555, name='Pomidor'))
    assert ok.status_code == 201 and ok.json()['plu_code'] == 555
    dup = client.post('/api/products/', json=_payload(plu_code=555))
    assert dup.status_code == 409 and 'PLU kodi band' in dup.json()['detail'] and 'Pomidor' in dup.json()['detail']
    bad = client.post('/api/products/', json=_payload(plu_code=100000))
    assert bad.status_code == 422


def test_create_same_plu_in_other_company_ok(db, mk, client):
    _, _, _, ua = mk.tenant()
    _, _, _, ub = mk.tenant()
    client.login(ua)
    assert client.post('/api/products/', json=_payload(plu_code=42)).status_code == 201
    client.login(ub)
    assert client.post('/api/products/', json=_payload(plu_code=42)).status_code == 201


def test_update_plu_busy_409_and_unit_change_assigns(db, mk, client):
    c, b, w, u = mk.tenant()
    client.login(u)
    a = client.post('/api/products/', json=_payload(plu_code=10)).json()
    dona = client.post('/api/products/', json=_payload(unit='dona')).json()
    assert dona['plu_code'] is None
    # band PLU -> 409
    r = client.put(f"/api/products/{dona['id']}", json={'plu_code': 10})
    assert r.status_code == 409
    # birlik kg ga o'zgarsa PLU avtomatik (10 band -> 1)
    r = client.put(f"/api/products/{dona['id']}", json={'unit': 'kg'})
    assert r.status_code == 200, r.text
    assert r.json()['plu_code'] == 1
    # o'z PLU sini qayta yuborish xato emas
    r = client.put(f"/api/products/{a['id']}", json={'plu_code': 10})
    assert r.status_code == 200 and r.json()['plu_code'] == 10


# ───────────────────────── GET /products/export/scale ─────────────────────────

def test_export_scale_no_50_limit_120_rows(db, mk, client):
    c, b, w, u = mk.tenant()
    for i in range(120):
        _prod(db, c, plu=i + 1, name=f'KG {i:03d}')
    _prod(db, c, unit='dona', name='Dona tovar')
    client.login(u)
    r = client.get('/api/products/export/scale')
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 120
    assert {'id', 'name', 'sku', 'plu_code', 'barcode', 'product_code', 'sale_price', 'unit'} <= set(rows[0])
    assert [x['plu_code'] for x in rows[:3]] == [1, 2, 3]
    assert all(x['unit'] in ('kg', 'g') for x in rows)


def test_export_scale_only_active_not_deleted(db, mk, client):
    c, b, w, u = mk.tenant()
    ok = _prod(db, c, plu=1)
    _prod(db, c, plu=2, is_deleted=True)
    _prod(db, c, plu=3, status=ProductStatus.inactive)
    client.login(u)
    assert [x['id'] for x in client.get('/api/products/export/scale').json()] == [ok.id]


def test_export_scale_company_isolation(db, mk, client):
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    pa = _prod(db, ca, plu=1, name='A tovar')
    pb = _prod(db, cb, plu=1, name='B tovar')
    client.login(ua)
    assert [x['id'] for x in client.get('/api/products/export/scale').json()] == [pa.id]
    # boshqa korxona filiali -> 404
    assert client.get('/api/products/export/scale', params={'branch_id': bb.id}).status_code == 404
    assert client.get('/api/products/export/scale', params={'branch_id': 999999}).status_code == 404
    client.login(ub)
    assert [x['id'] for x in client.get('/api/products/export/scale').json()] == [pb.id]


def test_export_scale_branch_cut(db, mk, client):
    c, b1, w1, u = mk.tenant()
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    p1 = _prod(db, c, plu=1, name='Faqat 1-filial')
    p2 = _prod(db, c, plu=2, name='Faqat 2-filial')
    p12 = _prod(db, c, plu=3, name='Ikkalasida')
    _prod(db, c, plu=4, name='Qoldiqsiz')
    _stock(db, p1, w1, 5)
    _stock(db, p2, w2, 7)
    _stock(db, p12, w1, 1)
    _stock(db, p12, w2, 1)
    client.login(u)
    ids = lambda **params: sorted(x['id'] for x in client.get('/api/products/export/scale', params=params).json())
    assert ids(branch_id=b1.id) == sorted([p1.id, p12.id])
    assert ids(branch_id=b2.id) == sorted([p2.id, p12.id])
    assert len(ids()) == 4                                  # filialsiz — butun katalog


def test_export_scale_only_in_stock(db, mk, client):
    c, b, w, u = mk.tenant()
    full = _prod(db, c, plu=1)
    empty = _prod(db, c, plu=2)
    _prod(db, c, plu=3)
    _stock(db, full, w, 3)
    _stock(db, empty, w, 0)
    client.login(u)
    r = client.get('/api/products/export/scale', params={'branch_id': b.id, 'only_in_stock': True})
    assert [x['id'] for x in r.json()] == [full.id]
    r = client.get('/api/products/export/scale', params={'branch_id': b.id})
    assert sorted(x['id'] for x in r.json()) == sorted([full.id, empty.id])
    r = client.get('/api/products/export/scale', params={'only_in_stock': True})
    assert [x['id'] for x in r.json()] == [full.id]


def test_export_scale_branch_user_forced_to_own_branch(db, mk, client):
    c, b1, w1, _ = mk.tenant()
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    mgr = mk.user(c, role=UserRole.manager, branch=b1)
    p1 = _prod(db, c, plu=1)
    p2 = _prod(db, c, plu=2)
    _stock(db, p1, w1, 1)
    _stock(db, p2, w2, 1)
    client.login(mgr)
    assert [x['id'] for x in client.get('/api/products/export/scale').json()] == [p1.id]
    # boshqa filial so'ralsa — ruxsat yo'q
    assert client.get('/api/products/export/scale', params={'branch_id': b2.id}).status_code == 403


def test_export_scale_role_forbidden(db, mk, client):
    c, b, w, _ = mk.tenant()
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    client.login(cashier)
    assert client.get('/api/products/export/scale').status_code == 403


# ───────────────────────── /export/rongta ─────────────────────────

def test_export_rongta_returns_200_with_plu_codes(db, mk, client):
    c, b, w, u = mk.tenant()
    _prod(db, c, plu=123, name='Olma', price=15000)
    _prod(db, c, sku='KG-0456', plu=None, name='Nok', price=20000)   # PLU hali berilmagan eski yozuv
    _prod(db, c, unit='dona', name='Dona')
    client.login(u)
    r = client.get('/api/products/export/rongta')
    assert r.status_code == 200, r.text
    lines = r.text.split('\r\n')
    assert len(lines) == 2
    assert lines[0].startswith('123;OLMA;;15000;')
    assert lines[1].startswith('456;NOK;;20000;')


def test_export_rongta_company_isolation(db, mk, client):
    ca, _, _, ua = mk.tenant()
    cb, _, _, _ = mk.tenant()
    _prod(db, ca, plu=1, name='Mening')
    _prod(db, cb, plu=1, name='Begona')
    client.login(ua)
    assert 'BEGONA' not in client.get('/api/products/export/rongta').text


# ───────────────────────── /barcode/{code} ─────────────────────────

def test_barcode_lookup_by_plu_single_indexed_query(db, mk, client):
    c, b, w, u = mk.tenant()
    p = _prod(db, c, sku='KG-0123', plu=123, name='Tarozi tovar')
    other = _prod(db, c, sku='SKU-1A2B3C', plu=7, name='Boshqa')   # eski usulda 123 ga to'qnashardi
    client.login(u)

    stmts = []

    def _spy(conn, cursor, statement, parameters, context, executemany):
        stmts.append(statement)

    bind = db.get_bind()
    event.listen(bind, 'before_cursor_execute', _spy)
    try:
        r = client.get('/api/products/barcode/00123')
    finally:
        event.remove(bind, 'before_cursor_execute', _spy)
    assert r.status_code == 200, r.text
    assert r.json()['id'] == p.id and r.json()['plu_code'] == 123
    plu_q = [s for s in stmts if 'products.plu_code = ?' in s and 'FROM products' in s]
    assert len(plu_q) == 1
    # eski "barcha SKU larni Python'da aylanish" so'rovi yo'q
    assert not [s for s in stmts if 'FROM products' in s and 'sku IS NOT NULL' in s]
    assert other.id != p.id


def test_barcode_plu_company_isolation(db, mk, client):
    ca, _, _, ua = mk.tenant()
    cb, _, _, ub = mk.tenant()
    pa = _prod(db, ca, plu=50, name='A')
    pb = _prod(db, cb, plu=50, name='B')
    client.login(ua)
    assert client.get('/api/products/barcode/00050').json()['id'] == pa.id
    client.login(ub)
    assert client.get('/api/products/barcode/00050').json()['id'] == pb.id
    cc, _, _, uc = mk.tenant()
    client.login(uc)
    assert client.get('/api/products/barcode/00050').status_code == 404


def test_barcode_exact_match_wins_over_plu(db, mk, client):
    c, b, w, u = mk.tenant()
    _prod(db, c, plu=12345, name='PLU egasi')
    real = _prod(db, c, barcode='12345', unit='dona', name='Haqiqiy shtrix-kod')
    client.login(u)
    assert client.get('/api/products/barcode/12345').json()['id'] == real.id


# ───────────────────────── pos-list / ro'yxat ─────────────────────────

def test_pos_list_and_list_include_plu_code(db, mk, client):
    c, b, w, u = mk.tenant()
    p = _prod(db, c, plu=88, name='Qovun')
    _stock(db, p, w, 5)
    client.login(u)
    r = client.get('/api/products/pos-list', params={'limit': 50})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x['id'] == p.id)
    assert row['plu_code'] == 88
    r = client.get('/api/products/', params={'limit': 50})
    assert next(x for x in r.json() if x['id'] == p.id)['plu_code'] == 88


# ───────────────────────── ommaviy import ─────────────────────────

def test_bulk_import_assigns_plu_to_kg_rows(db, mk, client):
    import sqlite3
    # import "Min. qoldiq" ni Decimal beradi (PostgreSQL Integer ga o'zi o'giradi, SQLite — yo'q)
    sqlite3.register_adapter(Decimal, float)
    c, b, w, u = mk.tenant()
    client.login(u)
    rows = [
        {'Nomi': 'Import kg 1', 'Shtrix-kod': '7770000000011', 'Sotuv narxi': 1000, "O'lchov": 'kg'},
        {'Nomi': 'Import dona', 'Shtrix-kod': '7770000000028', 'Sotuv narxi': 1000, "O'lchov": 'dona'},
    ]
    r = client.post('/api/products/bulk-import', json=rows)
    assert r.status_code == 200, r.text
    got = {p.name: p for p in db.query(Product).filter(Product.company_id == c.id).all()}
    if 'Import kg 1' not in got:           # ustun nomlari boshqacha bo'lsa import xatolarini ko'rsatamiz
        pytest.fail(f'import qatori yaratilmadi: {r.json()}')
    assert got['Import kg 1'].plu_code == 1
    assert got['Import dona'].plu_code is None


# ───────────────────────── migratsiya (ko'chirish mantig'i) ─────────────────────────

def _load_migration():
    path = os.path.join(ROOT, 'alembic', 'versions', 't3_12_add_products_plu_code.py')
    spec = importlib.util.spec_from_file_location('t3_12_mig', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_metadata_and_legacy_candidate():
    mig = _load_migration()
    assert mig.revision == 't3_12' and mig.down_revision == 't3_9'
    assert mig._legacy_candidate('KG-0123') == 123
    assert mig._legacy_candidate('SKU-A1B2C3') == 123
    assert mig._legacy_candidate('SKU-1A2B3C') == 123
    assert mig._legacy_candidate('1234567') == 34567
    assert mig._legacy_candidate('ABC') == 0
    assert mig._legacy_candidate(None) == 0


def test_migration_backfill_keeps_legacy_plu_and_resolves_collisions(db, mk, monkeypatch):
    mig = _load_migration()
    a, b = mk.company(), mk.company()
    kg = _prod(db, a, sku='KG-0123', unit='kg')
    dup1 = _prod(db, a, sku='SKU-A1B2C3', unit='kg')      # 123 -> band (kg), eng kichik bo'sh = 1
    dup2 = _prod(db, a, sku='SKU-1A2B3C', unit='kg')      # 123 -> band, keyingi bo'sh = 2
    zero = _prod(db, a, sku='SKU-ABCDEF', unit='g')       # raqam yo'q -> 3
    dona = _prod(db, a, sku='D-0777', unit='dona')
    deleted = _prod(db, a, sku='KG-0999', unit='kg', is_deleted=True)
    other = _prod(db, b, sku='KG-0123', unit='kg')        # boshqa korxonada 123 band emas
    for p in (kg, dup1, dup2, zero, dona, deleted, other):
        p.plu_code = None
    db.flush()

    executed = []
    fake_op = SimpleNamespace(execute=lambda sql: executed.append(str(sql)), get_bind=lambda: db.connection())
    monkeypatch.setattr(mig, 'op', fake_op)
    mig.upgrade()
    for p in (kg, dup1, dup2, zero, dona, deleted, other):
        db.refresh(p)

    assert kg.plu_code == 123                              # qabul mezoni 1: KG-0123 -> 123
    assert dup1.plu_code == 123 or dup1.plu_code in (1, 2, 3)
    codes = {kg.plu_code, dup1.plu_code, dup2.plu_code, zero.plu_code}
    assert len(codes) == 4                                 # korxona ichida unikal
    assert dup1.plu_code == 1 and dup2.plu_code == 2 and zero.plu_code == 3
    assert dona.plu_code is None and deleted.plu_code is None
    assert other.plu_code == 123
    assert any('uq_products_plu_active' in s for s in executed)
    assert any('ck_products_plu_range' in s for s in executed)


def test_migration_first_candidate_kept_even_if_later_row_collides(db, mk, monkeypatch):
    """Eski TMA PLU lari saqlanadi: id kichikroq mahsulot kodni oladi, keyingisi o'zgaradi."""
    mig = _load_migration()
    c = mk.company()
    first = _prod(db, c, sku='SKU-A1B2C3', unit='kg')
    second = _prod(db, c, sku='KG-0123', unit='kg')
    first.plu_code = second.plu_code = None
    db.flush()
    monkeypatch.setattr(mig, 'op', SimpleNamespace(execute=lambda s: None, get_bind=lambda: db.connection()))
    mig.upgrade()
    db.refresh(first), db.refresh(second)
    assert first.plu_code == 123 and second.plu_code == 1


# ───────────────────────── frontend fayllari (statik) ─────────────────────────

def test_frontend_scale_utils_and_export_use_plu():
    scale = _read('frontend/src/utils/scale.js')
    for token in ("SCALE_UNITS = ['kg', 'g']", 'export function pluCode', 'export function parseScaleBarcode',
                  'export function findScaleProduct', "'20'", "'21'", "'22'", 'padStart(5'):
        assert token in scale, token
    assert "replace(/\\D/g, '')" in scale and "replace(/\\\\D/g" not in scale
    exp = _read('frontend/src/utils/scaleExport.js')
    for fn in ('buildShtrixM', 'buildTma', 'buildRongta'):
        assert f'export function {fn}' in exp
    assert exp.count('pluNumber(prod)') >= 3                # uchala format bitta PLU manbasidan
    assert 'prod.sku' not in exp


def test_frontend_products_page_uses_scale_endpoint_and_branch():
    src = _read('frontend/src/pages/admin/Products.jsx')
    assert "/products/export/scale" in src
    assert 'scaleBranch' in src and 'branch_id: scaleBranch' in src
    assert "api.get('/products/')" not in src                # eksport endi 50 talik ro'yxatdan qurilmaydi
    assert 'plu_code' in src and 'product.pluCode' in src


def test_frontend_pos_use_shared_scale_parser_no_broken_regex():
    for path in ('frontend/src/pages/admin/PosKassa.jsx', 'frontend/src/pages/admin/PosDesktop.jsx'):
        src = _read(path)
        assert 'parseScaleBarcode' in src and 'findScaleProduct' in src, path
        assert "replace(/\\\\D/g" not in src, path           # buzilgan /\\D/g regex qolmagan
        assert '/products/barcode/' in src, path             # lokal topilmasa serverdan PLU bo'yicha


def test_pos_desktop_renderer_matches_by_plu_code():
    src = _read('pos-desktop/renderer/pos.js')
    assert "startsWith('20')" in src and "startsWith('21')" in src and "startsWith('22')" in src
    assert 'Number(x.plu_code) === Number(itemCode)' in src
    assert 'x.sku === itemCode' not in src


def test_i18n_pending_keys_in_all_languages():
    with open(os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T3.12.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    keys = set(data['uz'])
    assert {'product.pluCode', 'product.pluBusy', 'product.scaleBranch'} <= keys
    assert set(data['ru']) == keys and set(data['en']) == keys
    assert all(v.strip() for lang in data.values() for v in lang.values())
