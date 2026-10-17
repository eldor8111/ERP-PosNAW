"""T0.20 — get_current_user ORM User'ni mutatsiya qilmaydi; /auth/refresh company_id/role saqlaydi."""
import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from app.core.dependencies import get_current_user, get_current_user_allow_expired, require_permissions
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.database import get_db
from app.main import app
from app.models.role import Role
from app.models.user import User, UserRole
from app.models.user_company import UserCompany

import itertools

_n = itertools.count(90000)
_probe = APIRouter(prefix="/__t020")


@_probe.post("/write")
def _write(current_user: User = Depends(get_current_user), db=Depends(get_db)):
    """Yozuvchi endpoint: commit qiladi, so'ng kontekstni qaytaradi."""
    from app.models.company import Company
    db.add(Company(name="Probe", org_code=f"PT{next(_n):05d}"))
    db.commit()
    return {"company_id": current_user.company_id, "role": current_user.role.value}


@_probe.get("/perm")
def _perm(current_user: User = Depends(require_permissions("products", "view"))):
    return {"ok": True}


@_probe.post("/write-expired")
def _write_expired(current_user: User = Depends(get_current_user_allow_expired), db=Depends(get_db)):
    from app.models.company import Company
    db.add(Company(name="Probe2", org_code=f"PT{next(_n):05d}"))
    db.commit()
    return {"company_id": current_user.company_id}


@pytest.fixture
def api(db):
    """Haqiqiy get_current_user bilan (override'siz) TestClient."""
    def _db():
        yield db

    app.include_router(_probe)
    app.dependency_overrides[get_db] = _db
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()
        app.router.routes[:] = [r for r in app.router.routes if not getattr(r, "path", "").startswith("/__t020")]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _access(user, company_id, role):
    claims = {"sub": str(user.id), "role": role.value}
    if company_id is not None:
        claims["company_id"] = company_id
    return create_access_token(claims)


def _refresh(user, company_id=None):
    claims = {"sub": str(user.id)}
    if company_id is not None:
        claims["company_id"] = company_id
    return create_refresh_token(claims)


@pytest.fixture
def multi(db, mk):
    """A da admin (asosiy), B da kassir bo'lgan ko'p korxonali foydalanuvchi."""
    ca, cb = mk.company(), mk.company()
    user = mk.user(ca, role=UserRole.admin, permissions={"orig": {"view": True}})
    db.add_all([
        UserCompany(user_id=user.id, company_id=ca.id, role=UserRole.admin, is_active=True),
        UserCompany(user_id=user.id, company_id=cb.id, role=UserRole.cashier, is_active=True,
                    permissions={"products": {"view": True}}),
    ])
    db.flush()
    return ca, cb, user


def _db_user(db, uid):
    db.expire_all()
    return db.query(User).filter(User.id == uid).one()


def test_write_does_not_persist_token_context(api, db, multi):
    ca, cb, user = multi
    r = api.post("/__t020/write", headers=_bearer(_access(user, cb.id, UserRole.cashier)))
    assert r.status_code == 200, r.text
    # commit'dan keyin ham so'rov davomida kontekst B
    assert r.json() == {"company_id": cb.id, "role": "cashier"}
    u = _db_user(db, user.id)
    assert u.company_id == ca.id
    assert u.role == UserRole.admin
    assert u.permissions == {"orig": {"view": True}}


def test_allow_expired_does_not_persist_token_context(api, db, multi):
    ca, cb, user = multi
    r = api.post("/__t020/write-expired", headers=_bearer(_access(user, cb.id, UserRole.cashier)))
    assert r.status_code == 200, r.text
    assert r.json()["company_id"] == cb.id
    u = _db_user(db, user.id)
    assert (u.company_id, u.role) == (ca.id, UserRole.admin)


def test_role_comes_from_user_company_not_token_claim(api, db, multi):
    ca, cb, user = multi
    # Token'da noto'g'ri (yuqori) rol bo'lsa ham DB'dagi uc.role (cashier) ishlatiladi
    r = api.post("/__t020/write", headers=_bearer(_access(user, cb.id, UserRole.admin)))
    assert r.status_code == 200
    assert r.json()["role"] == "cashier"


def test_foreign_company_token_rejected(api, db, mk, multi):
    ca, cb, user = multi
    other = mk.company()
    r = api.post("/__t020/write", headers=_bearer(_access(user, other.id, UserRole.admin)))
    assert r.status_code == 401


def test_revoked_membership_access_token_401(api, db, multi):
    ca, cb, user = multi
    uc = db.query(UserCompany).filter_by(user_id=user.id, company_id=cb.id).one()
    token = _access(user, cb.id, UserRole.cashier)
    assert api.post("/__t020/write", headers=_bearer(token)).status_code == 200
    uc.is_active = False
    db.flush()
    r = api.post("/__t020/write", headers=_bearer(token))
    assert r.status_code == 401
    assert "bekor qilingan" in r.json()["detail"]


def test_legacy_user_without_user_company_row_works(api, db, mk):
    c = mk.company()
    user = mk.user(c, role=UserRole.manager)
    r = api.post("/__t020/write", headers=_bearer(_access(user, c.id, UserRole.manager)))
    assert r.status_code == 200
    assert r.json() == {"company_id": c.id, "role": "manager"}


def test_refresh_keeps_selected_company_and_role(api, db, multi):
    ca, cb, user = multi
    r = api.post("/api/auth/refresh", json={"refresh_token": _refresh(user, cb.id)})
    assert r.status_code == 200, r.text
    body = r.json()
    acc = decode_token(body["access_token"])
    assert acc["company_id"] == cb.id and acc["role"] == "cashier"
    assert decode_token(body["refresh_token"])["company_id"] == cb.id
    assert body["user"]["company_id"] == cb.id and body["user"]["role"] == "cashier"
    # DB'dagi users qatori o'zgarmagan
    u = _db_user(db, user.id)
    assert (u.company_id, u.role) == (ca.id, UserRole.admin)
    # /auth/me yangi token bilan B kontekstida
    me = api.get("/api/auth/me", headers=_bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["company_id"] == cb.id and me.json()["role"] == "cashier"
    # ikkinchi marta yangilash ham B'da qoladi
    r2 = api.post("/api/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert r2.status_code == 200
    assert decode_token(r2.json()["access_token"])["company_id"] == cb.id


def test_refresh_revoked_membership_401(api, db, multi):
    ca, cb, user = multi
    db.query(UserCompany).filter_by(user_id=user.id, company_id=cb.id).one().is_active = False
    db.flush()
    r = api.post("/api/auth/refresh", json={"refresh_token": _refresh(user, cb.id)})
    assert r.status_code == 401


def test_refresh_foreign_company_401(api, db, mk, multi):
    ca, cb, user = multi
    other = mk.company()
    r = api.post("/api/auth/refresh", json={"refresh_token": _refresh(user, other.id)})
    assert r.status_code == 401


def test_refresh_old_token_without_company_claim_still_works(api, db, multi):
    ca, cb, user = multi
    r = api.post("/api/auth/refresh", json={"refresh_token": _refresh(user)})
    assert r.status_code == 200, r.text
    body = r.json()
    acc = decode_token(body["access_token"])
    assert acc["role"] == "admin"
    assert body["user"]["company_id"] == ca.id
    # yangi refresh token endi korxona claim'ini ko'taradi
    assert decode_token(body["refresh_token"]).get("company_id") == ca.id


def test_refresh_mobile_role_in_selected_company_rejected(api, db, mk):
    ca, cb = mk.company(), mk.company()
    user = mk.user(ca, role=UserRole.admin)
    db.add_all([
        UserCompany(user_id=user.id, company_id=ca.id, role=UserRole.admin, is_active=True),
        UserCompany(user_id=user.id, company_id=cb.id, role=UserRole.courier, is_active=True),
    ])
    db.flush()
    assert api.post("/api/auth/refresh", json={"refresh_token": _refresh(user, cb.id)}).status_code == 401
    assert api.post("/api/auth/refresh", json={"refresh_token": _refresh(user, ca.id)}).status_code == 200


def test_custom_role_permission_check_no_detached_error(api, db, mk):
    c = mk.company()
    role = Role(name="Ombor nazoratchisi", company_id=c.id, permissions={"products": {"view": True}})
    db.add(role)
    db.flush()
    user = mk.user(c, role=UserRole.cashier, role_id=role.id)
    db.expire_all()
    token = _access(user, c.id, UserRole.cashier)
    r = api.get("/__t020/perm", headers=_bearer(token))
    assert r.status_code == 200, r.text
    # ruxsati yo'q dinamik rol -> 403 (500 emas)
    role2 = Role(name="Bosh", company_id=c.id, permissions={})
    db.add(role2)
    db.flush()
    user2 = mk.user(c, role=UserRole.cashier, role_id=role2.id)
    db.expire_all()
    assert api.get("/__t020/perm", headers=_bearer(_access(user2, c.id, UserRole.cashier))).status_code == 403


def test_tenant_isolation_own_company_ok_other_company_denied(api, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, _, _, ub = mk.tenant()
    # o'z korxonasi ishlaydi
    assert api.post("/__t020/write", headers=_bearer(_access(ua, ca.id, UserRole.admin))).status_code == 200
    # A foydalanuvchisi B korxonasi tokenini yasab ham kira olmaydi
    assert api.post("/__t020/write", headers=_bearer(_access(ua, cb.id, UserRole.admin))).status_code == 401
    assert api.post("/__t020/write", headers=_bearer(_access(ub, cb.id, UserRole.admin))).status_code == 200
