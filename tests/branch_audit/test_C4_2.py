"""C4.2 — Frontend: umumiy qobiq, tasdiqlash oqimi, tarif sahifalari (fayl-matn testlari).

Frontend o'zgarishlari uchun backend ikki-korxona izolyatsiyasi qo'llanmaydi: bu vazifada API/model
o'zgarmagan; testlar manba fayllardagi shartlarni tekshiradi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_C4_2.py -q -p no:cacheprovider
"""
import json
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"


def read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


# 1. T3.4 — sidebar filtri isPageAllowed bilan
def test_sidebar_uses_is_page_allowed():
    s = read("components/AdminLayout.jsx")
    assert re.search(r"import \{ isPageAllowed \} from '\.\./utils/permissions'", s)
    assert "isPageAllowed(user, permKey)" in s


# 2. T3.5 — tarif kartochkalarida i18n kalitlari, qattiq 'Cheksiz' / ' ta' yo'q
@pytest.mark.parametrize("rel", ["pages/admin/Tariflar.jsx", "pages/admin/SuperAdmin.jsx"])
def test_tariff_cards_use_i18n(rel):
    s = read(rel)
    assert "tariffs.limitUnlimited" in s and "tariffs.unit" in s
    assert "tariffs.branchLimit" in s and "tariffs.resourceLimits" in s
    assert "tariffs.systemModules" in s
    # Qattiq yozilgan ' ta`' va 'Cheksiz' faqat tf() zaxirasi sifatida qolishi mumkin
    assert "} ta`" not in s
    assert not re.search(r"\? 'Cheksiz'|: 'Cheksiz'", s)


def test_superadmin_settings_label_no_fallback():
    s = read("pages/admin/SuperAdmin.jsx")
    assert "t('common.settings') || 'Sozlamalar'" not in s
    assert "label: t('common.settings')," in s


# 3. T3.9 — SuperAdmin kuryer/agent qatorlarida cheksiz
def test_superadmin_agents_couriers_unlimited():
    s = read("pages/admin/SuperAdmin.jsx")
    assert re.search(r"tariff\.max_agents == null && tariff\.has_distribution \? unlimitedTxt", s)
    assert re.search(r"tariff\.max_couriers == null && tariff\.has_distribution \? unlimitedTxt", s)


# 4. T3.18 — PaymentReconciliation alohida yo'nalish
def test_payment_reconciliation_route():
    s = read("App.jsx")
    assert "import('./pages/admin/PaymentReconciliation')" in s
    m = re.search(r'<Route path="payment-reconciliation" element=\{(.+)\} />', s)
    assert m and "PrivateRoute" in m.group(1) and "<PaymentReconciliation />" in m.group(1)


# 5. T3.18 — sozlamalar menyusida payment_terminals
def test_settings_menu_payment_terminals():
    # 344afc9 (jamoa qarori): to'lov terminallari va solishtirish sozlamalar menyusidan asosiy menyuning
    # "Moliya" guruhiga ko'chirildi; Settings.jsx dagi tab o'zgarishsiz qoladi
    s = read("components/AdminLayout.jsx")
    assert "path: '/admin/settings?tab=payment_terminals'" in s
    assert "path: '/admin/payment-reconciliation'" in s
    assert "id: 'payment_terminals'" not in read("constants/settingsMenus.jsx")
    # Settings.jsx da tab allaqachon tayyor
    assert "tab === 'payment_terminals'" in read("pages/admin/Settings.jsx")


# 6. T4.2 — PosReturn chek meta'sida filial yuridik nomi va STIR
def test_pos_return_meta_branch_requisites():
    s = read("pages/admin/PosReturn.jsx")
    assert "branch_legal_name: saved?.branch_legal_name" in s
    assert "branch_stir: saved?.branch_stir" in s


# 7. T4.2 — PartialReturnModal chek meta'si
def test_partial_return_meta_branch_requisites():
    s = read("pages/admin/PartialReturnModal.jsx")
    assert "branch_legal_name:" in s and "branch_stir:" in s


# 8. T4.6 — axios 403 detail obyekt va toast
def test_axios_object_detail_handling():
    s = read("api/axios.js")
    assert "_detailMsg" in s
    assert "detailCode === 'approval_required'" in s
    assert "detailCode === 'limit_exceeded'" in s
    assert "toast.error(detail ||" not in s
    assert "toast.warn(detail ||" not in s


# 9. T4.6 — usePosSync: suppressToast va oflayn approval_required
def test_use_pos_sync_suppress_toast_and_offline_approval():
    s = read("hooks/usePosSync.js")
    assert "{ suppressToast = false } = {}" in s
    assert "_suppressToast: true" in s
    assert "detail.code === 'approval_required'" in s


# 10, 12. T4.6, T4.7 — sidebar: approvals va branch-plans havolalari
def test_sidebar_approvals_and_branch_plans_links():
    s = read("components/AdminLayout.jsx")
    m = re.search(r"path: '/admin/approvals',\s*roles: ROLE_GROUPS\.POS_ACCESS", s)
    assert m, "approvals havolasi admin/director/manager uchun"
    assert re.search(r"path: '/admin/branch-plans',\s*roles: ROLE_GROUPS\.REPORTS_ACCESS", s)
    assert "approvalsCount > 0" in s and "/approvals/requests" in s
    assert "t('plan.title')" in s and "t('approvals.title')" in s


def test_sidebar_roles_match_spec():
    roles = read("constants/roles.js")
    pos = re.search(r"POS_ACCESS:\s*\[([^\]]*)\]", roles).group(1)
    assert all(r in pos for r in ("ADMIN", "DIRECTOR", "MANAGER"))
    rep = re.search(r"REPORTS_ACCESS:\s*\[([^\]]*)\]", roles).group(1)
    assert all(r in rep for r in ("ADMIN", "DIRECTOR", "MANAGER", "ACCOUNTANT"))


# 11. T4.6 — PartialReturnModal approval oqimi (haqiqiy fayl: pages/admin/PartialReturnModal.jsx)
def test_partial_return_approval_flow():
    s = read("pages/admin/PartialReturnModal.jsx")
    assert "useApprovalFlow" in s and "<ApprovalModal flow={approvalFlow} />" in s
    assert "approval_id: approvalId || undefined" in s
    assert "raw.code === 'approval_required'" in s
    assert "typeof raw === 'object'" in s
    assert "onClick={() => submitReturn()}" in s  # click hodisasi approvalId bo'lib ketmasin


# i18n: pending fayl uchala tilda bir xil kalitlar va lug'atlarga birlashtirilgan (aynan bir marta)
def test_pending_i18n_consistent():
    data = json.loads((Path(__file__).parent / "i18n_pending" / "C4.2.json").read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    for lang in ("uz", "ru", "en"):
        base = read(f"i18n/{lang}.js")
        for k in data[lang]:
            n = len(re.findall(r"^\s*['\"]" + re.escape(k) + r"['\"]\s*:", base, re.M))
            assert n == 1, f"{k} {lang}.js da {n} marta"


def test_used_new_keys_are_in_pending():
    data = json.loads((Path(__file__).parent / "i18n_pending" / "C4.2.json").read_text(encoding="utf-8"))["uz"]
    for rel in ("pages/admin/Tariflar.jsx", "pages/admin/SuperAdmin.jsx", "constants/settingsMenus.jsx"):
        s = read(rel)
        for k in re.findall(r"tf?\(\s*(?:t, )?'((?:tariffs\.(?:systemModules|module\.\w+|has|hasNot))|settings\.menu\.payment_\w+)'", s):
            assert k in data, k
