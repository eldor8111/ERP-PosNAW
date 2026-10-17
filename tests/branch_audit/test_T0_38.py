"""T0.38 — bir nechta korxonada ishlaydigan umumiy foydalanuvchini boshqa korxona admini o'zgartira olmaydi.

Parol/telefon/email/ism/global status/role_id/branch_id faqat egasi o'zi yoki super_admin;
boshqa korxona admini faqat o'z korxonasidagi UserCompany (role, permissions, is_active) ni o'zgartiradi.
"""
import pytest

from app.core.dependencies import _load_context_user
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole, UserStatus
from app.models.user_company import UserCompany


@pytest.fixture
def world(db, mk):
    """A va B korxona; A da egasi bo'lgan `shared` foydalanuvchi B ga ham a'zo; B admini."""
    ca = mk.company()
    cb = mk.company()
    ba = mk.branch(ca)
    bb = mk.branch(cb)
    admin_a = mk.user(ca, role=UserRole.admin, branch=ba)
    admin_b = mk.user(cb, role=UserRole.admin, branch=bb)
    shared = mk.user(ca, role=UserRole.cashier, branch=ba, email='shared@a.uz', hashed_password='ORIGINAL-HASH')
    only_b = mk.user(cb, role=UserRole.cashier, branch=bb, email='onlyb@b.uz', hashed_password='B-HASH')
    for u, c, r in ((admin_a, ca, UserRole.admin), (admin_b, cb, UserRole.admin),
                    (shared, ca, UserRole.cashier), (shared, cb, UserRole.cashier),
                    (only_b, cb, UserRole.cashier)):
        db.add(UserCompany(user_id=u.id, company_id=c.id, role=r, permissions={}, is_active=True))
    db.flush()
    return dict(ca=ca, cb=cb, ba=ba, bb=bb, admin_a=admin_a, admin_b=admin_b, shared=shared, only_b=only_b)


def _uc(db, user, company):
    db.expire_all()
    return db.query(UserCompany).filter_by(user_id=user.id, company_id=company.id).one()


def _full_payload(u):
    """Frontend butun payloadni yuboradi — mavjud qiymatlar o'zgarmagan holda."""
    return {'name': u.name, 'phone': u.phone, 'email': u.email, 'role': u.role.value,
            'permissions': u.permissions or {}, 'branch_id': u.branch_id}


# ---- 1. parol ----------------------------------------------------------------------------
def test_other_company_admin_cannot_change_shared_password(client, db, world):
    w = world
    r = client.login(w['admin_b']).patch(f"/api/users/{w['shared'].id}/password", json={'new_password': 'hacked123'})
    assert r.status_code == 403
    assert 'Parolni faqat o\'zi' in r.json()['detail']
    db.expire_all()
    assert db.get(User, w['shared'].id).hashed_password == 'ORIGINAL-HASH'
    denied = db.query(AuditLog).filter_by(action='USER_SHARED_EDIT_DENIED', entity_id=w['shared'].id).count()
    assert denied == 1


def test_home_company_admin_also_cannot_change_shared_password(client, db, world):
    w = world
    r = client.login(w['admin_a']).patch(f"/api/users/{w['shared'].id}/password", json={'new_password': 'hacked123'})
    assert r.status_code == 403
    db.expire_all()
    assert db.get(User, w['shared'].id).hashed_password == 'ORIGINAL-HASH'


# ---- 2. shaxsiy maydonlar ----------------------------------------------------------------
@pytest.mark.parametrize('field,value', [('phone', '998900000001'), ('email', 'new@x.uz'), ('name', 'Boshqa Ism')])
def test_shared_personal_field_change_forbidden(client, db, world, field, value):
    w = world
    before = (w['shared'].name, w['shared'].phone, w['shared'].email)
    r = client.login(w['admin_b']).put(f"/api/users/{w['shared'].id}", json={field: value})
    assert r.status_code == 403
    assert 'Shaxsiy ma\'lumotlarni faqat o\'zi' in r.json()['detail']
    db.expire_all()
    u = db.get(User, w['shared'].id)
    assert (u.name, u.phone, u.email) == before


def test_shared_unchanged_full_payload_ok(client, db, world):
    w = world
    s = w['shared']
    payload = _full_payload(s)
    payload['phone'] = '+' + s.phone          # normallashtirilgach teng
    payload['branch_id'] = s.branch_id
    r = client.login(w['admin_b']).put(f"/api/users/{s.id}", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()['is_shared'] is True
    db.expire_all()
    u = db.get(User, s.id)
    assert u.phone == s.phone and u.email == 'shared@a.uz' and u.branch_id == w['ba'].id


# ---- 3. status ---------------------------------------------------------------------------
def test_shared_status_inactive_only_affects_this_company(client, db, world):
    w = world
    s = w['shared']
    r = client.login(w['admin_b']).put(f"/api/users/{s.id}", json={'status': 'inactive'})
    assert r.status_code == 200, r.text
    assert _uc(db, s, w['cb']).is_active is False
    assert _uc(db, s, w['ca']).is_active is True
    assert db.get(User, s.id).status == UserStatus.active
    # A korxonaga kirish saqlanadi (token konteksti ishlaydi)
    ctx = _load_context_user(db, {'sub': str(s.id), 'company_id': w['ca'].id})
    assert ctx.company_id == w['ca'].id


# ---- 4. rol ------------------------------------------------------------------------------
def test_shared_role_and_permissions_only_user_company(client, db, world):
    w = world
    s = w['shared']
    r = client.login(w['admin_b']).put(f"/api/users/{s.id}", json={'role': 'manager', 'permissions': {'x': {'view': True}}})
    assert r.status_code == 200, r.text
    assert _uc(db, s, w['cb']).role == UserRole.manager
    assert _uc(db, s, w['cb']).permissions == {'x': {'view': True}}
    assert _uc(db, s, w['ca']).role == UserRole.cashier
    u = db.get(User, s.id)
    assert u.role == UserRole.cashier
    assert not u.permissions


def test_shared_role_without_membership_row_404(client, db, world):
    """Uy korxonasi B, a'zolik qatori yo'q, A da faol: B admini rol bera olmaydi (uc yo'q -> 404)."""
    w = world
    s = w['shared']
    db.query(UserCompany).filter_by(user_id=s.id, company_id=w['cb'].id).delete()
    s.company_id = w['cb'].id
    db.flush()
    r = client.login(w['admin_b']).put(f"/api/users/{s.id}", json={'role': 'manager'})
    assert r.status_code == 404


# ---- 5. filial / role_id -----------------------------------------------------------------
def test_shared_branch_change_only_in_own_company(client, db, world):
    """T1.2: filial endi korxona bo'yicha (user_companies.branch_id) — B admini B dagi filialni o'zgartira
    oladi, lekin global users.branch_id (A korxona filiali) o'zgarmaydi."""
    w = world
    s = w['shared']
    r = client.login(w['admin_b']).put(f"/api/users/{s.id}", json={'branch_id': w['bb'].id})
    assert r.status_code == 200, r.text
    assert r.json()['branch_id'] == w['bb'].id
    assert _uc(db, s, w['cb']).branch_id == w['bb'].id
    assert db.get(User, s.id).branch_id == w['ba'].id
    r = client.login(w['admin_b']).put(f"/api/users/{s.id}", json={'branch_id': None})
    assert r.status_code == 200, r.text
    assert _uc(db, s, w['cb']).branch_id is None
    db.expire_all()
    assert db.get(User, s.id).branch_id == w['ba'].id


# ---- 6. toggle-status --------------------------------------------------------------------
def test_toggle_shared_only_flips_user_company(client, db, world):
    w = world
    s = w['shared']
    r = client.login(w['admin_b']).post(f"/api/users/{s.id}/toggle-status")
    assert r.status_code == 200, r.text
    assert r.json() == {'ok': True, 'status': 'inactive'}
    assert _uc(db, s, w['cb']).is_active is False
    assert _uc(db, s, w['ca']).is_active is True
    assert db.get(User, s.id).status == UserStatus.active
    r = client.login(w['admin_b']).post(f"/api/users/{s.id}/toggle-status")
    assert r.json() == {'ok': True, 'status': 'active'}
    assert _uc(db, s, w['cb']).is_active is True


def test_toggle_non_member_forbidden(client, db, world):
    w = world
    r = client.login(w['admin_a']).post(f"/api/users/{w['only_b'].id}/toggle-status")
    assert r.status_code == 403
    db.expire_all()
    assert db.get(User, w['only_b'].id).status == UserStatus.active


# ---- 7. regressiya -----------------------------------------------------------------------
def test_single_company_user_works_as_before(client, db, world):
    w = world
    o = w['only_b']
    c = client.login(w['admin_b'])
    r = c.put(f"/api/users/{o.id}", json={'name': 'Yangi Ism', 'phone': '998901112233', 'email': 'n@b.uz',
                                          'role': 'manager', 'branch_id': w['bb'].id})
    assert r.status_code == 200, r.text
    assert r.json()['is_shared'] is False
    db.expire_all()
    u = db.get(User, o.id)
    assert (u.name, u.phone, u.email, u.role) == ('Yangi Ism', '998901112233', 'n@b.uz', UserRole.manager)
    assert _uc(db, o, w['cb']).role == UserRole.manager
    assert c.patch(f"/api/users/{o.id}/password", json={'new_password': 'newpass123'}).status_code == 204
    db.expire_all()
    assert db.get(User, o.id).hashed_password != 'B-HASH'
    r = c.post(f"/api/users/{o.id}/toggle-status")
    assert r.json() == {'ok': True, 'status': 'inactive'}
    assert db.get(User, o.id).status == UserStatus.inactive


def test_super_admin_can_edit_shared_user(client, db, world, mk):
    w = world
    sa = mk.user(None, role=UserRole.super_admin)
    c = client.login(sa)
    assert c.put(f"/api/users/{w['shared'].id}", json={'phone': '998907654321'}).status_code == 200
    assert c.patch(f"/api/users/{w['shared'].id}/password", json={'new_password': 'saPass123'}).status_code == 204
    db.expire_all()
    u = db.get(User, w['shared'].id)
    assert u.phone == '998907654321' and u.hashed_password != 'ORIGINAL-HASH'


def test_user_can_change_own_password_and_profile(client, db, world):
    w = world
    me = w['admin_b']
    db.add(UserCompany(user_id=me.id, company_id=w['ca'].id, role=UserRole.admin, permissions={}, is_active=True))
    db.flush()
    c = client.login(me)
    assert c.patch(f"/api/users/{me.id}/password", json={'new_password': 'mine12345'}).status_code == 204
    r = c.put(f"/api/users/{me.id}", json={'name': 'Men O\'zim'})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(User, me.id).name == 'Men O\'zim'


# ---- 8. delete_user ----------------------------------------------------------------------
def test_delete_shared_only_deactivates_membership(client, db, world):
    w = world
    s = w['shared']
    r = client.login(w['admin_b']).delete(f"/api/users/{s.id}")
    assert r.status_code == 204
    assert _uc(db, s, w['cb']).is_active is False
    assert _uc(db, s, w['ca']).is_active is True
    assert db.get(User, s.id).status == UserStatus.active


def test_delete_single_company_user_deactivates_globally(client, db, world):
    w = world
    r = client.login(w['admin_b']).delete(f"/api/users/{w['only_b'].id}")
    assert r.status_code == 204
    db.expire_all()
    assert db.get(User, w['only_b'].id).status == UserStatus.inactive


# ---- izolyatsiya va is_shared ------------------------------------------------------------
def test_cross_company_isolation(client, db, world):
    w = world
    c = client.login(w['admin_a'])
    o = w['only_b']
    assert c.put(f"/api/users/{o.id}", json={'name': 'X'}).status_code == 404
    assert c.patch(f"/api/users/{o.id}/password", json={'new_password': 'hacked123'}).status_code == 404
    assert c.get(f"/api/users/{o.id}").status_code == 404
    db.expire_all()
    assert db.get(User, o.id).hashed_password == 'B-HASH'


def test_is_shared_flag_in_list_and_detail(client, db, world):
    w = world
    c = client.login(w['admin_b'])
    rows = {u['id']: u for u in c.get('/api/users/').json()}
    assert rows[w['shared'].id]['is_shared'] is True
    assert rows[w['only_b'].id]['is_shared'] is False
    assert c.get(f"/api/users/{w['shared'].id}").json()['is_shared'] is True
    assert c.get(f"/api/users/{w['only_b'].id}").json()['is_shared'] is False
