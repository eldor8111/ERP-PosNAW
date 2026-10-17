"""C4.3 — Frontend: filial hooklari, mijoz tanlash, sozlamalar.

Frontend bandlari manba fayllardagi shartlar (fayl-matn/regex) bilan tekshiriladi; frontend ishlatadigan
backend shartnomalari (mijozlar sahifalash/qidiruv, yagona mijozni olish, filiallar ro'yxati) ikki korxona
bilan tekshiriladi: A korxona foydalanuvchisi B resursini ko'rmaydi (404/bo'sh), o'z resursi ishlaydi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_C4_3.py -q -p no:cacheprovider
"""
import json
import re
from pathlib import Path

import pytest

from app.models.customer import Customer
from app.models.user import UserRole

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
PENDING = ROOT / "tests" / "branch_audit" / "i18n_pending" / "C4.3.json"


def read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


# ── 1. T3.1 Operations.jsx: transfer filtrlari mobilga moslangan ─────────────

def test_operations_filter_grids_are_responsive():
    s = read("pages/admin/Operations.jsx")
    # Transfer filtrlari: mobilda 1 ustun
    assert "grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3" in s
    assert "grid grid-cols-1 sm:grid-cols-3 gap-3" in s
    assert s.count("grid-cols-1 md:grid-cols-[1fr_auto_1fr_1fr]") >= 2
    # Eski qotirilgan ustunli ko'rinishlar qolmagan
    assert "grid grid-cols-4 gap-3" not in s
    assert "grid grid-cols-3 gap-3" not in s
    assert not re.search(r'className="grid grid-cols-\[1fr_auto_1fr_1fr\]', s)


# ── 2. T3.3 Filiallar.jsx: WarehouseModal defaultBranchId ────────────────────

def test_filiallar_warehouse_modal_default_branch():
    s = read("pages/admin/Filiallar.jsx")
    assert "function WarehouseModal({ branches, editWh, defaultBranchId, onSave, onClose })" in s
    assert "defaultBranchId={whModal?.branchId}" in s
    assert re.search(r"branch_id: editWh\?\.branch_id \?\? defaultBranchId \?\? ''", s)


# ── 3. T3.5 Shifts.jsx: toast, til bo'yicha format, "so'm" kalitga ───────────

def test_shifts_active_shift_error_toast_and_locale():
    s = read("pages/admin/Shifts.jsx")
    i = s.index("const loadActive")
    block = s[i:i + 600]
    assert "console.error" not in block
    assert "_silent: true, _suppressToast: true" in block
    assert "toast.error(err.response?.data?.detail || t('common.loadError'))" in block
    # 'uz-UZ' qattiq yozilmagan (faqat localeOf zaxirasi)
    assert "const localeOf = (lang)" in s
    assert len(re.findall(r"'uz-UZ'", s)) <= 4          # localeOf zaxirasi + default parametrlar
    assert not re.search(r"toLocale\w*\('uz-UZ'", s)
    # "so'm" qattiq yozilmagan
    assert "so'm" not in re.sub(r"//.*", "", s)
    assert "t('common.sum')" in s


# ── 4. T3.5 Settings.jsx: alert() yo'q ───────────────────────────────────────

def test_settings_has_no_alert_calls():
    s = read("pages/admin/Settings.jsx")
    assert not re.search(r"(?<![\w.])alert\(", s), "Settings.jsx da alert() qolgan"
    assert "toast.error(err.response?.data?.detail || t('error.serverError'))" in s


# ── 5. T3.8 filial hooklari: api.get('/branches') o'rniga useBranches ────────

PAGES_WITH_BRANCH_HOOK = [
    "pages/admin/Filiallar.jsx",
    "pages/admin/Settings.jsx",
    "pages/admin/Users.jsx",
    "pages/admin/Settings/Users.jsx",
    "pages/admin/Warehouse.jsx",
    "pages/admin/Ombor.jsx",
    "pages/admin/Reports.jsx",
    "pages/admin/Purchases.jsx",
    "pages/admin/Profile.jsx",
]


@pytest.mark.parametrize("rel", PAGES_WITH_BRANCH_HOOK)
def test_pages_use_branches_hook(rel):
    s = read(rel)
    assert "hooks/useBranches'" in s and "useBranches(" in s
    assert not re.search(r"api\.get\(\s*['\"`]/branches(['\"`?])", s), f"{rel}: api.get('/branches') qolgan"


@pytest.mark.parametrize("rel", ["pages/admin/Users.jsx", "pages/admin/Settings/Users.jsx",
                                 "pages/admin/Reports.jsx", "pages/admin/Filiallar.jsx"])
def test_pages_needing_inactive_branches_pass_flag(rel):
    assert "useBranches({ includeInactive: true })" in read(rel)


def test_branch_changes_invalidate_cache():
    f = read("pages/admin/Filiallar.jsx")
    # yaratish/tahrirlash (modal onSave), nofaol qilish va qayta yoqish
    assert "onSave={() => { setBranchModal(null); invalidateBranches(); load(); }}" in f
    assert len(re.findall(r"invalidateBranches\(\);\s*\n\s*load\(\);", f)) >= 2
    st = read("pages/admin/Settings.jsx")
    assert "invalidateBranches();" in st            # BranchRequisitesSection PATCH dan keyin
    assert "import { useBranches, invalidateBranches }" in st


def test_use_branches_hook_reload_and_failed_marker():
    h = read("hooks/useBranches.js")
    assert "async (force = true)" in h                # reload(false) — keshdan
    assert "failed.failed = true" in h
    assert "export function invalidateBranches" in h


# ── 6. T3.8 AuthContext: chiqish va korxona almashtirishda keshni tozalash ───

def test_auth_context_invalidates_branches_on_logout_and_company_switch():
    s = read("context/AuthContext.jsx")
    assert "import { invalidateBranches } from '../hooks/useBranches'" in s
    # applyAuthResponse (login + select-company) va logout
    apply_block = s[s.index("const applyAuthResponse"):s.index("const login = ")]
    assert "invalidateBranches()" in apply_block
    logout_block = s[s.index("const logout = "):s.index("const updateUser")]
    assert "invalidateBranches()" in logout_block


# ── 7. T3.8 PosDesktop: CustomerPicker ───────────────────────────────────────

def test_pos_desktop_uses_customer_picker():
    s = read("pages/admin/PosDesktop.jsx")
    assert "import CustomerPicker from '../../components/CustomerPicker'" in s
    assert "function CustSearch" not in s and "<CustSearch" not in s
    assert re.search(r'<CustomerPicker variant="pos" customers=\{customers\} value=\{custId\} onChange=\{pickCustomer\}', s)
    assert "isOnline={isOnline}" in s
    # oflayn zaxira: usePosSync.fetchCustomers hamon limit 500 bilan
    assert "limit: 500" in read("hooks/usePosSync.js")


# ── 8. T3.8 UlgurjiSotuv: CustomerPicker (sozlamalar) va tanlangan mijozni olish ──

def test_ulgurji_customer_picker_and_resolve():
    s = read("pages/admin/UlgurjiSotuv.jsx")
    assert "import CustomerPicker from '../../components/CustomerPicker'" in s
    assert "<CustomerPicker" in s
    assert "/customers/?limit=200" in s                  # oflayn zaxira ro'yxat saqlangan
    # 200 talikda yo'q tanlangan mijoz yagona-mijoz endpointi (POST /customers/{id}) bilan olinadi
    assert "api.post(`/customers/${id}`, null" in s


def test_customer_picker_single_customer_uses_existing_endpoint():
    s = read("components/CustomerPicker.jsx")
    assert "api.post(`/customers/${value}`, null" in s
    assert "api.get(`/customers/${value}`" not in s


# ── 9. T3.8 KirimTolovlar: mijozlar sahifalanadi, qidiruv serverda ───────────

def test_kirim_tolovlar_customers_paginated_server_side():
    s = read("pages/admin/KirimTolovlar.jsx")
    assert "limit: 2000" not in s
    assert "/customers/paginated" in s
    assert "skip" in s and "search: custDq" in s and "min_debt" in s
    assert "loadMoreCustomers" in s
    assert "matchesSearch" not in s                      # klientda qidirish olib tashlandi


# ── 10. T3.8 AssignCustomersModal: sahifalash, qidiruv serverda ──────────────

def test_assign_customers_modal_paginated():
    s = read("pages/admin/AssignCustomersModal.jsx")
    assert "limit: 2000" not in s
    assert "page: 1, limit: PAGE_SIZE" in s
    assert "x-total-count" in s
    assert "search: dq" in s
    assert "loadMore" in s
    assert "fieldStaff.loadMore" in s


# ── 11. T3.18 UlgurjiSotuv: fiskal natijani serverga yozish, tranzaksiya raqami ──

def test_ulgurji_fiscal_patch_and_transaction_reference():
    s = read("pages/admin/UlgurjiSotuv.jsx")
    assert "saleId: res?.data?.id ?? null" in s
    assert "api.patch(`/sales/${saleId}/fiscal`, body, { _suppressToast: true })" in s
    assert "fiscal_factory_id: factoryId" in s
    # provayder to'lovi: terminal + tranzaksiya raqami
    assert "'/payment-terminals/mine'" in s
    assert "const REF_PROVIDERS = ['click', 'payme', 'uzum']" in s
    assert "referenceRequired(" in s and "pos.referencePlaceholder" in s
    assert re.search(r"reference: String\(p\.reference\)\.trim\(\)", s)
    assert re.search(r"terminal_id: Number\(p\.terminal_id\)", s)
    # tur o'zgarganda reference/terminal tozalanadi
    assert "{ type: e.target.value, reference: '', terminal_id: '' }" in s


# ── 12. T4.2 Filiallar.jsx: dialogda rekvizit maydonlari ─────────────────────

def test_filiallar_dialog_has_requisite_fields():
    s = read("pages/admin/Filiallar.jsx")
    i = s.index("function BranchModal")
    j = s.index("function WarehouseModal")
    m = s[i:j]
    for field in ("code", "legal_name", "stir", "tax_regime", "working_hours"):
        assert field in m, field
    assert "api.patch(`/branches/${branch.id}`, body" in m
    assert "api.post('/branches', { ...body, ...provision }" in m
    assert r"/^(\d{9}|\d{14})$/" in m
    for k in ("branchSettings.code", "branchSettings.legalName", "branchSettings.stir", "branchSettings.taxRegime",
              "branchSettings.hours"):
        assert k in m


# ── 13. T4.3 Settings: aksiyalarni avtomatik qo'llash tumbleri ───────────────

def test_promotions_auto_apply_toggle_in_settings_tab():
    st = read("pages/admin/Settings.jsx")
    assert "import Promotions from './Promotions'" in st and "<Promotions />" in st
    p = read("pages/admin/Promotions.jsx")
    assert "api.get('/promotions/settings'" in p and "api.put('/promotions/settings', { auto_apply: next })" in p
    assert "promotion.autoApply" in p and "promotion.autoApplyHint" in p


# ── i18n: pending fayl va ishlatilgan yangi kalitlar ─────────────────────────

def test_pending_i18n_keys_consistent():
    data = json.loads(PENDING.read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"]) and data["uz"]
    assert "fieldStaff.loadMore" in data["uz"]
    assert "fieldStaff.loadMore" in read("pages/admin/AssignCustomersModal.jsx")


# ── Backend shartnomalari (ikki korxona): frontend ishlatadigan endpointlar ──

def _cust(db, company, name, phone=None, debt=0, **kw):
    c = Customer(name=name, phone=phone, company_id=company.id, is_active=True, debt_balance=debt, **kw)
    db.add(c)
    db.flush()
    return c


@pytest.fixture
def w(db, mk):
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    return dict(ca=ca, ba=ba, admin=admin, cb=cb, bb=bb, admin_b=admin_b)


def test_customers_page_limit_total_count_isolated(client, db, w):
    own = [_cust(db, w["ca"], f"Alpha {i}", phone=f"99890100{i:04d}") for i in range(5)]
    other = _cust(db, w["cb"], "Alpha Begona", phone="998901999999")
    api = client.login(w["admin"])

    r = api.get("/api/customers?page=1&limit=2")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5"            # begona korxona hisobga olinmaydi
    r2 = api.get("/api/customers?page=3&limit=2")
    assert len(r2.json()) == 1
    ids = {x["id"] for x in r.json()} | {x["id"] for x in api.get("/api/customers?page=2&limit=2").json()} \
        | {x["id"] for x in r2.json()}
    assert ids == {c.id for c in own} and other.id not in ids

    # server qidiruvi (AssignCustomersModal / CustomerPicker)
    s = api.get("/api/customers?search=Alpha 3&limit=20")
    assert [x["name"] for x in s.json()] == ["Alpha 3"]
    assert s.headers["X-Total-Count"] == "1"
    # B korxona o'z mijozini ko'radi, A mijozlarini emas
    rb = client.login(w["admin_b"]).get("/api/customers?search=Alpha&limit=20")
    assert [x["id"] for x in rb.json()] == [other.id]


def test_customers_paginated_search_min_debt_isolated(client, db, w):
    d1 = _cust(db, w["ca"], "Qarzdor Bir", debt=1000)
    _cust(db, w["ca"], "Qarzsiz", debt=0)
    d2 = _cust(db, w["ca"], "Qarzdor Ikki", debt=500)
    _cust(db, w["cb"], "Qarzdor Begona", debt=9999)
    api = client.login(w["admin"])

    r = api.get("/api/customers/paginated?skip=0&limit=50&min_debt=0.0001")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total"] == 2
    assert {x["id"] for x in d["items"]} == {d1.id, d2.id}
    # qidiruv + sahifalash (skip)
    d = api.get("/api/customers/paginated?skip=0&limit=1&search=Qarzdor").json()
    assert d["total"] == 2 and len(d["items"]) == 1
    d = api.get("/api/customers/paginated?skip=1&limit=1&search=Qarzdor").json()
    assert len(d["items"]) == 1
    assert "Begona" not in " ".join(x["name"] for x in d["items"])


def test_single_customer_endpoint_company_scoped(client, db, w):
    own = _cust(db, w["ca"], "Oz mijoz")
    other = _cust(db, w["cb"], "Begona mijoz")
    api = client.login(w["admin"])
    ok = api.post(f"/api/customers/{own.id}")
    assert ok.status_code == 200 and ok.json()["id"] == own.id
    assert api.post(f"/api/customers/{other.id}").status_code == 404
    # GET marshruti mavjud emas — CustomerPicker POST ishlatadi
    assert api.get(f"/api/customers/{own.id}").status_code in (404, 405)


def test_branches_list_company_isolated(client, db, mk, w):
    b2 = mk.branch(w["ca"], name="A ikkinchi")
    mk.branch(w["cb"], name="B ikkinchi")
    r = client.login(w["admin"]).get("/api/branches")
    assert r.status_code == 200, r.text
    ids = {x["id"] for x in r.json()}
    assert ids == {w["ba"].id, b2.id}
    rb = client.login(w["admin_b"]).get("/api/branches?include_inactive=true")
    assert w["ba"].id not in {x["id"] for x in rb.json()}
