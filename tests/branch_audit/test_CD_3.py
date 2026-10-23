"""CD.3 — Eskirgan testlar va menyu ruxsati: sidebar ruxsat filtri (isPageAllowed) va header/logout tarjimalari.

Frontend vazifasi: API/model o'zgarmagan, shuning uchun ikki-korxona izolyatsiyasi qo'llanmaydi. Testlar
AdminLayout.jsx manbasidagi havolalarni o'qib, filtr qoidasini (rol + feature + huquq) Python'da qayta hisoblaydi.
Dorixona holati: 'Dorixona' havolasi feature='pharmacy' ga bog'liq (modul o'chiq do'konda ko'rinmaydi).

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_CD_3.py -q -p no:cacheprovider
"""
import json
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
LAYOUT = (SRC / "components" / "AdminLayout.jsx").read_text(encoding="utf-8")
ROLES_JS = (SRC / "constants" / "roles.js").read_text(encoding="utf-8")


# ─── roles.js va AdminLayout havolalarini o'qish ───────────────────────────────────────────

def _roles_enum():
    body = re.search(r"export const ROLES = \{(.*?)\n\}", ROLES_JS, re.S).group(1)
    return {m.group(1): m.group(2) for m in re.finditer(r"(\w+):\s*'(\w+)'", body)}


def _role_groups():
    enum = _roles_enum()
    body = re.search(r"export const ROLE_GROUPS = \{(.*?)\n\}", ROLES_JS, re.S).group(1)
    out = {}
    for m in re.finditer(r"(\w+):\s*\[(.*?)\]", body, re.S):
        out[m.group(1)] = {enum[k] for k in re.findall(r"ROLES\.(\w+)", m.group(2))}
    return out


def _parse_roles(expr):
    expr = expr.strip()
    if expr.startswith("ROLE_GROUPS."):
        return _role_groups()[expr.split(".", 1)[1]]
    enum = _roles_enum()
    return {enum[k] for k in re.findall(r"ROLES\.(\w+)", expr)}


def _nav_links():
    """buildNavGroups ichidagi barcha havolalar: {path: {'roles': set, 'feature': str|None}}."""
    block = LAYOUT[LAYOUT.index("function buildNavGroups"):LAYOUT.index("// Language switcher dropdown")]
    out = {}
    rx = re.compile(r"path: '([^']+)',\s*(?:feature: '(\w+)',\s*)?roles: ([^\n]+?),\n")
    for m in rx.finditer(block):
        out[m.group(1)] = {"roles": _parse_roles(m.group(3)), "feature": m.group(2)}
    return out


def _visible(links, user_role, features=(), permissions=None):
    """isNavLinkVisible ning Python ko'rinishi (manba bilan bir xil qoidalar)."""
    perms = permissions or {}
    aliases = {"ombor": ["ombor", "warehouse"]}
    out = set()
    for path, link in links.items():
        if link["feature"] and link["feature"] not in features:
            continue
        if user_role == "super_admin":
            out.add(path)
            continue
        key = path.split("?")[0].split("/")[-1]
        if perms:
            if not all(perms.get(k) is not False for k in aliases.get(key, [key])):
                continue
            if key in perms:
                if perms[key] is True:
                    out.add(path)
                continue
        if user_role in link["roles"]:
            out.add(path)
    return out


# ─── 1. Manba: filtr chaqiriladi (sidebar guruhlari va flyout havolalari) ────────────────────

def test_is_page_allowed_wired_into_sidebar():
    assert re.search(r"import \{ isPageAllowed \} from '\.\./utils/permissions'", LAYOUT)
    fn = LAYOUT[LAYOUT.index("function isNavLinkVisible"):LAYOUT.index("function buildNavGroups")]
    assert "isPageAllowed(user, permKey)" in fn
    assert "link.path.split('?')[0].split('/').pop()" in fn           # ?tab=... route segmentiga ta'sir qilmaydi
    assert "link.feature && !features?.[link.feature]" in fn           # modul (dorixona va b.) o'chiq bo'lsa yashirin
    # guruh ro'yxati ham, flyout havolalari ham shu funksiya orqali
    assert "group.links.some((l) => isNavLinkVisible(user, l, features))" in LAYOUT
    assert "if (!isNavLinkVisible(user, link, features)) return null;" in LAYOUT
    # eski faqat-rol tekshiruvi qaytib kelmagan
    assert "link.roles && !link.roles.includes(user.role)" not in LAYOUT


# ─── 2. Rol/feature/huquq matritsasi ─────────────────────────────────────────────────────────

def test_nav_links_parsed():
    links = _nav_links()
    assert len(links) >= 25
    assert "/admin/approvals" in links and "/admin/pharmacy" in links


def test_pharmacy_link_only_when_module_on():
    links = _nav_links()
    assert links["/admin/pharmacy"]["feature"] == "pharmacy"
    # (a) dorixona yoqilgan korxona
    assert "/admin/pharmacy" in _visible(links, "admin", features={"pharmacy"})
    # (b) oddiy do'kon — menyu avvalgidek, dorixona havolasi yo'q
    assert "/admin/pharmacy" not in _visible(links, "admin", features=set())
    assert "/admin/sotuv" in _visible(links, "admin", features=set())


def test_manager_sees_approvals_but_not_staff_management():
    links = _nav_links()
    mgr = _visible(links, "manager")
    assert "/admin/approvals" in mgr and "/admin/branch-plans" in mgr
    assert "/admin/filiallar" not in mgr and "/admin/settings?tab=users" not in mgr
    assert "/admin/settings" not in mgr and "/admin/super-admin" not in mgr


def test_role_matrix():
    links = _nav_links()
    assert "/admin/finance" not in _visible(links, "cashier")
    assert "/admin/sotuv" in _visible(links, "cashier")
    assert "/admin/finance" in _visible(links, "accountant")
    assert "/admin/settings?tab=payment_terminals" in _visible(links, "accountant")
    assert "/admin/super-admin" not in _visible(links, "admin")
    assert "/admin/super-admin" in _visible(links, "super_admin")


def test_explicit_false_permission_hides_link():
    links = _nav_links()
    base = _visible(links, "admin")
    assert "/admin/ombor" in base
    no_ombor = _visible(links, "admin", permissions={"ombor": False, "sotuv": True})
    assert "/admin/ombor" not in no_ombor and "/admin/sotuv" in no_ombor
    # eski 'warehouse' huquqi ham /admin/ombor ni yopadi (alias)
    assert "/admin/ombor" not in _visible(links, "admin", permissions={"warehouse": False, "sotuv": True})
    # bo'sh huquqlar — faqat rol bo'yicha (o'zgarishsiz)
    assert _visible(links, "admin", permissions={}) == base
    # super_admin huquqlardan qat'i nazar hamma narsani ko'radi
    assert "/admin/ombor" in _visible(links, "super_admin", permissions={"ombor": False})


def test_explicit_true_permission_grants_link():
    links = _nav_links()
    assert "/admin/finance" not in _visible(links, "cashier")
    assert "/admin/finance" in _visible(links, "cashier", permissions={"finance": True})


def test_approvals_roles_match_route_and_backend():
    links = _nav_links()
    assert links["/admin/approvals"]["roles"] == {"admin", "director", "manager"}
    app = (SRC / "App.jsx").read_text(encoding="utf-8")
    assert 'path="approvals" element={<PrivateRoute roles={[...ROLE_GROUPS.POS_ACCESS' in app


# ─── 3. i18n: pending/CD.3.json ──────────────────────────────────────────────────────────────

HEADER_KEYS = {"header.collapseSidebar", "header.expandSidebar", "settings.group.system",
               "settings.group.finance", "settings.group.integrations", "subscription.renewNow",
               "pos.logoutWarningSync"}


def _pending():
    return json.loads((Path(__file__).resolve().parent / "i18n_pending" / "CD.3.json").read_text(encoding="utf-8"))


def test_pending_three_languages_same_keys():
    data = _pending()
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"]) == HEADER_KEYS
    assert all(v.strip() for lang in data.values() for v in lang.values())
    for lang in data.values():   # {count} o'zgaruvchisi saqlangan
        assert "{count}" in lang["pos.logoutWarningSync"]


@pytest.mark.parametrize("lang", ["uz", "ru", "en"])
def test_pending_keys_not_already_in_dictionaries(lang):
    # Birlashtirilgandan keyin: har kalit lug'atda aynan bir marta (takror yo'q)
    base = (SRC / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
    for k in _pending()[lang]:
        n = len(re.findall(r"^\s*['\"]" + re.escape(k) + r"['\"]\s*:", base, re.M))
        assert n == 1, f"{k} {lang}.js da {n} marta"


def test_layout_uses_pending_keys():
    for k in ("header.collapseSidebar", "header.expandSidebar", "subscription.renewNow", "pos.logoutWarningSync"):
        assert f"'{k}'" in LAYOUT, k
    menus = (SRC / "constants" / "settingsMenus.jsx").read_text(encoding="utf-8")
    for k in ("settings.group.system", "settings.group.finance", "settings.group.integrations"):
        assert f"'{k}'" in menus, k
