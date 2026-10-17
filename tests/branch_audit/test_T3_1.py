"""T3.1 — Filiallar sahifasi va navigatsiya.

Backend: GET /branches va /warehouses `include_inactive` (faqat admin/director/super_admin),
`warehouses_count`/`users_count`, nofaol filialni qayta yoqishda tarif limiti (403),
GET /users/?branch_id= (begona korxona filiali -> []), super_admin company_id'siz POST /branches -> 400.
Frontend: statik tekshiruvlar (vitest o'rnatilmagan) — sidebar havolalari, marshrut cheklovlari,
BranchesTab o'chirilgani, mobil tab <select>, ShiftCloseModal, ombor turlari konstantasi, i18n kalitlari.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_1.py -q -p no:cacheprovider
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from app.models.billing import Tariff
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'frontend', 'src')


def _read(*parts):
    with open(os.path.join(SRC, *parts), encoding='utf-8') as f:
        return f.read()


def _tariff(db, company, max_branches=10):
    t = Tariff(name="Test tarif", max_branches=max_branches, price_per_month=100000)
    db.add(t)
    db.flush()
    company.tariff_id = t.id
    company.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.flush()
    return t


@pytest.fixture
def w(db, mk):
    """A korxona: faol filial a1 (ombor wa1), nofaol filial a_off (nofaol ombor), admin, kassir.
    B korxona: filial b1, admin."""
    ca, a1, wa1, admin_a = mk.tenant()
    a_off = mk.branch(ca, "Arxiv filial", is_active=False)
    wh_off = mk.warehouse(ca, a1, name="Nofaol ombor", is_active=False)
    cashier = mk.user(ca, role=UserRole.cashier, branch=a1)
    cb, b1, wb1, admin_b = mk.tenant()
    return dict(ca=ca, a1=a1, wa1=wa1, admin=admin_a, a_off=a_off, wh_off=wh_off, cashier=cashier,
                cb=cb, b1=b1, admin_b=admin_b)


# ── 1. GET /branches include_inactive ────────────────────────────────────────

def test_branches_default_only_active(client, w):
    ids = {b["id"] for b in client.login(w["admin"]).get("/api/branches").json()}
    assert w["a1"].id in ids and w["a_off"].id not in ids


def test_include_inactive_admin_sees_inactive(client, w):
    rows = client.login(w["admin"]).get("/api/branches", params={"include_inactive": "true"}).json()
    by = {b["id"]: b for b in rows}
    assert w["a_off"].id in by and by[w["a_off"].id]["is_active"] is False
    assert w["a1"].id in by
    assert w["b1"].id not in by                   # begona korxona filiali hech qachon


def test_include_inactive_ignored_for_cashier(client, w):
    ids = {b["id"] for b in client.login(w["cashier"]).get("/api/branches", params={"include_inactive": "true"}).json()}
    assert w["a1"].id in ids
    assert w["a_off"].id not in ids


def test_branch_counts_in_list(client, w, mk):
    mk.user(w["ca"], role=UserRole.warehouse, branch=w["a1"])
    row = next(b for b in client.login(w["admin"]).get("/api/branches").json() if b["id"] == w["a1"].id)
    assert row["warehouses_count"] == 1           # nofaol ombor sanalmaydi
    assert row["warehouse_count"] == 1
    assert row["users_count"] == 3                # admin + kassir + omborchi


# ── 2. GET /warehouses include_inactive ──────────────────────────────────────

def test_warehouses_include_inactive_admin_only(client, w):
    ids = lambda r: {x["id"] for x in r.json()}
    adm = client.login(w["admin"])
    assert w["wh_off"].id not in ids(adm.get("/api/warehouses"))
    assert w["wh_off"].id in ids(adm.get("/api/warehouses", params={"include_inactive": "true"}))
    cash = client.login(w["cashier"])
    assert w["wh_off"].id not in ids(cash.get("/api/warehouses", params={"include_inactive": "true"}))


# ── 3. Qayta yoqish — tarif limiti ───────────────────────────────────────────

def test_reactivate_blocked_by_tariff_limit(client, db, w):
    _tariff(db, w["ca"], max_branches=1)          # a1 faol -> limit to'lgan
    cl = client.login(w["admin"])
    r = cl.patch(f"/api/branches/{w['a_off'].id}", json={"is_active": True})
    assert r.status_code == 403, r.text
    assert "maksimal filiallar soni" in r.json()["detail"]
    db.refresh(w["a_off"])
    assert w["a_off"].is_active is False


def test_reactivate_ok_when_limit_free(client, db, w):
    _tariff(db, w["ca"], max_branches=5)
    r = client.login(w["admin"]).patch(f"/api/branches/{w['a_off'].id}", json={"is_active": True})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True
    db.refresh(w["a_off"])
    assert w["a_off"].is_active is True


def test_reactivate_foreign_branch_404(client, db, w):
    other = w["b1"]
    other.is_active = False
    db.flush()
    r = client.login(w["admin"]).patch(f"/api/branches/{other.id}", json={"is_active": True})
    assert r.status_code == 404
    db.refresh(other)
    assert other.is_active is False


# ── 4. GET /users/?branch_id= ────────────────────────────────────────────────

def test_users_branch_filter_own_branch(client, db, mk, w):
    a2 = mk.branch(w["ca"], "Ikkinchi filial")
    u2 = mk.user(w["ca"], role=UserRole.cashier, branch=a2)
    cl = client.login(w["admin"])
    ids1 = {u["id"] for u in cl.get("/api/users/", params={"branch_id": w["a1"].id}).json()}
    assert w["cashier"].id in ids1 and u2.id not in ids1
    ids2 = {u["id"] for u in cl.get("/api/users/", params={"branch_id": a2.id}).json()}
    assert ids2 == {u2.id}
    # filtrsiz — hammasi
    all_ids = {u["id"] for u in cl.get("/api/users/").json()}
    assert {w["cashier"].id, u2.id, w["admin"].id} <= all_ids


def test_users_branch_filter_foreign_branch_empty(client, w):
    r = client.login(w["admin"]).get("/api/users/", params={"branch_id": w["b1"].id})
    assert r.status_code == 200
    assert r.json() == []


# ── 5. POST /branches (super_admin) ──────────────────────────────────────────

def test_super_admin_create_without_company_400(client, db, mk):
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post("/api/branches", json={"name": "Yetim"})
    assert r.status_code == 400, r.text


def test_super_admin_create_with_company_ok(client, db, mk, w):
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post("/api/branches", json={"name": "Yangi filial", "company_id": w["ca"].id})
    assert r.status_code == 200, r.text
    assert r.json()["company_id"] == w["ca"].id


def test_admin_create_branch_own_company(client, db, w):
    _tariff(db, w["ca"], max_branches=5)
    r = client.login(w["admin"]).post("/api/branches", json={"name": "Chilonzor"})
    assert r.status_code == 200, r.text
    assert r.json()["company_id"] == w["ca"].id


# ── 6. Frontend statik tekshiruvlar ──────────────────────────────────────────

def test_warehouse_types_constant_has_six_types():
    src = _read('constants', 'warehouseTypes.js')
    values = re.findall(r"value:\s*'([a-z_]+)'", src)
    assert values == ['main', 'shop', 'transit', 'returns', 'raw_material', 'wip']
    assert re.findall(r"labelKey:\s*'(branch\.type\w+)'", src) == [
        'branch.typeMain', 'branch.typeShop', 'branch.typeTransit', 'branch.typeReturns',
        'branch.typeRawMaterial', 'branch.typeWip']
    # backend enum bilan mos
    from app.models.warehouse import WarehouseType
    assert sorted(values) == sorted(e.value for e in WarehouseType)


def test_filiallar_uses_shared_types_and_new_behaviour():
    src = _read('pages', 'admin', 'Filiallar.jsx')
    assert "constants/warehouseTypes" in src
    assert "WH_TYPE_LABEL" not in src and "WH_TYPE_COLOR" not in src
    assert "embedded" in src
    assert "include_inactive: true" in src
    assert "loadError" in src
    assert "!loadError && branches.length === 0" in src
    assert "defaultBranchId" in src and "presetBranchId" not in src
    assert "branch_id: editWh?.branch_id ?? defaultBranchId ?? ''" in src
    assert "setStats" not in src
    assert "}, [t, reloadBranches]);" in src      # C4.3: filiallar useBranches hookidan (reload barqaror)
    assert "is_active: true" in src               # qayta yoqish
    assert "/users/" in src and "branch_id: branchId" in src


def test_ombor_and_warehouse_use_shared_types():
    ombor = _read('pages', 'admin', 'Ombor.jsx')
    assert "constants/warehouseTypes" in ombor
    assert "aria-label={tab.label}" in ombor and "title={tab.label}" in ombor
    assert "grid grid-cols-1 sm:grid-cols-3" in ombor
    wh = _read('pages', 'admin', 'Warehouse.jsx')
    assert "constants/warehouseTypes" in wh
    assert '<div className="overflow-x-auto">\r\n              <table' in wh or '<div className="overflow-x-auto">\n              <table' in wh


def test_settings_branches_tab_replaced_by_filiallar():
    src = _read('pages', 'admin', 'Settings.jsx')
    assert "BranchesTab" not in src
    assert "<Filiallar embedded />" in src
    assert "import Filiallar from './Filiallar'" in src
    # mobil tab-bar
    assert 'className="md:hidden mb-4"' in src
    assert "setSearchParams({ tab: e.target.value })" in src
    assert "navigate(m.path)" in src
    assert "MENUS.map(m => <option" in src


def test_app_routes_restricted_to_management():
    src = _read('App.jsx')
    assert re.search(r'path="settings" element=\{<PrivateRoute roles=\{MANAGEMENT_ROUTE_ROLES\}>', src)
    assert re.search(r'path="filiallar" element=\{<PrivateRoute roles=\{MANAGEMENT_ROUTE_ROLES\}>', src)
    assert "MANAGEMENT_ROUTE_ROLES = [...ROLE_GROUPS.MANAGEMENT" in src


def test_sidebar_links_and_flyout():
    src = _read('components', 'AdminLayout.jsx')
    for name, path, roles in [
        ("nav.branches", "/admin/filiallar", "ROLE_GROUPS.MANAGEMENT"),
        ("nav.shifts", "/admin/shifts", "ROLE_GROUPS.SALES"),
        ("nav.warehouse", "/admin/ombor", "ROLE_GROUPS.WAREHOUSE_ACCESS"),
    ]:
        pat = r"name: t\('%s'\),\s*path: '%s',\s*roles: %s," % (re.escape(name), re.escape(path), re.escape(roles))
        assert re.search(pat, src), name
    assert "'ERP System'" not in src and "t('app.title')" in src
    assert "aria-expanded" in src and "onFocus=" in src
    assert "handleSettingsEnter : () =>" in src      # Sozlamalar havolasi aside'ni yopmaydi


def test_shift_close_modal_shared_by_shifts_and_pos_pages():
    modal = _read('components', 'ShiftCloseModal.jsx')
    assert "export default function ShiftCloseModal({ shift, onClosed, onCancel })" in modal
    assert "/shifts/${shift.id}/close" in modal
    shifts = _read('pages', 'admin', 'Shifts.jsx')
    assert "ShiftCloseModal" in shifts and "/close`" not in shifts
    assert "grid grid-cols-1 sm:grid-cols-3" in shifts
    for page in ('PosKassa.jsx', 'UlgurjiSotuv.jsx'):
        src = _read('pages', 'admin', page)
        assert "ShiftCloseModal" in src, page
        assert "shift.closeAction" in src, page
        assert "reloadShift()" in src, page


def test_stat_grids_responsive():
    for rel in (('pages', 'admin', 'Users.jsx'), ('pages', 'admin', 'Settings', 'Users.jsx')):
        src = _read(*rel)
        assert "grid grid-cols-2 md:grid-cols-4 gap-4" in src, rel
        assert "grid grid-cols-4 gap-4" not in src, rel
    assert "grid grid-cols-2 md:grid-cols-4 gap-3 text-sm" in _read('pages', 'admin', 'Purchases.jsx')


def test_pending_i18n_keys_same_in_all_languages():
    with open(os.path.join(os.path.dirname(__file__), 'i18n_pending', 'T3.1.json'), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data) == {'uz', 'ru', 'en'}
    keys = set(data['uz'])
    assert keys == set(data['ru']) == set(data['en'])
    for k in ('nav.branches', 'branch.loadFailedRetry', 'branch.showInactive',
              'branch.usersList', 'shift.closeAction'):
        assert k in keys, k
        assert all(data[lang][k].strip() for lang in data)
    # kodda ishlatilgan yangi kalitlar yozilgan (branch.reactivate T3.9 pending'ida)
    code = _read('pages', 'admin', 'Filiallar.jsx') + _read('components', 'AdminLayout.jsx')
    for k in ('branch.loadFailedRetry', 'branch.showInactive', 'branch.usersList', 'nav.branches'):
        assert k in code, k
