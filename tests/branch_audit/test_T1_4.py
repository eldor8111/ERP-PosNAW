"""T1.4 — Filial uchun default ombor/kassa, filial yaratish provisioning, asosiy filial/ombor.

Qabul mezonlari 1-5 va 8 (SQLite'da indeks va servis), korxonalararo izolyatsiya.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token
from app.models.billing import Tariff
from app.models.branch import Branch
from app.models.moliya import Wallet
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse, WarehouseType
from app.services.branch_provisioning import (
    get_default_warehouse, get_main_branch, provision_branch, set_default_warehouse,
)


# ───────────────────────── yordamchilar ─────────────────────────

def _tariff(db, company, max_branches=5):
    t = Tariff(name="Test tarif", max_branches=max_branches, price_per_month=100000)
    db.add(t)
    db.flush()
    company.tariff_id = t.id
    company.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.flush()
    return t


def _wh(db, company, branch, **kw):
    w = Warehouse(name=kw.pop("name", "W"), company_id=company.id,
                  branch_id=branch.id if branch else None, **kw)
    db.add(w)
    db.flush()
    return w


# ───────────────────────── 1. Ro'yxatdan o'tish ─────────────────────────

def test_register_creates_main_branch_default_warehouse_and_wallet(db, client):
    phone = "998901234567"
    token = create_access_token({"type": "otp_verified", "phone": phone})
    r = client.post("/api/auth/register", json={
        "company_name": "Yangi Savdo", "name": "Ali", "phone": phone, "region": "Toshkent",
        "district": "Chilonzor", "password": "Parol12345", "otp_verified_token": token,
    })
    assert r.status_code == 201, r.text
    user = db.query(User).filter(User.phone == phone).one()
    branches = db.query(Branch).filter(Branch.company_id == user.company_id).all()
    assert len(branches) == 1 and branches[0].is_main is True
    whs = db.query(Warehouse).filter(Warehouse.company_id == user.company_id).all()
    assert len(whs) == 1
    assert whs[0].is_default is True and whs[0].branch_id == branches[0].id
    assert whs[0].type == WarehouseType.main and whs[0].name == "Asosiy ombor"
    wallets = db.query(Wallet).filter(Wallet.company_id == user.company_id).all()
    assert len(wallets) == 1
    assert wallets[0].branch_id == branches[0].id and wallets[0].is_open is False
    assert wallets[0].name == "Asosiy kassa"


# ───────────────────────── 2. POST /branches provisioning ─────────────────────────

def test_create_branch_provisions_warehouse_and_wallet(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    r = client.login(admin).post("/api/branches", json={"name": "Sergeli"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["warehouse_id"] and body["wallet_id"]
    assert body["default_warehouse_id"] == body["warehouse_id"]
    assert body["warehouse_count"] == 1
    assert body["is_main"] is False  # korxonada filial bor edi
    wh = db.get(Warehouse, body["warehouse_id"])
    assert wh.branch_id == body["id"] and wh.company_id == c.id and wh.is_default is True
    wl = db.get(Wallet, body["wallet_id"])
    assert wl.branch_id == body["id"] and wl.company_id == c.id and wl.is_open is False


def test_create_branch_custom_names(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    r = client.login(admin).post("/api/branches", json={
        "name": "Yunusobod", "warehouse_name": "Yunusobod ombori", "wallet_name": "Yunusobod kassasi"})
    assert r.status_code == 200, r.text
    assert db.get(Warehouse, r.json()["warehouse_id"]).name == "Yunusobod ombori"
    assert db.get(Wallet, r.json()["wallet_id"]).name == "Yunusobod kassasi"


def test_create_branch_without_warehouse_and_wallet(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c)
    r = client.login(admin).post("/api/branches", json={
        "name": "Bo'sh filial", "create_warehouse": False, "create_wallet": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["warehouse_id"] is None and body["wallet_id"] is None
    assert body["warehouse_count"] == 0 and body["default_warehouse_id"] is None
    assert db.query(Warehouse).filter(Warehouse.branch_id == body["id"]).count() == 0
    assert db.query(Wallet).filter(Wallet.branch_id == body["id"]).count() == 0


def test_create_branch_tariff_limit_creates_nothing(db, mk, client):
    c, b, w, admin = mk.tenant()
    _tariff(db, c, max_branches=1)  # allaqachon 1 ta filial bor
    n_wh = db.query(Warehouse).count()
    n_wl = db.query(Wallet).count()
    r = client.login(admin).post("/api/branches", json={"name": "Limitdan tashqari"})
    assert r.status_code == 403
    assert db.query(Warehouse).count() == n_wh and db.query(Wallet).count() == n_wl


def test_first_branch_of_company_is_main(db, mk, client):
    c = mk.company()
    admin = mk.user(c, role=UserRole.admin)
    r = client.login(admin).post("/api/branches", json={"name": "Birinchi"})
    # tarifsiz korxona: standart limit 1, birinchi filial ruxsat etiladi
    assert r.status_code == 200, r.text
    assert r.json()["is_main"] is True


def test_list_branches_has_counts_and_default(db, mk, client):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    db.flush()
    b2 = mk.branch(c, name="Bo'sh")
    _wh(db, c, b, name="Do'kon", type=WarehouseType.shop)
    r = client.login(admin).get("/api/branches")
    assert r.status_code == 200
    rows = {x["id"]: x for x in r.json()}
    assert rows[b.id]["warehouse_count"] == 2 and rows[b.id]["default_warehouse_id"] == w.id
    assert rows[b2.id]["warehouse_count"] == 0 and rows[b2.id]["default_warehouse_id"] is None
    assert "is_main" in rows[b.id]


def test_list_branches_isolated_between_companies(db, mk, client):
    c1, b1, w1, a1 = mk.tenant()
    c2, b2, w2, a2 = mk.tenant()
    ids = {x["id"] for x in client.login(a1).get("/api/branches").json()}
    assert b1.id in ids and b2.id not in ids


# ───────────────────────── 3. POST /warehouses avto-filial ─────────────────────────

def test_create_warehouse_without_branch_uses_users_branch(db, mk, client):
    c, b, w, admin = mk.tenant()
    # filiali bor admin (users.branch_id) branch_id'siz yaratadi
    r = client.login(admin).post("/api/warehouses", json={"name": "Yangi ombor"})
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == b.id
    # keyingi GET da ko'rinadi, dublikat yo'q
    lst = client.get("/api/warehouses").json()
    assert [x["name"] for x in lst].count("Yangi ombor") == 1


def test_create_warehouse_single_branch_company_without_user_branch(db, mk, client):
    c = mk.company()
    b = mk.branch(c)
    admin = mk.user(c, role=UserRole.admin)  # filialsiz admin, lekin yagona filial bor
    r = client.login(admin).post("/api/warehouses", json={"name": "Ombor A"})
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == b.id


def test_create_warehouse_multi_branch_unassigned_admin_stays_branchless(db, mk, client):
    c = mk.company()
    mk.branch(c)
    mk.branch(c)
    admin = mk.user(c, role=UserRole.admin)
    r = client.login(admin).post("/api/warehouses", json={"name": "Umumiy"})
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] is None


def test_create_warehouse_foreign_branch_rejected(db, mk, client):
    c1, b1, w1, a1 = mk.tenant()
    c2, b2, w2, a2 = mk.tenant()
    r = client.login(a1).post("/api/warehouses", json={"name": "X", "branch_id": b2.id})
    assert r.status_code in (400, 404)
    assert db.query(Warehouse).filter(Warehouse.name == "X").count() == 0


def test_first_warehouse_in_branch_becomes_default(db, mk, client):
    c = mk.company()
    b = mk.branch(c)
    admin = mk.user(c, role=UserRole.admin, branch=b)
    cl = client.login(admin)
    r1 = cl.post("/api/warehouses", json={"name": "Birinchi", "branch_id": b.id}).json()
    r2 = cl.post("/api/warehouses", json={"name": "Ikkinchi", "branch_id": b.id}).json()
    assert r1["is_default"] is True and r2["is_default"] is False
    # raw_material turi avtomatik default bo'lmaydi
    c3 = mk.company()
    b3 = mk.branch(c3)
    a3 = mk.user(c3, role=UserRole.admin, branch=b3)
    r3 = client.login(a3).post("/api/warehouses", json={"name": "Xom", "type": "raw_material", "branch_id": b3.id}).json()
    assert r3["is_default"] is False


def test_create_warehouse_explicit_default_replaces_previous(db, mk, client):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    db.flush()
    r = client.login(admin).post("/api/warehouses", json={"name": "Yangi asosiy", "branch_id": b.id, "is_default": True})
    assert r.status_code == 200, r.text
    assert r.json()["is_default"] is True
    db.refresh(w)
    assert w.is_default is False


# ───────────────────────── 4. PATCH branch_id: null ─────────────────────────

def test_patch_branch_id_null_detaches_warehouse(db, mk, client):
    c, b, w, admin = mk.tenant()
    r = client.login(admin).patch(f"/api/warehouses/{w.id}", json={"branch_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] is None
    db.refresh(w)
    assert w.branch_id is None


def test_patch_without_branch_id_keeps_branch_and_rejects_null_name(db, mk, client):
    c, b, w, admin = mk.tenant()
    # T4.5: name/is_active uchun aniq null — 422, filial va qolgan maydonlar o'zgarmaydi
    r = client.login(admin).patch(f"/api/warehouses/{w.id}", json={"name": None, "is_active": None})
    assert r.status_code == 422, r.text
    db.refresh(w)
    assert w.branch_id == b.id and w.name and w.is_active is True


def test_patch_foreign_branch_and_foreign_warehouse(db, mk, client):
    c1, b1, w1, a1 = mk.tenant()
    c2, b2, w2, a2 = mk.tenant()
    cl = client.login(a1)
    assert cl.patch(f"/api/warehouses/{w1.id}", json={"branch_id": b2.id}).status_code == 400
    assert cl.patch(f"/api/warehouses/{w2.id}", json={"name": "Hack"}).status_code == 404
    assert cl.patch(f"/api/warehouses/{w2.id}", json={"branch_id": None}).status_code == 404
    db.refresh(w2)
    assert w2.branch_id == b2.id


def test_detaching_default_warehouse_reassigns_in_old_branch(db, mk, client):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    other = _wh(db, c, b, name="Do'kon", type=WarehouseType.shop)
    r = client.login(admin).patch(f"/api/warehouses/{w.id}", json={"branch_id": None})
    assert r.status_code == 200, r.text
    db.refresh(w)
    db.refresh(other)
    assert w.is_default is False and other.is_default is True


# ───────────────────────── 5. Default ombor almashishi ─────────────────────────

def test_db_rejects_second_default_in_same_branch(db, mk):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    db.flush()
    sp = db.begin_nested()
    db.add(Warehouse(name="Ikkinchi", company_id=c.id, branch_id=b.id, is_default=True))
    with pytest.raises(IntegrityError):
        db.flush()
    sp.rollback()
    # boshqa filialda va filialsiz bir nechta default mumkin
    b2 = mk.branch(c)
    db.add(Warehouse(name="B2", company_id=c.id, branch_id=b2.id, is_default=True))
    db.add(Warehouse(name="N1", company_id=c.id, branch_id=None, is_default=True))
    db.add(Warehouse(name="N2", company_id=c.id, branch_id=None, is_default=True))
    db.flush()


def test_db_rejects_second_main_branch_in_company(db, mk):
    c = mk.company()
    mk.branch(c, is_main=True)
    sp = db.begin_nested()
    db.add(Branch(name="Yana asosiy", company_id=c.id, is_main=True))
    with pytest.raises(IntegrityError):
        db.flush()
    sp.rollback()
    c2 = mk.company()
    mk.branch(c2, is_main=True)  # boshqa korxonada mumkin
    db.flush()


def test_set_default_service_switches_default(db, mk):
    c, b, w, admin = mk.tenant()
    w2 = _wh(db, c, b, name="Ikkinchi", type=WarehouseType.shop)
    set_default_warehouse(db, w)
    set_default_warehouse(db, w2)
    db.refresh(w)
    assert w.is_default is False and w2.is_default is True
    assert get_default_warehouse(db, c.id, b.id).id == w2.id


def test_patch_is_default_true_switches_via_api(db, mk, client):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    w2 = _wh(db, c, b, name="Ikkinchi")
    r = client.login(admin).patch(f"/api/warehouses/{w2.id}", json={"is_default": True})
    assert r.status_code == 200, r.text
    assert r.json()["is_default"] is True
    db.refresh(w)
    assert w.is_default is False


def test_patch_unset_current_default_rejected(db, mk, client):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    db.flush()
    r = client.login(admin).patch(f"/api/warehouses/{w.id}", json={"is_default": False})
    assert r.status_code == 400
    assert "asosiy ombor" in r.json()["detail"]
    db.refresh(w)
    assert w.is_default is True


def test_patch_default_on_branchless_warehouse_rejected(db, mk, client):
    c, b, w, admin = mk.tenant()
    nb = _wh(db, c, None, name="Filialsiz")
    r = client.login(admin).patch(f"/api/warehouses/{nb.id}", json={"is_default": True})
    assert r.status_code == 400


def test_delete_default_reassigns_to_other_main_or_shop(db, mk, client):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    raw = _wh(db, c, b, name="Xom", type=WarehouseType.raw_material)
    shop = _wh(db, c, b, name="Do'kon", type=WarehouseType.shop)
    r = client.login(admin).delete(f"/api/warehouses/{w.id}")
    assert r.status_code == 204
    db.refresh(w)
    db.refresh(raw)
    db.refresh(shop)
    assert w.is_active is False and w.is_default is False
    assert shop.is_default is True and raw.is_default is False


def test_delete_default_without_candidates_leaves_none(db, mk, client):
    c, b, w, admin = mk.tenant()
    w.is_default = True
    db.flush()
    assert client.login(admin).delete(f"/api/warehouses/{w.id}").status_code == 204
    assert get_default_warehouse(db, c.id, b.id) is None


def test_delete_isolation(db, mk, client):
    c1, b1, w1, a1 = mk.tenant()
    c2, b2, w2, a2 = mk.tenant()
    assert client.login(a1).delete(f"/api/warehouses/{w2.id}").status_code == 404
    db.refresh(w2)
    assert w2.is_active is True


# ───────────────────────── servis funksiyalari ─────────────────────────

def test_get_default_warehouse_fallback_by_type_and_order(db, mk):
    c = mk.company()
    b = mk.branch(c)
    _wh(db, c, b, name="Xom", type=WarehouseType.raw_material)
    main = _wh(db, c, b, name="Main", type=WarehouseType.main)
    _wh(db, c, b, name="Shop", type=WarehouseType.shop)
    assert get_default_warehouse(db, c.id, b.id).id == main.id  # is_default yo'q — id bo'yicha main/shop
    other = _wh(db, c, b, name="Belgilangan", type=WarehouseType.shop, is_default=True)
    assert get_default_warehouse(db, c.id, b.id).id == other.id
    other.is_active = False
    db.flush()
    assert get_default_warehouse(db, c.id, b.id).id == main.id  # nofaol default e'tiborsiz
    # begona korxona filiali bo'yicha topilmaydi
    c2 = mk.company()
    assert get_default_warehouse(db, c2.id, b.id) is None
    assert get_default_warehouse(db, c.id, None) is None


def test_get_main_branch(db, mk):
    c = mk.company()
    b1 = mk.branch(c, name="Birinchi")
    b2 = mk.branch(c, name="Ikkinchi")
    assert get_main_branch(db, c.id).id == b1.id  # is_main yo'q — eng kichik id
    b2.is_main = True
    db.flush()
    assert get_main_branch(db, c.id).id == b2.id
    assert get_main_branch(db, mk.company().id) is None
    assert get_main_branch(db, None) is None


def test_provision_branch_flags(db, mk):
    c = mk.company()
    b = mk.branch(c)
    wh, wl = provision_branch(db, b, create_warehouse=False, create_wallet=True)
    assert wh is None and wl.branch_id == b.id and wl.company_id == c.id
    b2 = mk.branch(c)
    wh2, wl2 = provision_branch(db, b2, create_warehouse=True, create_wallet=False, warehouse_name="  ")
    assert wl2 is None and wh2.name == "Asosiy ombor" and wh2.is_default is True


# ───────────────────────── asosiy filial fallback'i ─────────────────────────

def test_resolve_branch_id_falls_back_to_main_branch(db, mk):
    from app.services.sale_helpers import resolve_branch_id
    c = mk.company()
    mk.branch(c, name="Birinchi")
    main = mk.branch(c, name="Asosiy", is_main=True)
    u = mk.user(c, role=UserRole.admin)  # filialsiz
    assert resolve_branch_id(db, u) == main.id


def test_finance_resolve_tx_branch_uses_main(db, mk):
    from app.routers.finance import _resolve_tx_branch
    c = mk.company()
    mk.branch(c, name="Birinchi")
    main = mk.branch(c, name="Asosiy", is_main=True)
    u = mk.user(c, role=UserRole.admin)
    assert _resolve_tx_branch(db, u) == main.id


# ───────────────────────── 8. Migratsiya (Alembic) ─────────────────────────

def test_migration_file_is_well_formed():
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions",
                        "t1_4_branch_default_warehouse_main.py")
    spec = importlib.util.spec_from_file_location("t1_4_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "t1_4" and mod.down_revision == "t1_2"
    src = open(path, encoding="utf-8").read()
    for needle in ("ADD COLUMN IF NOT EXISTS is_default", "ADD COLUMN IF NOT EXISTS is_main",
                   "uq_warehouses_branch_default", "uq_branches_company_main", "HAVING COUNT(*) = 1"):
        assert needle in src
    assert "def downgrade" in src and "DROP COLUMN IF EXISTS is_main" in src
