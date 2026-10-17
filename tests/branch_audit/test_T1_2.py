"""T1.2 — foydalanuvchi-filial modeli: user_companies.branch_id, user_branches, filial menejeri.

Filial korxona bo'yicha saqlanadi; ko'p korxonali xodim B ni tanlaganda rol/korxona/filial B niki;
manager'ga bir nechta filial biriktiriladi (rol enum'i kengaytirilmaydi).
"""
import importlib.util
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect

from app.core.branch_context import (
    assigned_branch_ids, build_branch_context, effective_branch_id,
)
from app.core.security import create_access_token, create_refresh_token
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.models.user_branch import UserBranch
from app.models.user_company import UserCompany
from app.services.sale_helpers import resolve_branch_id

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _bearer(user_id, company_id, role):
    tok = create_access_token({"sub": str(user_id), "role": role, "company_id": company_id})
    return {"Authorization": f"Bearer {tok}"}


def _drop_user_override():
    from app.core.dependencies import get_current_user, get_current_user_allow_expired
    from app.main import app
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_allow_expired, None)


def _add_uc(db, user, company, role, branch=None):
    uc = UserCompany(user_id=user.id, company_id=company.id, role=role, permissions={}, is_active=True,
                     branch_id=branch.id if branch else None)
    db.add(uc)
    db.flush()
    return uc


@pytest.fixture
def world(db, mk):
    """A va B korxona. `multi` — A da admin (A filiali), B da kassir (B filiali). Har korxonada admin."""
    ca, cb = mk.company(), mk.company()
    ba, bb = mk.branch(ca), mk.branch(cb)
    wa, wb = mk.warehouse(ca, ba), mk.warehouse(cb, bb)
    admin_a = mk.user(ca, role=UserRole.admin, branch=ba)
    admin_b = mk.user(cb, role=UserRole.admin, branch=bb)
    _add_uc(db, admin_a, ca, UserRole.admin, ba)
    _add_uc(db, admin_b, cb, UserRole.admin, bb)
    multi = mk.user(ca, role=UserRole.admin, branch=ba)            # users.branch_id = A filiali (legacy)
    _add_uc(db, multi, ca, UserRole.admin, ba)
    _add_uc(db, multi, cb, UserRole.cashier, bb)
    return dict(ca=ca, cb=cb, ba=ba, bb=bb, wa=wa, wb=wb, admin_a=admin_a, admin_b=admin_b, multi=multi)


# ---- 1. select-company / me / refresh: B kontekstida -------------------------------------
def test_select_company_returns_selected_company_context(client, db, world):
    w = world
    m = w['multi']
    temp = create_access_token({"user_id": m.id, "type": "temp_login"})
    r = client.post('/api/auth/select-company', json={'temp_token': temp, 'company_id': w['cb'].id})
    assert r.status_code == 200, r.text
    u = r.json()['user']
    assert u['role'] == 'cashier' and u['company_id'] == w['cb'].id
    assert u['branch_id'] == w['bb'].id and u['branch_ids'] == [w['bb'].id]
    # A ni tanlasa — A konteksti
    r = client.post('/api/auth/select-company', json={'temp_token': temp, 'company_id': w['ca'].id})
    u = r.json()['user']
    assert u['role'] == 'admin' and u['company_id'] == w['ca'].id and u['branch_id'] == w['ba'].id
    # ORM obyekti o'zgarmagan (users jadvali asosiy korxona qiymatlarini saqlaydi)
    db.expire_all()
    mm = db.get(User, m.id)
    assert mm.company_id == w['ca'].id and mm.role == UserRole.admin and mm.branch_id == w['ba'].id


def test_select_company_foreign_membership_denied(client, db, mk, world):
    w = world
    temp = create_access_token({"user_id": w['admin_a'].id, "type": "temp_login"})
    r = client.post('/api/auth/select-company', json={'temp_token': temp, 'company_id': w['cb'].id})
    assert r.status_code in (400, 403, 404), r.text


def test_me_and_warehouses_in_selected_company(client, db, world):
    w = world
    h = _bearer(w['multi'].id, w['cb'].id, 'cashier')
    r = client.get('/api/auth/me', headers=h)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me['company_id'] == w['cb'].id and me['role'] == 'cashier'
    assert me['branch_id'] == w['bb'].id
    # B ombori ko'rinadi (A filiali bilan kesishib bo'sh chiqmaydi)
    r = client.get('/api/warehouses', headers=h)
    assert r.status_code == 200, r.text
    ids = [x['id'] for x in r.json()]
    assert w['wb'].id in ids and w['wa'].id not in ids


def test_resolve_branch_id_never_returns_other_company_branch(db, world):
    w = world
    # B kontekstidagi xodim: users.branch_id (A filiali) hali bor, lekin company_id = B
    ctx_user = SimpleNamespace(id=w['multi'].id, company_id=w['cb'].id, branch_id=w['ba'].id,
                               role=UserRole.cashier)
    assert resolve_branch_id(db, ctx_user) == w['bb'].id
    assert effective_branch_id(db, ctx_user) == w['bb'].id
    # A kontekstida — A filiali
    ctx_a = SimpleNamespace(id=w['multi'].id, company_id=w['ca'].id, branch_id=w['ba'].id, role=UserRole.admin)
    assert resolve_branch_id(db, ctx_a) == w['ba'].id


def test_legacy_users_branch_of_other_company_ignored(db, mk, world):
    """uc.branch_id yo'q, users.branch_id begona korxona filiali — hisobga olinmaydi."""
    w = world
    u = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])
    _add_uc(db, u, w['ca'], UserRole.cashier, None)
    _add_uc(db, u, w['cb'], UserRole.cashier, None)
    ns_b = SimpleNamespace(id=u.id, company_id=w['cb'].id, branch_id=w['ba'].id, role=UserRole.cashier)
    assert assigned_branch_ids(db, ns_b) == []
    ns_a = SimpleNamespace(id=u.id, company_id=w['ca'].id, branch_id=w['ba'].id, role=UserRole.cashier)
    assert assigned_branch_ids(db, ns_a) == [w['ba'].id]       # legacy fallback faqat o'z korxonasi


def test_refresh_keeps_selected_company(client, db, world):
    w = world
    m = w['multi']
    refresh = create_refresh_token({"sub": str(m.id), "company_id": w['cb'].id})
    r = client.post('/api/auth/refresh', json={'refresh_token': refresh})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['user']['role'] == 'cashier' and body['user']['company_id'] == w['cb'].id
    assert body['user']['branch_id'] == w['bb'].id
    from app.core.security import decode_token
    claims = decode_token(body['access_token'])
    assert claims['company_id'] == w['cb'].id and claims['role'] == 'cashier'
    assert decode_token(body['refresh_token'])['company_id'] == w['cb'].id
    # eski refresh token (claim yo'q) — asosiy korxona
    old = create_refresh_token({"sub": str(m.id)})
    r = client.post('/api/auth/refresh', json={'refresh_token': old})
    assert r.status_code == 200 and r.json()['user']['company_id'] == w['ca'].id


# ---- 2. users.py: filial korxona bo'yicha ------------------------------------------------
def test_other_company_admin_branch_change_does_not_touch_other_company(client, db, world):
    w = world
    m = w['multi']
    bb2 = Branch(name='B2', company_id=w['cb'].id)
    db.add(bb2)
    db.flush()
    r = client.login(w['admin_b']).put(f"/api/users/{m.id}", json={'branch_id': bb2.id})
    assert r.status_code == 200, r.text
    assert r.json()['branch_id'] == bb2.id
    db.expire_all()
    uc_a = db.query(UserCompany).filter_by(user_id=m.id, company_id=w['ca'].id).one()
    uc_b = db.query(UserCompany).filter_by(user_id=m.id, company_id=w['cb'].id).one()
    assert uc_a.branch_id == w['ba'].id          # A dagi filial o'zgarmadi
    assert uc_b.branch_id == bb2.id
    assert db.get(User, m.id).branch_id == w['ba'].id   # users.branch_id (asosiy korxona ko'zgusi)


def test_user_branch_must_belong_to_company(client, db, mk, world):
    w = world
    r = client.login(w['admin_a']).post('/api/users/', json={
        'name': 'Yangi', 'phone': '998901112233', 'password': 'secret123', 'role': 'manager',
        'branch_id': w['bb'].id})
    assert r.status_code in (400, 404), r.text
    r = client.login(w['admin_a']).post('/api/users/', json={
        'name': 'Yangi', 'phone': '998901112233', 'password': 'secret123', 'role': 'manager',
        'branch_ids': [w['bb'].id]})
    assert r.status_code in (400, 404), r.text
    assert db.query(User).filter(User.phone == '998901112233').count() == 0


def test_create_user_writes_branch_to_user_company(client, db, world):
    w = world
    r = client.login(w['admin_a']).post('/api/users/', json={
        'name': 'Kassir', 'phone': '998901112244', 'password': 'secret123', 'role': 'cashier',
        'branch_id': w['ba'].id})
    assert r.status_code in (200, 201), r.text
    uid = r.json()['id']
    uc = db.query(UserCompany).filter_by(user_id=uid, company_id=w['ca'].id).one()
    assert uc.branch_id == w['ba'].id
    assert r.json()['branch_id'] == w['ba'].id


def test_add_existing_user_to_company_saves_branch_per_company(client, db, world):
    """Mavjud xodimni B ga qo'shish: branch_id B a'zoligiga yoziladi, users.branch_id (A) tegilmaydi."""
    w = world
    from app.models.user import UserStatus
    u = User(name='Faqat A', phone='998905550001', hashed_password='x', role=UserRole.cashier,
             company_id=w['ca'].id, branch_id=w['ba'].id, status=UserStatus.active)
    db.add(u)
    db.flush()
    _add_uc(db, u, w['ca'], UserRole.cashier, w['ba'])
    r = client.login(w['admin_b']).post('/api/users/', json={
        'name': 'Faqat A', 'phone': '998905550001', 'password': 'secret123', 'role': 'cashier',
        'branch_id': w['bb'].id,
        'otp_verified_token': create_access_token({"type": "otp_verified", "phone": '998905550001'})})
    assert r.status_code in (200, 201), r.text
    db.expire_all()
    ucb = db.query(UserCompany).filter_by(user_id=u.id, company_id=w['cb'].id).one()
    assert ucb.branch_id == w['bb'].id
    assert db.get(User, u.id).branch_id == w['ba'].id
    assert db.query(UserCompany).filter_by(user_id=u.id, company_id=w['ca'].id).one().branch_id == w['ba'].id


def test_cashier_without_branch_in_multi_branch_company_400(client, db, mk, world):
    w = world
    # 1 faol filial: filialsiz kassir mumkin
    r = client.login(w['admin_a']).post('/api/users/', json={
        'name': 'K1', 'phone': '998901110001', 'password': 'secret123', 'role': 'cashier'})
    assert r.status_code in (200, 201), r.text
    mk.branch(w['ca'])                                           # endi 2 ta faol filial
    for role in ('cashier', 'warehouse'):
        r = client.login(w['admin_a']).post('/api/users/', json={
            'name': 'K2', 'phone': '998901110002', 'password': 'secret123', 'role': role})
        assert r.status_code == 400, r.text
        assert r.json()['detail'] == "Bu rol uchun filial majburiy"
    assert db.query(User).filter(User.phone == '998901110002').count() == 0
    # filial bilan — ok; manager filialsiz ham mumkin
    r = client.login(w['admin_a']).post('/api/users/', json={
        'name': 'K3', 'phone': '998901110003', 'password': 'secret123', 'role': 'cashier',
        'branch_id': w['ba'].id})
    assert r.status_code in (200, 201), r.text
    r = client.login(w['admin_a']).post('/api/users/', json={
        'name': 'M1', 'phone': '998901110004', 'password': 'secret123', 'role': 'manager'})
    assert r.status_code in (200, 201), r.text


def test_list_users_company_scoped_and_orm_not_dirty(client, db, world):
    w = world
    m = w['multi']
    r = client.login(w['admin_b']).get('/api/users/')
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x['id'] == m.id)
    assert row['branch_id'] == w['bb'].id and row['branch_ids'] == [w['bb'].id]
    # ORM obyektlariga yozilmagan: sessiyada o'zgargan (dirty) User yo'q va users.branch_id o'zgarmagan
    assert not [o for o in db.dirty if isinstance(o, User)]
    db.expire_all()
    assert db.get(User, m.id).branch_id == w['ba'].id
    # A admini uchun — A filiali
    r = client.login(w['admin_a']).get('/api/users/')
    row = next(x for x in r.json() if x['id'] == m.id)
    assert row['branch_id'] == w['ba'].id


def test_users_isolation_between_companies(client, db, mk, world):
    w = world
    only_b = mk.user(w['cb'], role=UserRole.cashier, branch=w['bb'])
    _add_uc(db, only_b, w['cb'], UserRole.cashier, w['bb'])
    r = client.login(w['admin_a']).put(f"/api/users/{only_b.id}", json={'branch_id': w['ba'].id})
    assert r.status_code in (403, 404), r.text
    db.expire_all()
    assert db.query(UserCompany).filter_by(user_id=only_b.id, company_id=w['cb'].id).one().branch_id == w['bb'].id
    r = client.login(w['admin_a']).get('/api/users/')
    assert only_b.id not in [x['id'] for x in r.json()]
    # ijobiy yo'l: o'z korxonasi xodimi
    r = client.login(w['admin_b']).put(f"/api/users/{only_b.id}", json={'name': 'Yangi nom'})
    assert r.status_code == 200, r.text


# ---- 3. manager + bir nechta filial -----------------------------------------------------
def test_manager_with_two_branches_scoped(client, db, mk, world):
    w = world
    b2, b3 = mk.branch(w['ca']), mk.branch(w['ca'])
    w2, w3 = mk.warehouse(w['ca'], b2), mk.warehouse(w['ca'], b3)
    mgr = mk.user(w['ca'], role=UserRole.manager)
    _add_uc(db, mgr, w['ca'], UserRole.manager, None)
    r = client.login(w['admin_a']).put(f"/api/users/{mgr.id}", json={
        'branch_id': w['ba'].id, 'branch_ids': [w['ba'].id, b2.id]})
    assert r.status_code == 200, r.text
    assert r.json()['branch_ids'] == sorted([w['ba'].id, b2.id])
    assert {x.branch_id for x in db.query(UserBranch).filter_by(user_id=mgr.id, company_id=w['ca'].id)} \
        == {w['ba'].id, b2.id}

    h = _bearer(mgr.id, w['ca'].id, 'manager')
    _drop_user_override()       # haqiqiy token orqali (client.login override'i olib tashlanadi)
    r = client.get('/api/warehouses', headers=h)
    assert r.status_code == 200, r.text
    ids = {x['id'] for x in r.json()}
    assert w['wa'].id in ids and w2.id in ids and w3.id not in ids
    # ruxsat etilgan filial headeri — ok, 3-filial — 403
    assert client.get('/api/warehouses', headers={**h, 'X-Branch-Id': str(b2.id)}).status_code == 200
    r = client.get('/api/warehouses', headers={**h, 'X-Branch-Id': str(b3.id)})
    assert r.status_code == 403, r.text

    # branch_ids bo'sh yuborilsa to'plam tozalanadi
    r = client.login(w['admin_a']).put(f"/api/users/{mgr.id}", json={'branch_id': None, 'branch_ids': []})
    assert r.status_code == 200 and r.json()['branch_ids'] == []
    assert db.query(UserBranch).filter_by(user_id=mgr.id).count() == 0


def test_branch_ids_replace_only_current_company(client, db, mk, world):
    w = world
    m = w['multi']
    extra_a = mk.branch(w['ca'])
    db.add(UserBranch(user_id=m.id, company_id=w['ca'].id, branch_id=extra_a.id))
    db.flush()
    r = client.login(w['admin_b']).put(f"/api/users/{m.id}", json={'branch_ids': [w['bb'].id]})
    assert r.status_code == 200, r.text
    assert db.query(UserBranch).filter_by(user_id=m.id, company_id=w['ca'].id).count() == 1   # A tegilmadi
    assert db.query(UserBranch).filter_by(user_id=m.id, company_id=w['cb'].id).count() == 1


def test_build_branch_context_uses_union(db, mk, world):
    w = world
    b2 = mk.branch(w['ca'])
    mgr = mk.user(w['ca'], role=UserRole.manager)
    _add_uc(db, mgr, w['ca'], UserRole.manager, w['ba'])
    db.add(UserBranch(user_id=mgr.id, company_id=w['ca'].id, branch_id=b2.id))
    db.flush()
    ctx = build_branch_context(db, mgr)
    assert ctx.allowed_branch_ids == frozenset({w['ba'].id, b2.id}) and ctx.branch_id is None
    # begona korxona filiali user_branches ga tushib qolsa ham ruxsat etilmaydi
    db.add(UserBranch(user_id=mgr.id, company_id=w['ca'].id, branch_id=w['bb'].id))
    db.flush()
    assert w['bb'].id not in assigned_branch_ids(db, mgr)


# ---- 4. /branches include_inactive -------------------------------------------------------
def test_branches_include_inactive(client, db, mk, world):
    w = world
    off = mk.branch(w['ca'], is_active=False)
    r = client.login(w['admin_a']).get('/api/branches')
    assert off.id not in [x['id'] for x in r.json()]
    r = client.login(w['admin_a']).get('/api/branches?include_inactive=true')
    ids = [x['id'] for x in r.json()]
    assert off.id in ids and w['bb'].id not in ids          # begona korxona filiali hech qachon


# ---- 5. model / migratsiya mosligi -------------------------------------------------------
def test_models_match_migration(db):
    insp = inspect(db.get_bind())
    uc_cols = {c['name'] for c in insp.get_columns('user_companies')}
    assert 'branch_id' in uc_cols
    ub_cols = {c['name'] for c in insp.get_columns('user_branches')}
    assert {'id', 'user_id', 'company_id', 'branch_id', 'created_at'} <= ub_cols
    assert any(ix['name'] == 'ix_user_branches_user_company' for ix in insp.get_indexes('user_branches'))
    assert any(u['name'] == 'uq_user_branch' for u in insp.get_unique_constraints('user_branches'))


def test_migration_file_contract():
    path = os.path.join(ROOT, 'alembic', 'versions', 't1_2_user_companies_branch_user_branches.py')
    spec = importlib.util.spec_from_file_location('t1_2_mig', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == 't1_2'
    sql = ' '.join(mod.SCHEMA_STATEMENTS)
    assert 'ADD COLUMN IF NOT EXISTS branch_id' in sql and 'CREATE TABLE IF NOT EXISTS user_branches' in sql
    assert 'ix_user_branches_user_company' in sql and 'uq_user_branch' in sql
    data = ' '.join(mod.DATA_STATEMENTS)
    assert 'b.company_id = uc.company_id' in data            # begona korxona filiali o'tkazilmaydi
    assert 'UPDATE shifts' in data


# ---- 6. company_purge user_branches ni ham o'chiradi --------------------------------------
def test_company_purge_removes_user_branches(db, mk):
    from app.services.company_purge import purge_company
    cx, cy = mk.company(), mk.company()
    bx1, bx2, by = mk.branch(cx), mk.branch(cx), mk.branch(cy)
    mgr = mk.user(cx, role=UserRole.manager, branch=bx1)
    _add_uc(db, mgr, cx, UserRole.manager, bx1)
    _add_uc(db, mgr, cy, UserRole.manager, by)          # boshqa korxonaga ham a'zo: user saqlanadi
    db.add_all([
        UserBranch(user_id=mgr.id, company_id=cx.id, branch_id=bx1.id),
        UserBranch(user_id=mgr.id, company_id=cx.id, branch_id=bx2.id),
        UserBranch(user_id=mgr.id, company_id=cy.id, branch_id=by.id),
    ])
    db.flush()
    purge_company(db, cx.id)
    assert db.query(UserBranch).filter(UserBranch.company_id == cx.id).count() == 0
    assert db.query(UserBranch).filter(UserBranch.company_id == cy.id).count() == 1
    assert db.query(UserCompany).filter(UserCompany.company_id == cx.id).count() == 0


# ---- 7. qaytarish: ombor ruxsati joriy korxona filiallari bo'yicha (users.branch_id emas) -------
def _ret_product(db, company, wh, qty=100):
    from decimal import Decimal
    from app.models.inventory import StockLevel
    from app.models.product import Product
    n = f"{company.id}-{wh.id}"
    p = Product(name=f"T12 tovar {n}", sku=f"T12-{n}", barcode=f"B12-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


def _wallet12(db, company, branch):
    from decimal import Decimal
    from app.models.moliya import KassaSession, Wallet
    w = Wallet(name=f"T12 kassa {company.id}", type="cash", balance=Decimal(0), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _return_data(prod, wh):
    from decimal import Decimal
    from app.schemas.sale import SaleCreate
    return SaleCreate(items=[{"product_id": prod.id, "quantity": 1, "unit_price": 1000}],
                      payment_type="debt", paid_amount=Decimal("1000"), warehouse_id=wh.id)


def test_full_return_multi_company_cashier_in_b(db, mk, world):
    """A va B ga a'zo kassir (users.branch_id = A filiali) B ning o'z omborida qaytarish qila oladi."""
    from fastapi import HTTPException
    from app.services.sale_return import create_return_sale
    w = world
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])      # users.branch_id = A filiali
    _add_uc(db, cashier, w['ca'], UserRole.cashier, w['ba'])
    _add_uc(db, cashier, w['cb'], UserRole.cashier, w['bb'])
    prod_b = _ret_product(db, w['cb'], w['wb'])
    prod_a = _ret_product(db, w['ca'], w['wa'])
    cashier.company_id = w['cb'].id          # get_current_user B tokenida shunday qiladi
    sale = create_return_sale(db, _return_data(prod_b, w['wb']), cashier)
    assert sale.company_id == w['cb'].id
    # A ning ombori B kontekstida ko'rinmaydi → 404 (boshqa korxona ombori)
    with pytest.raises(HTTPException) as ei:
        create_return_sale(db, _return_data(prod_a, w['wa']), cashier)
    assert ei.value.status_code == 404


def test_full_return_manager_two_branches(db, mk, world):
    """branch_ids=[1,2] manager ikkala filial omborida qaytarish qila oladi, 3-filial omborida 403."""
    from fastapi import HTTPException
    from app.services.sale_return import create_return_sale
    w = world
    b2, b3 = mk.branch(w['ca']), mk.branch(w['ca'])
    w2, w3 = mk.warehouse(w['ca'], b2), mk.warehouse(w['ca'], b3)
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['ba'])        # users.branch_id faqat 1-filial
    _add_uc(db, mgr, w['ca'], UserRole.manager, w['ba'])
    db.add(UserBranch(user_id=mgr.id, company_id=w['ca'].id, branch_id=b2.id))
    db.flush()
    p1, p2, p3 = (_ret_product(db, w['ca'], x) for x in (w['wa'], w2, w3))
    assert create_return_sale(db, _return_data(p1, w['wa']), mgr).warehouse_id == w['wa'].id
    assert create_return_sale(db, _return_data(p2, w2), mgr).warehouse_id == w2.id
    with pytest.raises(HTTPException) as ei:
        create_return_sale(db, _return_data(p3, w3), mgr)
    assert ei.value.status_code == 403


def test_partial_return_multi_company_cashier_and_manager(db, mk, world):
    from decimal import Decimal
    from fastapi import HTTPException
    from app.models.sale import Sale
    from app.schemas.sale import SaleCreate, SaleReturnRequest
    from app.services.sale_create import create_sale
    from app.services.sale_partial_return import process_partial_return
    w = world

    def _sale(admin, company, branch, wh):
        _wallet12(db, company, branch)
        prod = _ret_product(db, company, wh)
        s = create_sale(db, SaleCreate(
            items=[{"product_id": prod.id, "quantity": 2, "unit_price": 1000}], payment_type="cash",
            paid_amount=Decimal("2000"), warehouse_id=wh.id), admin)
        return db.query(Sale).get(s.id)

    # 1) ko'p korxonali kassir B da (users.branch_id = A filiali)
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])
    _add_uc(db, cashier, w['ca'], UserRole.cashier, w['ba'])
    _add_uc(db, cashier, w['cb'], UserRole.cashier, w['bb'])
    sale_b = _sale(w['admin_b'], w['cb'], w['bb'], w['wb'])
    cashier.company_id = w['cb'].id
    out = process_partial_return(db, sale_b.id, SaleReturnRequest(
        items=[{"sale_item_id": sale_b.items[0].id, "quantity": 1}], payment_type="debt",
        warehouse_id=w['wb'].id), cashier)
    assert out is not None

    # 2) 2 filialli manager: ikkinchi filial ombori ruxsat, 3-filial ombori 403
    b2, b3 = mk.branch(w['ca']), mk.branch(w['ca'])
    w2, w3 = mk.warehouse(w['ca'], b2), mk.warehouse(w['ca'], b3)
    mgr = mk.user(w['ca'], role=UserRole.manager, branch=w['ba'])
    _add_uc(db, mgr, w['ca'], UserRole.manager, w['ba'])
    db.add(UserBranch(user_id=mgr.id, company_id=w['ca'].id, branch_id=b2.id))
    db.flush()
    sale_a2 = _sale(w['admin_a'], w['ca'], b2, w2)
    process_partial_return(db, sale_a2.id, SaleReturnRequest(
        items=[{"sale_item_id": sale_a2.items[0].id, "quantity": 1}], payment_type="debt",
        warehouse_id=w2.id), mgr)
    with pytest.raises(HTTPException) as ei:
        process_partial_return(db, sale_a2.id, SaleReturnRequest(
            items=[{"sale_item_id": sale_a2.items[0].id, "quantity": 1}], payment_type="debt",
            warehouse_id=w3.id), mgr)
    assert ei.value.status_code == 403


# ---- 8. update_user: allaqachon biriktirilgan nofaol filial forma qayta saqlanganda to'smaydi ----
def test_update_manager_keeps_inactive_assigned_branch(client, db, mk, world):
    w = world
    b2, b3 = mk.branch(w['ca']), mk.branch(w['ca'])
    mgr = mk.user(w['ca'], role=UserRole.manager)
    _add_uc(db, mgr, w['ca'], UserRole.manager, None)
    db.add(UserBranch(user_id=mgr.id, company_id=w['ca'].id, branch_id=b2.id))
    db.flush()
    b2.is_active = False
    b3.is_active = False
    db.flush()
    c = client.login(w['admin_a'])
    # o'zgarmagan nofaol filial + faol filial: 200
    r = c.put(f"/api/users/{mgr.id}", json={'name': 'Yangi', 'branch_ids': [b2.id, w['ba'].id]})
    assert r.status_code == 200, r.text
    assert set(r.json()['branch_ids']) == {b2.id, w['ba'].id}
    # YANGI qo'shilayotgan nofaol filial: 400
    r = c.put(f"/api/users/{mgr.id}", json={'branch_ids': [b2.id, w['ba'].id, b3.id]})
    assert r.status_code == 400, r.text
