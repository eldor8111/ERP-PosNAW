"""C2.2 — 2-bosqich frontend qoldiqlari: fayl-matn (regex) testlari."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN = ROOT / "frontend" / "src" / "pages" / "admin"
PENDING = ROOT / "tests" / "branch_audit" / "i18n_pending" / "C2.2.json"


def _read(name: str) -> str:
    return (ADMIN / name).read_text(encoding="utf-8")


def test_tolovlar_branch_select_and_param():
    for name in ("KirimTolovlar.jsx", "ChiqimTolovlar.jsx"):
        src = _read(name)
        assert "import BranchSelect from '../../components/BranchSelect'" in src, name
        assert "<BranchSelect" in src, name
        assert re.search(r"branch_id:\s*branchId", src), name
        assert re.search(r"\[dateFrom,\s*dateTo,\s*branchId\]", src), f"{name}: filial o'zgarganda qayta yuklanmaydi"
        assert "/branches" in src, name


def test_kassa_finance_currency():
    kassa = _read("Kassa.jsx")
    assert "CurrencyField" in kassa and "/currencies/active" in kassa
    # xarajat, kirim (invest) va chiqim (withdraw) so'rovlari valyutani yuboradi
    assert len(re.findall(r"currency:\s*form\.currency\s*\|\|\s*'UZS'", kassa)) == 3
    fin = _read("Finance.jsx")
    assert "/currencies/active" in fin
    assert "currency: 'UZS'" in fin  # forma boshlang'ich qiymati
    assert "amount_uzs" in fin
    assert "currency_code" in fin  # tranzaksiyalar ro'yxati


def test_reports_pnl_compare_suppresses_toast():
    src = _read("Reports.jsx")
    assert re.search(r"/reports/pnl-compare\?\$\{p\}`,\s*\{\s*_suppressToast:\s*true\s*\}", src)
    assert "st === 403 || st === 404" in src
    assert "pnlCompareError" in src


def test_alerts_low_stock_pagination():
    src = _read("Alerts.jsx")
    assert "LOW_STOCK_PAGE = 500" in src
    assert "/inventory/low-stock-count" in src
    assert re.search(r"skip:\s*lowStock\.length", src)
    assert "alert.loadMore" in src


def test_settings_has_no_inline_permission_editor():
    # Huquqlar tahrirlagichi Settings/Roles.jsx da (reports.all_branches u yerda mavjud); Settings.jsx da yo'q
    assert "all_branches" in (ADMIN / "Settings" / "Roles.jsx").read_text(encoding="utf-8")
    assert "togglePermission" not in _read("Settings.jsx")


def test_pending_json_same_keys_in_all_langs():
    data = json.loads(PENDING.read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    assert data["uz"]
    for lang in data.values():
        assert all(isinstance(v, str) and v for v in lang.values())
    # kodda ishlatilgan yangi kalitlar pending faylda bor
    used = {
        "reports.pnlBranchNotFound": "Reports.jsx",
        "reports.pnlNoAccess": "Reports.jsx",
        "alert.loadMore": "Alerts.jsx",
    }
    for key, fname in used.items():
        assert key in data["uz"]
        assert key in _read(fname)
