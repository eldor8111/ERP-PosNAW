"""T0.21 — bin_locations korxona/omborga bog'langan, rol cheklovi bor."""
import pytest

from app.models.bin_location import BinLocation
from app.models.user import UserRole

URL = '/api/bin-locations'


def _bl(db, company, code='A-1', warehouse=None, active=True, label=None):
    b = BinLocation(company_id=company.id, warehouse_id=warehouse.id if warehouse else None,
                    code=code, label=label, is_active=active)
    db.add(b)
    db.flush()
    return b


def test_list_isolated(client, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, _, _, ub = mk.tenant()
    _bl(db, ca, 'A-1')
    _bl(db, cb, 'B-9')
    r = client.login(ua).get(URL)
    assert r.status_code == 200
    assert [x['code'] for x in r.json()] == ['A-1']


def test_put_delete_foreign_404(client, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, _, _, _ = mk.tenant()
    foreign = _bl(db, cb, 'B-1', label='asl')
    c = client.login(ua)
    assert c.put(f'{URL}/{foreign.id}', json={'label': 'buzildi'}).status_code == 404
    assert c.delete(f'{URL}/{foreign.id}').status_code == 404
    db.refresh(foreign)
    assert foreign.label == 'asl' and foreign.is_active is True


def test_same_code_two_companies_and_dup(client, db, mk):
    ca, ba, wa, ua = mk.tenant()
    cb, _, _, ub = mk.tenant()
    assert client.login(ua).post(URL, json={'code': 'A-1'}).status_code == 200
    assert client.login(ub).post(URL, json={'code': 'A-1'}).status_code == 200
    r = client.login(ua).post(URL, json={'code': 'A-1'})
    assert r.status_code == 400
    # boshqa omborda ruxsat
    r = client.login(ua).post(URL, json={'code': 'A-1', 'warehouse_id': wa.id})
    assert r.status_code == 200
    assert r.json()['warehouse_id'] == wa.id and r.json()['warehouse_name'] == wa.name
    assert client.login(ua).post(URL, json={'code': 'A-1', 'warehouse_id': wa.id}).status_code == 400
    # ro'yxat warehouse_id filtri
    r = client.login(ua).get(URL, params={'warehouse_id': wa.id})
    assert [x['warehouse_id'] for x in r.json()] == [wa.id]


@pytest.mark.parametrize('role', [UserRole.cashier, UserRole.courier, UserRole.accountant])
def test_write_roles_forbidden(client, db, mk, role):
    c, b, w, admin = mk.tenant()
    u = mk.user(c, role=role, branch=b)
    bl = _bl(db, c, 'X-1')
    cl = client.login(u)
    assert cl.post(URL, json={'code': 'N-1'}).status_code == 403
    assert cl.put(f'{URL}/{bl.id}', json={'label': 'q'}).status_code == 403
    assert cl.delete(f'{URL}/{bl.id}').status_code == 403
    assert cl.get(URL).status_code == 200  # o'qish ochiq


@pytest.mark.parametrize('role', [UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager])
def test_write_roles_allowed(client, db, mk, role):
    c = mk.company()
    b = mk.branch(c)
    u = mk.user(c, role=role, branch=b)
    cl = client.login(u)
    r = cl.post(URL, json={'code': 'N-1', 'label': 'x'})
    assert r.status_code == 200
    bid = r.json()['id']
    assert cl.put(f'{URL}/{bid}', json={'label': 'y'}).json()['label'] == 'y'
    assert cl.delete(f'{URL}/{bid}').status_code == 204
    assert cl.get(URL).json() == []


def test_foreign_or_inactive_warehouse_404(client, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, bb, wb, _ = mk.tenant()
    inactive = mk.warehouse(ca, is_active=False)
    c = client.login(ua)
    assert c.post(URL, json={'code': 'Z-1', 'warehouse_id': wb.id}).status_code == 404
    assert c.post(URL, json={'code': 'Z-1', 'warehouse_id': inactive.id}).status_code == 404
    own = _bl(db, ca, 'Z-2')
    assert c.put(f'{URL}/{own.id}', json={'warehouse_id': wb.id}).status_code == 404


def test_foreign_inactive_not_reactivated(client, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, _, _, _ = mk.tenant()
    foreign = _bl(db, cb, 'A-1', active=False, label='begona')
    r = client.login(ua).post(URL, json={'code': 'A-1', 'label': 'mening'})
    assert r.status_code == 200 and r.json()['id'] != foreign.id
    db.refresh(foreign)
    assert foreign.is_active is False and foreign.label == 'begona'


def test_own_inactive_reactivated(client, db, mk):
    ca, _, _, ua = mk.tenant()
    own = _bl(db, ca, 'A-1', active=False, label='eski')
    r = client.login(ua).post(URL, json={'code': 'A-1', 'label': 'yangi'})
    assert r.status_code == 200 and r.json()['id'] == own.id and r.json()['label'] == 'yangi'


def test_update_duplicate_400_and_clear_warehouse(client, db, mk):
    ca, _, wa, ua = mk.tenant()
    a1 = _bl(db, ca, 'A-1')
    a2 = _bl(db, ca, 'A-2')
    c = client.login(ua)
    assert c.put(f'{URL}/{a2.id}', json={'code': 'A-1'}).status_code == 400
    # omborga ko'chirish mumkin, keyin qaytarish (null)
    r = c.put(f'{URL}/{a2.id}', json={'warehouse_id': wa.id})
    assert r.status_code == 200 and r.json()['warehouse_id'] == wa.id
    r = c.put(f'{URL}/{a2.id}', json={'warehouse_id': None})
    assert r.status_code == 200 and r.json()['warehouse_id'] is None


def test_blank_and_long_code_422(client, db, mk):
    _, _, _, ua = mk.tenant()
    c = client.login(ua)
    assert c.post(URL, json={'code': '  '}).status_code == 422
    assert c.post(URL, json={'code': 'x' * 51}).status_code == 422
    r = c.post(URL, json={'code': '  B-1  '})
    assert r.status_code == 200 and r.json()['code'] == 'B-1'


def test_no_company_user(client, db, mk):
    u = mk.user(None, role=UserRole.super_admin)
    c = client.login(u)
    assert c.get(URL).json() == []
    r = c.post(URL, json={'code': 'S-1'})
    assert r.status_code == 400 and 'Korxona' in r.json()['detail']
