"""T0.37 — Super admin GET /super-admin/users?company_id=X filtri."""
from app.models.user import UserRole
from app.models.user_company import UserCompany


def _super(mk):
    return mk.user(None, role=UserRole.super_admin)


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return [u["id"] for u in resp.json()]


def test_filialsiz_korxona_faqat_oz_foydalanuvchilari(db, mk, client):
    sa = _super(mk)
    a = mk.company()                       # filialsiz
    ua = mk.user(a, role=UserRole.admin)
    cb, bb, _w, ub = mk.tenant()
    ids = _ids(client.login(sa).get(f"/api/super-admin/users?company_id={a.id}"))
    assert ids == [ua.id]
    assert ub.id not in ids and sa.id not in ids


def test_boshqa_korxona_faqat_oz_foydalanuvchilari(db, mk, client):
    sa = _super(mk)
    a = mk.company()
    mk.user(a)
    cb, bb, _w, ub = mk.tenant()
    ids = _ids(client.login(sa).get(f"/api/super-admin/users?company_id={cb.id}"))
    assert ids == [ub.id]


def test_user_companies_orqali_azo_dublikatsiz(db, mk, client):
    sa = _super(mk)
    a = mk.company()
    ca, ba, _w, ua = mk.tenant()
    cb, bb, _w2, ub = mk.tenant()
    # ub A ga ham a'zo; ua o'z korxonasida ham user_companies qatoriga ega
    db.add(UserCompany(user_id=ub.id, company_id=ca.id, role=UserRole.cashier))
    db.add(UserCompany(user_id=ua.id, company_id=ca.id, role=UserRole.admin))
    db.flush()
    c = client.login(sa)
    ids_a = _ids(c.get(f"/api/super-admin/users?company_id={ca.id}"))
    ids_b = _ids(c.get(f"/api/super-admin/users?company_id={cb.id}"))
    assert sorted(ids_a) == sorted([ua.id, ub.id])
    assert len(ids_a) == len(set(ids_a))
    assert ids_b == [ub.id]


def test_mavjud_bolmagan_korxona_404(db, mk, client):
    sa = _super(mk)
    r = client.login(sa).get("/api/super-admin/users?company_id=999999")
    assert r.status_code == 404
    assert "Korxona topilmadi" in r.text


def test_company_id_siz_hamma_va_role_branch_filtrlari(db, mk, client):
    sa = _super(mk)
    ca, ba, _w, ua = mk.tenant()
    cb, bb, _w2, ub = mk.tenant()
    mgr = mk.user(ca, role=UserRole.manager, branch=ba)
    c = client.login(sa)
    ids = _ids(c.get("/api/super-admin/users"))
    assert {sa.id, ua.id, ub.id, mgr.id} <= set(ids)
    assert _ids(c.get("/api/super-admin/users?role=manager")) == [mgr.id]
    assert sorted(_ids(c.get(f"/api/super-admin/users?branch_id={ba.id}"))) == sorted([ua.id, mgr.id])
    # company_id + role AND sifatida
    assert _ids(c.get(f"/api/super-admin/users?company_id={ca.id}&role=manager")) == [mgr.id]
    assert _ids(c.get(f"/api/super-admin/users?company_id={cb.id}&role=manager")) == []


def test_super_admin_bolmagan_403(db, mk, client):
    c, b, _w, admin = mk.tenant()
    r = client.login(admin).get(f"/api/super-admin/users?company_id={c.id}")
    assert r.status_code == 403
