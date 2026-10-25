"""Korxonani o'chirish: matnli PK li jadval (pending_actions.id VARCHAR).

Vaqtinchalik "o'chirish to'plami" jadvali ustuni BIGINT edi — PostgreSQL VARCHAR qiymatni unga yozmaydi (42804),
shuning uchun serverda delete-preview va o'chirish har qanday korxonada 500 berardi (SQLite turga qaramaydi).
Endi ustun turi jadval PK'siga mos: butun son — BIGINT, matn — TEXT.
"""
from datetime import datetime, timedelta, timezone

from app.models.pending_action import PendingAction
from app.models.user import UserRole
from app.services.company_purge import _Purger, preview_company_purge_ex, purge_company


def _action(db, company, user, aid):
    now = datetime.now(timezone.utc)
    db.add(PendingAction(id=aid, company_id=company.id, user_id=user.id, tool_name="t", tool_arguments={},
                         status="pending", created_at=now, expires_at=now + timedelta(hours=1)))
    db.flush()


def test_temp_set_id_type_follows_primary_key(db, mk):
    x, _b, _wh, _admin = mk.tenant()
    p = _Purger(db, x.id)
    assert p._id_type("pending_actions") == "TEXT"
    assert p._id_type("sales") == "BIGINT" and p._id_type("companies") == "BIGINT"


def test_preview_and_purge_with_text_pk_rows(db, mk, client):
    x, _bx, _wx, admin = mk.tenant()
    y, _by, _wy, admin_y = mk.tenant()
    _action(db, x, admin, "c0ffee00-0000-4000-8000-000000000001")
    _action(db, y, admin_y, "c0ffee00-0000-4000-8000-000000000002")
    db.commit()
    res = preview_company_purge_ex(db, x.id)
    assert res["counts"]["pending_actions"] == 1
    su = mk.user(None, role=UserRole.super_admin)
    r = client.login(su).get(f"/api/super-admin/companies/{x.id}/delete-preview")
    assert r.status_code == 200, r.text
    purge_company(db, x.id)
    assert [a.id for a in db.query(PendingAction).all()] == ["c0ffee00-0000-4000-8000-000000000002"]
