"""T0.9 — branch_id va role_id qiymatlarini korxonaga tekshirish.

users, shifts, warehouses, finance va kassa (wallet yaratish) da mijoz yuborgan `branch_id` / `role_id`
shu korxonaga tegishli (va filial faol) bo'lishi shart; aks holda 400. Global IntegrityError handler 409 beradi.
"""
import itertools

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.models.branch import Branch
from app.models.moliya import Wallet
from app.models.role import Role
from app.models.shift import Shift
from app.models.user import User, UserRole
from app.models.user_company import UserCompany
from app.models.warehouse import Warehouse
from app.services.tenant_guards import (
    BRANCH_INVALID, ROLE_INVALID, validate_branch, validate_role,
)

_n = itertools.count(1)


@pytest.fixture
def world(db, mk):
    """A va B korxona (har birida filial, admin), A da ombor va nofaol filial, uch xil rol."""
    ca, cb = mk.company(), mk.company()
    ba, bb = mk.branch(ca), mk.branch(cb)
    ba_off = mk.branch(ca, is_active=False)
    wa = mk.warehouse(ca, ba)
    admin_a = mk.user(ca, role=UserRole.admin, branch=ba)
    admin_b = mk.user(cb, role=UserRole.admin, branch=bb)
    role_a = Role(name='RA', company_id=ca.id, permissions={})
    role_b = Role(name='RB', company_id=cb.id, permissions={})
    role_g = Role(name='RG', company_id=None, permissions={}, is_system=True)
    db.add_all([role_a, role_b, role_g])
    db.flush()
    return dict(ca=ca, cb=cb, ba=ba, bb=bb, ba_off=ba_off, wa=wa, admin_a=admin_a, admin_b=admin_b,
                role_a=role_a, role_b=role_b, role_g=role_g)


def _phone():
    return f'9988{next(_n):08d}'


def _user_payload(**kw):
    p = {'name': 'Yangi', 'phone': _phone(), 'password': 'secret123', 'role': 'cashier'}
    p.update(kw)
    return p


# ---------- birlik testlar: validate_branch / validate_role ------------------------------------
def test_validate_branch_none_returns_none(db, world):
    assert validate_branch(db, None, world['ca'].id) is None


def test_validate_branch_own_ok(db, world):
    assert validate_branch(db, world['ba'].id, world['ca'].id).id == world['ba'].id


def test_validate_branch_foreign_missing_inactive(db, world):
    for bid in (world['bb'].id, 999999, world['ba_off'].id):
        with pytest.raises(HTTPException) as e:
            validate_branch(db, bid, world['ca'].id)
        assert e.value.status_code == 400 and e.value.detail == BRANCH_INVALID
    # require_active=False — nofaol filial o'tadi, begona baribir yo'q
    assert validate_branch(db, world['ba_off'].id, world['ca'].id, require_active=False).id == world['ba_off'].id
    with pytest.raises(HTTPException):
        validate_branch(db, world['bb'].id, world['ca'].id, require_active=False)


def test_validate_role(db, world):
    ca = world['ca'].id
    assert validate_role(db, None, ca) is None
    assert validate_role(db, world['role_a'].id, ca).id == world['role_a'].id
    assert validate_role(db, world['role_g'].id, ca).id == world['role_g'].id   # global rol
    for rid in (world['role_b'].id, 999999):
        with pytest.raises(HTTPException) as e:
            validate_role(db, rid, ca)
        assert e.value.status_code == 400 and e.value.detail == ROLE_INVALID


# ---------- users --------------------------------------------------------------------------------
def test_create_user_foreign_branch_400_and_no_row(client, db, world):
    w = world
    phone = _phone()
    r = client.login(w['admin_a']).post('/api/users/', json=_user_payload(phone=phone, branch_id=w['bb'].id))
    assert r.status_code == 400 and r.json()['detail'] == BRANCH_INVALID
    assert db.query(User).filter(User.phone == phone).count() == 0


def test_create_user_missing_and_inactive_branch(client, db, world):
    w = world
    for bid in (999999, w['ba_off'].id):
        r = client.login(w['admin_a']).post('/api/users/', json=_user_payload(branch_id=bid))
        assert r.status_code == 400, r.text


def test_create_user_foreign_role_400_global_ok(client, db, world):
    w = world
    r = client.login(w['admin_a']).post('/api/users/', json=_user_payload(role_id=w['role_b'].id))
    assert r.status_code == 400 and r.json()['detail'] == ROLE_INVALID
    r = client.login(w['admin_a']).post('/api/users/', json=_user_payload(role_id=w['role_g'].id))
    assert r.status_code == 201, r.text
    assert r.json()['role_id'] == w['role_g'].id


def test_create_user_own_branch_and_role_ok_and_null_branch_ok(client, db, world):
    w = world
    r = client.login(w['admin_a']).post('/api/users/', json=_user_payload(branch_id=w['ba'].id, role_id=w['role_a'].id))
    assert r.status_code == 201, r.text
    assert r.json()['branch_id'] == w['ba'].id
    r = client.login(w['admin_a']).post('/api/users/', json=_user_payload(branch_id=None))
    assert r.status_code == 201, r.text
    assert r.json()['branch_id'] is None


def test_create_user_existing_phone_branch_validated(client, db, mk, world):
    """Boshqa korxonadagi faol foydalanuvchini qo'shish tarmog'ida ham begona filial jimgina yutilmaydi."""
    w = world
    other = mk.user(w['cb'], role=UserRole.cashier, branch=w['bb'])
    r = client.login(w['admin_a']).post(
        '/api/users/', json=_user_payload(phone=other.phone, branch_id=w['bb'].id, otp_verified_token='x'))
    assert r.status_code == 400 and r.json()['detail'] == BRANCH_INVALID
    assert db.query(UserCompany).filter_by(user_id=other.id, company_id=w['ca'].id).count() == 0


def test_update_user_foreign_branch_400_unchanged(client, db, mk, world):
    w = world
    u = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'branch_id': w['bb'].id})
    assert r.status_code == 400 and r.json()['detail'] == BRANCH_INVALID
    db.expire_all()
    assert db.get(User, u.id).branch_id == w['ba'].id
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'branch_id': 999999})
    assert r.status_code == 400
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'branch_id': w['ba_off'].id})
    assert r.status_code == 400
    db.expire_all()
    assert db.get(User, u.id).branch_id == w['ba'].id


def test_update_user_own_branch_ok_and_null_clears(client, db, mk, world):
    w = world
    # T1.2: 2+ faol filialli korxonada kassir uchun filial majburiy — bo'shatish faqat ixtiyoriy-filialli rolda (manager)
    u = mk.user(w['ca'], role=UserRole.manager)
    other_branch = mk.branch(w['ca'])
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'branch_id': other_branch.id})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, u.id).branch_id == other_branch.id
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'branch_id': None})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, u.id).branch_id is None


def test_update_user_foreign_role_400(client, db, mk, world):
    w = world
    u = mk.user(w['ca'], role=UserRole.cashier, role_id=w['role_a'].id)
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'role_id': w['role_b'].id})
    assert r.status_code == 400 and r.json()['detail'] == ROLE_INVALID
    db.expire_all()
    assert db.get(User, u.id).role_id == w['role_a'].id
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'role_id': w['role_g'].id})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, u.id).role_id == w['role_g'].id


def test_update_user_role_id_null_clears(client, db, mk, world):
    w = world
    u = mk.user(w['ca'], role=UserRole.manager, role_id=w['role_a'].id)
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'role_id': None, 'role': 'cashier'})
    assert r.status_code == 200, r.text
    db.expire_all()
    got = db.get(User, u.id)
    assert got.role_id is None and got.role == UserRole.cashier
    # role_id umuman yuborilmasa — o'zgarmaydi
    got.role_id = w['role_a'].id
    db.flush()
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'name': 'Yangi ism'})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(User, u.id).role_id == w['role_a'].id


def test_update_user_other_company_admin_cannot_set_branch(client, db, mk, world):
    """Bir nechta korxonaga a'zo xodimning branch_id sini ikkinchi korxona admini o'zgartira olmaydi."""
    w = world
    s = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])
    for c in (w['ca'], w['cb']):
        db.add(UserCompany(user_id=s.id, company_id=c.id, role=UserRole.cashier, permissions={}, is_active=True))
    db.flush()
    r = client.login(w['admin_b']).put(f'/api/users/{s.id}', json={'branch_id': w['bb'].id})
    # T1.2: filial korxona bo'yicha (user_companies.branch_id) — B dagi filial B a'zoligiga yoziladi,
    # global users.branch_id (A korxona filiali) o'zgarmaydi
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(User, s.id).branch_id == w['ba'].id
    uc_b = db.query(UserCompany).filter_by(user_id=s.id, company_id=w['cb'].id).one()
    assert uc_b.branch_id == w['bb'].id
    # A korxona filiali (begona) B admini tomonidan baribir berilmaydi
    other_a = mk.branch(w['ca'])
    r = client.login(w['admin_b']).put(f'/api/users/{s.id}', json={'branch_id': other_a.id})
    assert r.status_code == 400, r.text


def test_update_user_other_company_not_member_is_404(client, db, mk, world):
    w = world
    u = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])
    r = client.login(w['admin_b']).put(f'/api/users/{u.id}', json={'branch_id': w['bb'].id})
    assert r.status_code == 404
    db.expire_all()
    assert db.get(User, u.id).branch_id == w['ba'].id


def test_update_user_resave_unchanged_inactive_branch_allowed(client, db, mk, world):
    w = world
    u = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba_off'])
    r = client.login(w['admin_a']).put(f'/api/users/{u.id}', json={'name': 'X', 'branch_id': w['ba_off'].id})
    assert r.status_code == 200, r.text


# ---------- shifts -------------------------------------------------------------------------------
def test_open_shift_branch_validation(client, db, mk, world):
    w = world
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])
    for bid in (w['bb'].id, 999999, w['ba_off'].id):
        r = client.login(cashier).post('/api/shifts/open', json={'branch_id': bid, 'opening_cash': 0})
        assert r.status_code == 400, r.text
        assert r.json()['detail'] == BRANCH_INVALID
    assert db.query(Shift).filter(Shift.cashier_id == cashier.id).count() == 0
    r = client.login(cashier).post('/api/shifts/open', json={'branch_id': w['ba'].id, 'opening_cash': 0})
    assert r.status_code == 201, r.text
    assert r.json()['branch_id'] == w['ba'].id


def test_open_shift_without_branch_uses_user_branch(client, db, mk, world):
    w = world
    cashier = mk.user(w['ca'], role=UserRole.cashier, branch=w['ba'])
    r = client.login(cashier).post('/api/shifts/open', json={'opening_cash': 0})
    assert r.status_code == 201, r.text
    assert r.json()['branch_id'] == w['ba'].id


# ---------- warehouses ---------------------------------------------------------------------------
def test_create_warehouse_branch_validation(client, db, world):
    w = world
    before = db.query(Warehouse).count()
    for bid in (w['bb'].id, 999999, w['ba_off'].id):
        r = client.login(w['admin_a']).post('/api/warehouses', json={'name': 'Yangi', 'branch_id': bid})
        assert r.status_code == 400, r.text
        assert r.json()['detail'] == BRANCH_INVALID
    assert db.query(Warehouse).count() == before
    r = client.login(w['admin_a']).post('/api/warehouses', json={'name': 'Yangi', 'branch_id': w['ba'].id})
    assert r.status_code == 200, r.text
    assert db.get(Warehouse, r.json()['id']).company_id == w['ca'].id
    r = client.login(w['admin_a']).post('/api/warehouses', json={'name': 'Filialsiz'})
    # T1.4: filial berilmasa korxonadagi yagona faol filial (ba; ba_off nofaol) avtomatik beriladi
    assert r.status_code == 200 and r.json()['branch_id'] == w['ba'].id


def test_patch_warehouse_branch_validation(client, db, mk, world):
    w = world
    for bid in (w['bb'].id, 999999, w['ba_off'].id):
        r = client.login(w['admin_a']).patch(f"/api/warehouses/{w['wa'].id}", json={'branch_id': bid})
        assert r.status_code == 400, r.text
    db.expire_all()
    assert db.get(Warehouse, w['wa'].id).branch_id == w['ba'].id
    b2 = mk.branch(w['ca'])
    r = client.login(w['admin_a']).patch(f"/api/warehouses/{w['wa'].id}", json={'branch_id': b2.id, 'name': 'Y'})
    assert r.status_code == 200 and r.json()['name'] == 'Y' and r.json()['branch_id'] == b2.id


def test_patch_warehouse_null_detaches_and_partial_keeps_branch(client, db, world):
    w = world
    r = client.login(w['admin_a']).patch(f"/api/warehouses/{w['wa'].id}", json={'name': 'X'})
    assert r.status_code == 200
    db.expire_all()
    got = db.get(Warehouse, w['wa'].id)
    assert got.name == 'X' and got.branch_id == w['ba'].id
    r = client.login(w['admin_a']).patch(f"/api/warehouses/{w['wa'].id}", json={'branch_id': None})
    assert r.status_code == 200 and r.json()['branch_id'] is None
    db.expire_all()
    got = db.get(Warehouse, w['wa'].id)
    assert got.branch_id is None and got.name == 'X' and got.is_active is True
    # T4.5: name/is_active uchun aniq null — 422 (jim e'tiborsiz qoldirilmaydi), ma'lumot o'zgarmaydi
    r = client.login(w['admin_a']).patch(f"/api/warehouses/{w['wa'].id}", json={'name': None, 'is_active': None})
    assert r.status_code == 422
    db.expire_all()
    got = db.get(Warehouse, w['wa'].id)
    assert got.name == 'X' and got.is_active is True


def test_warehouse_foreign_company_isolated(client, db, world):
    w = world
    r = client.login(w['admin_b']).patch(f"/api/warehouses/{w['wa'].id}", json={'name': 'hack'})
    assert r.status_code == 404
    r = client.login(w['admin_a']).patch(f"/api/warehouses/{w['wa'].id}", json={'name': 'ok'})
    assert r.status_code == 200


def test_super_admin_creates_warehouse_with_branch_company(client, db, mk, world):
    w = world
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post('/api/warehouses', json={'name': 'SA ombor', 'branch_id': w['bb'].id})
    assert r.status_code == 200, r.text
    assert db.get(Warehouse, r.json()['id']).company_id == w['cb'].id
    r = client.login(sa).post('/api/warehouses', json={'name': 'SA ombor 2', 'branch_id': 999999})
    assert r.status_code == 400


# ---------- wallets (finance va kassa) -----------------------------------------------------------
def test_finance_create_wallet_branch_validation(client, db, world):
    w = world
    before = db.query(Wallet).count()
    for bid in (w['bb'].id, 999999, w['ba_off'].id):
        r = client.login(w['admin_a']).post('/api/finance/wallets', json={'name': 'K', 'branch_id': bid})
        assert r.status_code == 400, r.text   # begona/mavjud emas: "Filial topilmadi" (T0.3), nofaol: BRANCH_INVALID
    assert db.query(Wallet).count() == before
    r = client.login(w['admin_a']).post('/api/finance/wallets', json={'name': 'K', 'branch_id': w['ba'].id})
    assert r.status_code in (200, 201), r.text
    assert db.query(Wallet).count() == before + 1


def test_kassa_create_wallet_branch_validation(client, db, world):
    w = world
    before = db.query(Wallet).count()
    for bid in (w['bb'].id, 999999, w['ba_off'].id):
        r = client.login(w['admin_a']).post('/api/kassa', json={'name': 'K', 'branch_id': bid})
        assert r.status_code == 400, r.text
        assert r.json()['detail'] == BRANCH_INVALID
    assert db.query(Wallet).count() == before
    r = client.login(w['admin_a']).post('/api/kassa', json={'name': 'K', 'branch_id': w['ba'].id})
    assert r.status_code in (200, 201), r.text
    assert db.query(Wallet).count() == before + 1


# ---------- global IntegrityError handler --------------------------------------------------------
def test_integrity_error_returns_409(client, db, world):
    from fastapi.routing import APIRoute

    def _boom():
        raise IntegrityError("INSERT ...", {}, Exception("FOREIGN KEY constraint failed"))

    route = APIRoute("/api/__t09_integrity", _boom, methods=["GET"])
    app.router.routes.insert(0, route)
    try:
        r = client.login(world['admin_a']).get("/api/__t09_integrity")
    finally:
        app.router.routes.remove(route)
    assert r.status_code == 409
    assert "bog'lanishi buzildi" in r.json()['detail']
