"""T1.13 — Branch modeli, indekslar va migratsiyalar sifati.

Qabul mezonlari: 1 (faol nom unikalligi), 2 (bo'sh nom / uzun maydon -> 422), 3 (created_at/is_active NOT NULL),
4 (bir kassirda bitta ochiq smena), 6 (indekslar modellarda e'lon qilingan), 7 (audit), 8 (DELETE /companies yo'q),
9 (downgrade'da nomsiz drop_constraint yo'q), korxonalararo izolyatsiya.
"""
import glob
import os
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError

from app.database import Base
from app.models.audit_log import AuditLog
from app.models.billing import Tariff
from app.models.branch import Branch
from app.models.shift import Shift
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
VERSIONS = os.path.join(ROOT, 'alembic', 'versions')


def _tariff(db, company, max_branches=10):
    t = Tariff(name="Test tarif", max_branches=max_branches, price_per_month=100000)
    db.add(t)
    db.flush()
    company.tariff_id = t.id
    company.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.flush()
    return t


# ───────────────────── 1. Faol nom unikalligi ─────────────────────

def test_duplicate_active_name_is_409(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    cl = client.login(admin)
    r = cl.post("/api/branches", json={"name": "Chilonzor"})
    assert r.status_code == 200, r.text
    for dup in ("Chilonzor", " chilonzor ", "CHILONZOR"):
        r2 = cl.post("/api/branches", json={"name": dup})
        assert r2.status_code == 409, (dup, r2.text)
        assert r2.json()["detail"] == "Bu nomli faol filial allaqachon mavjud"
    # 409 dan keyin sessiya ishlashda davom etadi va boshqa nom o'tadi
    assert cl.post("/api/branches", json={"name": "Sergeli"}).status_code == 200


def test_inactive_branch_name_does_not_conflict_and_other_company_ok(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    old = mk.branch(c, name="Yunusobod", is_active=False)
    cl = client.login(admin)
    r = cl.post("/api/branches", json={"name": "yunusobod"})
    assert r.status_code == 200, r.text
    # nofaol eskisini qayta yoqish endi to'qnashadi
    r = cl.patch(f"/api/branches/{old.id}", json={"is_active": True})
    assert r.status_code == 409, r.text
    # boshqa korxonada bir xil nom mumkin
    c2, b2, w2, admin2 = mk.tenant()
    _tariff(db, c2)
    assert client.login(admin2).post("/api/branches", json={"name": "Yunusobod"}).status_code == 200


def test_update_name_to_existing_active_name_is_409(db, mk, client):
    c, b, w, admin = mk.tenant()
    mk.branch(c, name="Mirzo Ulug'bek")
    other = mk.branch(c, name="Boshqa")
    cl = client.login(admin)
    assert cl.patch(f"/api/branches/{other.id}", json={"name": " mirzo ulug'bek "}).status_code == 409
    # o'z nomini (o'zgartirmasdan) qayta yuborish to'qnashmaydi
    assert cl.patch(f"/api/branches/{other.id}", json={"name": "Boshqa"}).status_code == 200


def test_name_unique_index_enforced_in_db(db, mk):
    c = mk.company()
    mk.branch(c, name="Olmazor")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Branch(name=" olmazor", company_id=c.id))
            db.flush()
    # nofaol bo'lsa bo'ladi
    db.add(Branch(name="OLMAZOR", company_id=c.id, is_active=False))
    db.flush()


# ───────────────────── 2. Validatsiya ─────────────────────

@pytest.mark.parametrize("payload", [
    {"name": ""},
    {"name": "   "},
    {"name": "x" * 101},
    {"name": "Filial", "phone": "+998 90 123 45 67 (ichki 12)"},   # 28 belgi
    {"name": "Filial", "phone": "1" * 25},
    {"name": "Filial", "address": "a" * 201},
])
def test_create_validation_422(db, mk, client, payload):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    n = db.query(Branch).count()
    r = client.login(admin).post("/api/branches", json=payload)
    assert r.status_code == 422, r.text
    assert db.query(Branch).count() == n


def test_update_validation_422_and_strip(db, mk, client):
    c, b, w, admin = mk.tenant()
    cl = client.login(admin)
    # bo'sh/faqat probel nom PATCH da router tomonidan 400 (T0.8 shartnomasi), uzun nom -> 422
    assert cl.patch(f"/api/branches/{b.id}", json={"name": "  "}).status_code == 400
    assert cl.patch(f"/api/branches/{b.id}", json={"name": "x" * 101}).status_code == 422
    assert cl.patch(f"/api/branches/{b.id}", json={"phone": "9" * 21}).status_code == 422
    r = cl.patch(f"/api/branches/{b.id}", json={"name": "  Yangi nom  "})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Yangi nom"


def test_create_name_is_stripped(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    r = client.login(admin).post("/api/branches", json={"name": "  Chilonzor  "})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Chilonzor"


def test_super_admin_requires_company(db, mk, client):
    c = mk.company()
    sa = mk.user(None, role=UserRole.super_admin)
    cl = client.login(sa)
    r = cl.post("/api/branches", json={"name": "Yetim"})
    assert r.status_code == 400
    assert r.json()["detail"] == "Korxona ko'rsating"
    r = cl.post("/api/branches", json={"name": "Yetim", "company_id": c.id})
    assert r.status_code == 200, r.text
    assert r.json()["company_id"] == c.id


def test_data_error_handler_returns_422(db, client):
    """Boshqa har qanday endpointda ustun uzunligi oshsa 500 emas, 422."""
    from app.main import app

    async def boom():
        raise DataError("INSERT ...", {}, Exception("value too long for type character varying(20)"))

    app.add_api_route("/api/_t1_13_boom", boom, methods=["GET"])
    try:
        r = client.get("/api/_t1_13_boom")
    finally:
        app.router.routes.pop()
    assert r.status_code == 422
    assert r.json()["detail"] == "Kiritilgan qiymat maydon uzunligidan oshib ketdi"


# ───────────────────── 3. NOT NULL / default ─────────────────────

def test_branch_defaults_created_at_and_is_active(db, mk):
    c = mk.company()
    b = Branch(name="Default", company_id=c.id)
    db.add(b)
    db.flush()
    db.refresh(b)
    assert b.created_at is not None
    assert b.is_active is True


def test_branch_not_null_constraints(db, mk):
    c = mk.company()
    # ORM None ni Python default bilan almashtiradi, shuning uchun to'g'ridan-to'g'ri SQL
    for active, company in (("NULL", c.id), ("1", None)):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.execute(
                    text("INSERT INTO branches (name, company_id, is_active, created_at) "
                         f"VALUES ('NN', :cid, {active}, CURRENT_TIMESTAMP)"),
                    {"cid": company},
                )


# ───────────────────── company_name / N+1 ─────────────────────

def test_branch_out_company_name_filled(db, mk, client):
    c, b, w, admin = mk.tenant()
    cl = client.login(admin)
    assert cl.get(f"/api/branches/{b.id}").json()["company_name"] == c.name
    rows = cl.get("/api/branches").json()
    assert rows and all(r["company_name"] == c.name and isinstance(r["is_active"], bool) for r in rows)


# ───────────────────── 7. Audit ─────────────────────

def test_branch_create_update_archive_audited_with_company_and_branch(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    cl = client.login(admin)
    bid = cl.post("/api/branches", json={"name": "Audit filial"}).json()["id"]
    assert cl.patch(f"/api/branches/{bid}", json={"address": "Ko'cha 1"}).status_code == 200
    assert cl.delete(f"/api/branches/{bid}").status_code == 204
    logs = db.query(AuditLog).filter(AuditLog.entity_type == "branch", AuditLog.entity_id == bid) \
        .order_by(AuditLog.id).all()
    assert [lg.action for lg in logs] == ["CREATE", "UPDATE", "DELETE"]  # DELETE = arxivlash (is_active=False)
    assert all(lg.company_id == c.id and lg.branch_id == bid and lg.user_id == admin.id for lg in logs)
    assert logs[1].old_values == {"address": None} and logs[1].new_values == {"address": "Ko'cha 1"}
    assert db.get(Branch, bid).is_active is False


# ───────────────────── izolyatsiya ─────────────────────

def test_cross_company_branch_isolation(db, mk, client):
    ca, ba, wa, admin_a = mk.tenant()
    cb, bb, wb, admin_b = mk.tenant()
    cl = client.login(admin_a)
    assert cl.get(f"/api/branches/{bb.id}").status_code == 404
    assert cl.patch(f"/api/branches/{bb.id}", json={"name": "Hack"}).status_code == 404
    assert cl.delete(f"/api/branches/{bb.id}").status_code == 404
    db.refresh(bb)
    assert bb.name != "Hack" and bb.is_active is True
    assert [r["id"] for r in cl.get("/api/branches").json()] == [ba.id]
    # ijobiy yo'l: o'z filiali
    assert cl.get(f"/api/branches/{ba.id}").status_code == 200
    assert cl.patch(f"/api/branches/{ba.id}", json={"phone": "998901112233"}).status_code == 200


# ───────────────────── 8. DELETE /companies/{id} yo'q ─────────────────────

def test_legacy_delete_company_route_removed(db, mk, client):
    c = mk.company()
    mk.branch(c)
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).delete(f"/api/companies/{c.id}")
    assert r.status_code in (404, 405)
    assert db.query(Branch).filter(Branch.company_id == c.id).count() == 1


# ───────────────────── 4. Bir kassirda bitta ochiq smena ─────────────────────

def test_one_open_shift_per_cashier_in_db(db, mk):
    c, b, w, u = mk.tenant()
    other = mk.user(c, role=UserRole.admin, branch=b)
    db.add(Shift(cashier_id=u.id, branch_id=b.id, company_id=c.id, status="open"))
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Shift(cashier_id=u.id, branch_id=b.id, company_id=c.id, status="open"))
            db.flush()
    # yopilgan smenalar cheklanmaydi, boshqa kassir ham ochishi mumkin
    db.add(Shift(cashier_id=u.id, branch_id=b.id, company_id=c.id, status="closed"))
    db.add(Shift(cashier_id=u.id, branch_id=b.id, company_id=c.id, status="closed"))
    db.add(Shift(cashier_id=other.id, branch_id=b.id, company_id=c.id, status="open"))
    db.flush()


# ───────────────────── 6. Indekslar modellarda e'lon qilingan ─────────────────────

def _index_cols(table):
    return {
        i.name: [c.name if hasattr(c, "name") else str(c) for c in i.expressions]
        for i in Base.metadata.tables[table].indexes
    }


@pytest.mark.parametrize("table,name,cols", [
    ("transactions", "ix_transactions_company_created", ["company_id", "created_at"]),
    ("transactions", "ix_transactions_company_branch_created", ["company_id", "branch_id", "created_at"]),
    ("transactions", "ix_transactions_reference", ["reference_type", "reference_id"]),
    ("wallets", "ix_wallets_company_branch", ["company_id", "branch_id"]),
    ("shifts", "ix_shifts_company_branch_opened", ["company_id", "branch_id", "opened_at"]),
    ("shifts", "ux_shifts_one_open_per_cashier", ["cashier_id"]),
    ("users", "ix_users_company_branch", ["company_id", "branch_id"]),
    ("warehouses", "ix_warehouses_company_branch", ["company_id", "branch_id"]),
    ("stock_transfers", "ix_stock_transfers_from_wh", ["from_warehouse_id"]),
    ("stock_transfers", "ix_stock_transfers_to_wh", ["to_warehouse_id"]),
    ("branches", "ix_branches_company_id", ["company_id"]),
    ("audit_logs", "ix_audit_logs_company_created", ["company_id", "created_at"]),
])
def test_model_declares_index(table, name, cols):
    assert _index_cols(table).get(name) == cols


def test_perf_migration_matches_model_indexes():
    """Migratsiyadagi har bir indeks modelda ham e'lon qilingan (aks holda autogenerate uni o'chiradi)."""
    src = open(os.path.join(VERSIONS, "t1_13_perf_indexes.py"), encoding="utf-8").read()
    assert "autocommit_block" in src and "CONCURRENTLY" in src
    rows = re.findall(r'\("((?:ix|ux)_\w+)", "(\w+)"', src)
    assert len(rows) == 12
    for name, table in rows:
        assert name in _index_cols(table), (table, name)


# ───────────────────── 9/10. Migratsiyalar sifati ─────────────────────

_FIXED = ("09735e25bc45_add_branch_relationships.py", "a6ffaadaea75_add_company_model.py",
          "cff2b4b823e0_add_company_id_to_all_models.py")


@pytest.mark.parametrize("fname", _FIXED)
def test_fixed_downgrades_have_no_nameless_drop_constraint(fname):
    src = open(os.path.join(VERSIONS, fname), encoding="utf-8").read()
    assert "drop_constraint(None" not in src
    assert "DROP CONSTRAINT IF EXISTS" in src


def test_new_t1_13_migrations_lint():
    files = glob.glob(os.path.join(VERSIONS, "t1_13*.py"))
    assert len(files) == 2
    for f in files:
        src = open(f, encoding="utf-8").read()
        compile(src, f, "exec")
        assert "drop_constraint(None" not in src
    rev1 = open(os.path.join(VERSIONS, "t1_13_branch_integrity.py"), encoding="utf-8").read()
    assert "revision: str = 't1_13'" in rev1
    assert "uq_branches_company_name_active" in rev1 and "lower(btrim(name))" in rev1
    assert "SET NOT NULL" in rev1
    rev2 = open(os.path.join(VERSIONS, "t1_13_perf_indexes.py"), encoding="utf-8").read()
    assert "down_revision: Union[str, None] = 't1_13'" in rev2


def test_fixed_migrations_fk_names_are_postgres_default():
    """FK nomlari PostgreSQL standarti: <jadval>_<ustun>_fkey."""
    src = open(os.path.join(VERSIONS, "cff2b4b823e0_add_company_id_to_all_models.py"), encoding="utf-8").read()
    assert len(re.findall(r'DROP CONSTRAINT IF EXISTS (\w+)_company_id_fkey', src)) == 14
    src = open(os.path.join(VERSIONS, "09735e25bc45_add_branch_relationships.py"), encoding="utf-8").read()
    assert "warehouses_branch_id_fkey" in src and "users_branch_id_fkey" in src
