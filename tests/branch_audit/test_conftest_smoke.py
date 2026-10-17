"""Umumiy test muhitining o'zi ishlashini tekshiradi (ikki korxona, izolyatsiya, client.login)."""
from app.models.user import UserRole


def test_maker_builds_two_tenants(mk):
    c1, b1, w1, u1 = mk.tenant()
    c2, b2, w2, u2 = mk.tenant(role=UserRole.cashier)
    assert c1.id != c2.id and b1.company_id == c1.id and w2.branch_id == b2.id
    assert u1.company_id == c1.id and u2.role == UserRole.cashier


def test_rows_do_not_leak_between_tests(db):
    from app.models.company import Company
    assert db.query(Company).count() == 0


def test_client_login_and_branches_endpoint(client, mk):
    c1, b1, w1, u1 = mk.tenant()
    c2, b2, w2, u2 = mk.tenant()
    r = client.login(u1).get('/api/branches/')
    assert r.status_code == 200, r.text
    ids = {x['id'] for x in r.json()}
    assert b1.id in ids and b2.id not in ids
