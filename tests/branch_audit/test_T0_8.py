"""T0.8 — Branch PATCH/CRUD xavfsizligi va tarif limiti."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Query

from app.models.audit_log import AuditLog
from app.models.billing import Tariff
from app.models.branch import Branch
from app.models.user import UserRole
from app.schemas.branch import BranchUpdate
from app.utils.tariff_check import check_branch_limit


def _tariff(db, company, max_branches=1, active=True):
    t = Tariff(name="Test tarif", max_branches=1)
    db.add(t)
    db.flush()
    if max_branches is None:
        db.execute(text("UPDATE tariffs SET max_branches = NULL WHERE id = :i"), {"i": t.id})
        db.expire(t)
    else:
        t.max_branches = max_branches
    company.tariff_id = t.id
    delta = timedelta(days=10) if active else -timedelta(days=10)
    company.subscription_ends_at = datetime.now(timezone.utc) + delta
    db.flush()
    db.refresh(company)
    return t


def _logs(db, action, branch_id):
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "branch", AuditLog.action == action, AuditLog.entity_id == branch_id)
        .all()
    )


def test_schema_has_no_company_id():
    assert "company_id" not in BranchUpdate.model_fields
    # eski klient company_id yuborsa xato bo'lmaydi, maydon e'tiborsiz
    assert "company_id" not in BranchUpdate(name="x", company_id=5).model_dump(exclude_unset=True)


def test_patch_company_id_ignored(client, db, mk):
    a, ba, _, ua = mk.tenant()
    b, _, _, _ = mk.tenant()
    r = client.login(ua).patch(f"/api/branches/{ba.id}", json={"company_id": b.id, "name": "Yangi nom"})
    assert r.status_code == 200
    db.expire_all()
    got = db.get(Branch, ba.id)
    assert got.company_id == a.id
    assert got.name == "Yangi nom"


def test_patch_other_company_branch_404(client, db, mk):
    a, ba, _, ua = mk.tenant()
    b, bb, _, ub = mk.tenant()
    r = client.login(ua).patch(f"/api/branches/{bb.id}", json={"name": "Hack"})
    assert r.status_code == 404
    db.expire_all()
    assert db.get(Branch, bb.id).name != "Hack"
    # o'z filiali ishlaydi
    assert client.login(ub).patch(f"/api/branches/{bb.id}", json={"name": "Ok"}).status_code == 200


def test_reactivate_blocked_by_limit(client, db, mk):
    a, ba, _, ua = mk.tenant()
    _tariff(db, a, max_branches=1)
    off = mk.branch(a, is_active=False)
    r = client.login(ua).patch(f"/api/branches/{off.id}", json={"is_active": True})
    assert r.status_code == 403
    assert "maksimal filiallar soni" in r.json()["detail"]
    db.expire_all()
    assert db.get(Branch, off.id).is_active is False
    assert db.query(Branch).filter(Branch.company_id == a.id, Branch.is_active == True).count() == 1


def test_reactivate_allowed_within_limit(client, db, mk):
    a, ba, _, ua = mk.tenant()
    _tariff(db, a, max_branches=2)
    off = mk.branch(a, is_active=False)
    r = client.login(ua).patch(f"/api/branches/{off.id}", json={"is_active": True})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Branch, off.id).is_active is True


def test_deactivate_and_active_noop_do_not_check_limit(client, db, mk):
    a, ba, _, ua = mk.tenant()
    _tariff(db, a, max_branches=1)
    # allaqachon faol filialga is_active=true — limit tekshirilmaydi
    assert client.login(ua).patch(f"/api/branches/{ba.id}", json={"is_active": True}).status_code == 200
    assert client.login(ua).patch(f"/api/branches/{ba.id}", json={"is_active": False}).status_code == 200


def test_null_max_branches_no_typeerror(client, db, mk):
    a, ba, _, ua = mk.tenant()
    _tariff(db, a, max_branches=None)
    # default 1: bitta faol bor -> POST 403
    r = client.login(ua).post("/api/branches", json={"name": "Yangi"})
    assert r.status_code == 403
    off = mk.branch(a, is_active=False)
    assert client.login(ua).patch(f"/api/branches/{off.id}", json={"is_active": True}).status_code == 403
    # faol filial bo'lmasa -> ruxsat
    ba.is_active = False
    db.flush()
    assert client.login(ua).patch(f"/api/branches/{off.id}", json={"is_active": True}).status_code == 200


def test_check_branch_limit_unit(db, mk):
    # tarif yo'q -> default 1
    c, b, _, u = mk.tenant()
    with pytest.raises(HTTPException) as e:
        check_branch_limit(db, c.id, u)
    assert e.value.status_code == 403
    # exclude_branch_id sanashdan chiqaradi
    check_branch_limit(db, c.id, u, exclude_branch_id=b.id)
    # muddati o'tgan obuna -> default 1
    c2, _, _, u2 = mk.tenant()
    _tariff(db, c2, max_branches=5, active=False)
    with pytest.raises(HTTPException):
        check_branch_limit(db, c2.id, u2)
    # super admin cheklanmaydi
    sa = mk.user(None, role=UserRole.super_admin)
    check_branch_limit(db, c.id, sa)


def test_limit_locks_company_row(db, mk, monkeypatch):
    """Parallel so'rovlardan himoya: korxona qatori with_for_update bilan qulflanadi."""
    c, _, _, u = mk.tenant()
    _tariff(db, c, max_branches=5)
    calls = []
    orig = Query.with_for_update

    def spy(self, *a, **k):
        calls.append(1)
        return orig(self, *a, **k)

    monkeypatch.setattr(Query, "with_for_update", spy)
    check_branch_limit(db, c.id, u)
    assert calls


def test_sequential_posts_only_first_succeeds(client, db, mk):
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    _tariff(db, c, max_branches=1)
    r1 = client.login(u).post("/api/branches", json={"name": "F1"})
    r2 = client.login(u).post("/api/branches", json={"name": "F2"})
    assert (r1.status_code, r2.status_code) == (200, 403)
    assert db.query(Branch).filter(Branch.company_id == c.id, Branch.is_active == True).count() == 1


def test_create_forces_own_company(client, db, mk):
    a, _, _, ua = mk.tenant()
    b, _, _, _ = mk.tenant()
    _tariff(db, a, max_branches=3)
    r = client.login(ua).post("/api/branches", json={"name": "Yangi", "company_id": b.id})
    assert r.status_code == 200
    assert r.json()["company_id"] == a.id


def test_super_admin_create_requires_company(client, db, mk):
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post("/api/branches", json={"name": "Yetim"})
    assert r.status_code == 400
    r = client.login(sa).post("/api/branches", json={"name": "X", "company_id": 999999})
    assert r.status_code == 404
    c = mk.company()
    r = client.login(sa).post("/api/branches", json={"name": "Ok", "company_id": c.id})
    assert r.status_code == 200
    assert r.json()["company_id"] == c.id


def test_audit_log_create_update_delete(client, db, mk):
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    _tariff(db, c, max_branches=2)
    cl = client.login(u)
    bid = cl.post("/api/branches", json={"name": "Audit"}).json()["id"]
    assert len(_logs(db, "CREATE", bid)) == 1
    assert cl.patch(f"/api/branches/{bid}", json={"name": "Audit2"}).status_code == 200
    up = _logs(db, "UPDATE", bid)
    assert len(up) == 1
    assert up[0].old_values["name"] == "Audit" and up[0].new_values["name"] == "Audit2"
    assert up[0].user_id == u.id
    assert cl.delete(f"/api/branches/{bid}").status_code == 204
    assert len(_logs(db, "DELETE", bid)) == 1


def test_patch_null_clears_address_phone(client, db, mk):
    a, ba, _, ua = mk.tenant()
    ba.address = "Manzil"
    ba.phone = "123"
    db.flush()
    r = client.login(ua).patch(f"/api/branches/{ba.id}", json={"address": None, "phone": None})
    assert r.status_code == 200
    db.expire_all()
    got = db.get(Branch, ba.id)
    assert got.address is None and got.phone is None
    assert got.name == ba.name


def test_patch_empty_name_400(client, db, mk):
    a, ba, _, ua = mk.tenant()
    old = ba.name
    for body in ({"name": ""}, {"name": "   "}, {"name": None}):
        assert client.login(ua).patch(f"/api/branches/{ba.id}", json=body).status_code == 400
    db.expire_all()
    assert db.get(Branch, ba.id).name == old
