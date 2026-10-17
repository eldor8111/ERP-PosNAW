"""T2.5 — filiallarni taqqoslash va konsolidatsiya hisobotlari.

Qamrov: GET /reports/branch-summary (filial qatorlari, "Filialsiz", "Jami", reconciled, cheklangan rol,
bo'sh davr, noto'g'ri sana, ikki korxona izolyatsiyasi); pnl-compare tarif cheklovi (403/200);
1C eksport (yangi ustunlar, fayl nomi); /finance/payments/income|expense da branch_id; GET /branches
include_inactive; frontend (exportMeta.js, i18n pending, Reports/Operations/Finance ulanishi) statik tekshiruvi.
"""
import csv
import io
import itertools
import json
import os
import re
from decimal import Decimal

import pytest

from app.core.security import create_access_token
from app.models.billing import Tariff
from app.models.moliya import Expense, ExpenseCategory, Transaction
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole
from app.services.pnl_service import UNASSIGNED_BRANCH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)
PERIOD = {'date_from': '2020-01-01', 'date_to': '2099-12-31'}
CMP = {'p1_from': '2020-01-01', 'p1_to': '2099-12-31', 'p2_from': '2020-01-01', 'p2_to': '2099-12-31'}
SUMMARY = '/api/reports/branch-summary'


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T25-{n}", barcode=f"B25-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _sale(db, user, company, product, warehouse, amount=1000, cost=400, refund=False, customer=None):
    n = next(_seq)
    s = Sale(number=f"{'R' if refund else 'S'}T25-{n}", cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None, total_amount=Decimal(amount),
             paid_amount=Decimal(amount), payment_type=PaymentType.cash,
             status=SaleStatus.refunded if refund else SaleStatus.completed,
             customer_id=customer.id if customer else None)
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, quantity=Decimal(1), unit_price=Decimal(amount),
                    cost_price=Decimal(cost), subtotal=Decimal(amount), currency_code="UZS", exchange_rate=1))
    db.flush()
    return s


def _cat(db, company, name="Ijara"):
    c = ExpenseCategory(name=name, company_id=company.id)
    db.add(c)
    db.flush()
    return c


def _expense(db, company, branch_id, cat, amount):
    e = Expense(company_id=company.id, branch_id=branch_id, category_id=cat.id, amount=Decimal(amount))
    db.add(e)
    db.flush()
    return e


def _tx(db, company, branch_id, amount, ref=None, tx_type="income"):
    t = Transaction(company_id=company.id, branch_id=branch_id, type=tx_type, amount=Decimal(amount),
                    reference_type=ref, currency_code="UZS", payment_type="cash")
    db.add(t)
    db.flush()
    return t


@pytest.fixture
def w(db, mk):
    """A korxona: 3 filial (a1, a2, a3), filialsiz ombor; B korxona: alohida tenant."""
    ca, a1, wh1, admin = mk.tenant(UserRole.admin)
    a2 = mk.branch(ca, "Yunusobod")
    wh2 = mk.warehouse(ca, a2, name="Ombor Yunusobod")
    a3 = mk.branch(ca, "Sergeli")
    wh3 = mk.warehouse(ca, a3, name="Ombor Sergeli")
    whn = mk.warehouse(ca, None, name="Filialsiz ombor")
    manager_a1 = mk.user(ca, role=UserRole.manager, branch=a1)
    manager_all = mk.user(ca, role=UserRole.manager)
    cashier = mk.user(ca, role=UserRole.cashier, branch=a1)
    prod = _product(db, ca)
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    prod_b = _product(db, cb)
    return dict(ca=ca, a1=a1, a2=a2, a3=a3, wh1=wh1, wh2=wh2, wh3=wh3, whn=whn, admin=admin,
                manager_a1=manager_a1, manager_all=manager_all, cashier=cashier, prod=prod,
                cb=cb, b1=b1, whb=whb, admin_b=admin_b, prod_b=prod_b)


def _seed(db, w):
    ca, admin, prod = w['ca'], w['admin'], w['prod']
    _sale(db, admin, ca, prod, w['wh1'], 10000, 4000)
    _sale(db, admin, ca, prod, w['wh1'], 2000, 800)
    _sale(db, admin, ca, prod, w['wh2'], 6000, 2000)
    _sale(db, admin, ca, prod, w['wh3'], 4000, 1500)
    _sale(db, admin, ca, prod, w['whn'], 3000, 1000)                       # filialsiz ombor
    _sale(db, admin, ca, prod, w['wh1'], 1000, 400, refund=True)           # qaytarish (a1)
    cat = _cat(db, ca)
    _expense(db, ca, w['a1'].id, cat, 2000)
    _expense(db, ca, w['a2'].id, cat, 500)
    _expense(db, ca, w['b1'].id, cat, 700)                                 # begona filial -> filialsiz
    _tx(db, ca, w['a1'].id, 300, ref="delivery_fee")
    _tx(db, ca, None, 100, ref="other_income")                             # filialsiz kirim
    # B korxona ma'lumoti A hisobotiga aralashmasligi kerak
    _sale(db, w['admin_b'], w['cb'], w['prod_b'], w['whb'], 99999, 1)


def _by_id(rows):
    return {r['branch_id']: r for r in rows}


# ── 1. branch-summary: asosiy yo'l ───────────────────────────────────────────

def test_branch_summary_rows_unassigned_total_reconciled(client, db, w):
    _seed(db, w)
    c = client.login(w['admin'])
    r = c.get(SUMMARY, params=PERIOD)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['currency'] == 'UZS' and j['reconciled'] is True
    assert j['debt_note']
    assert {'from', 'to'} <= set(j['period'])
    rows = _by_id(j['rows'])
    assert set(rows) == {w['a1'].id, w['a2'].id, w['a3'].id}
    assert UNASSIGNED_BRANCH not in rows

    a1 = rows[w['a1'].id]
    assert a1['branch_name'] == w['a1'].name and a1['is_active'] is True
    assert a1['gross_revenue'] == 12000 and a1['returns'] == 1000 and a1['net_revenue'] == 11000
    assert a1['check_count'] == 2 and a1['avg_check'] == 6000
    assert a1['cogs'] == 4800 - 400 and a1['gross_profit'] == 11000 - 4400
    assert a1['expenses'] == 2000 and a1['other_income'] == 300
    assert a1['net_profit'] == 6600 + 300 - 2000
    for k in ("gross_margin_pct", "net_margin_pct"):
        assert k in a1

    un = j['unassigned']
    assert un['branch_id'] == UNASSIGNED_BRANCH
    assert un['gross_revenue'] == 3000 and un['expenses'] == 700 and un['other_income'] == 100
    assert un['check_count'] == 1

    pl = c.get('/api/reports/profit-loss', params=PERIOD).json()
    total = j['total']
    assert total['net_profit'] == pl['net_profit']
    assert total['gross_revenue'] == pl['gross_revenue'] == 25000     # B korxona sotuvi kirmaydi
    assert total['returns'] == pl['returns'] and total['expenses'] == pl['expenses']['total']
    assert total['check_count'] == 5 and total['avg_check'] == 5000
    assert round(sum(r['net_profit'] for r in j['rows']) + un['net_profit'], 2) == total['net_profit']


def test_branch_summary_includes_closed_branch(client, db, w):
    _seed(db, w)
    w['a3'].is_active = False
    db.flush()
    j = client.login(w['admin']).get(SUMMARY, params=PERIOD).json()
    closed = _by_id(j['rows'])[w['a3'].id]
    assert closed['is_active'] is False and closed['gross_revenue'] == 4000
    assert j['reconciled'] is True


def test_branch_summary_reconciled_false_when_unattributed(client, db, w):
    """Hech bir guruhga tushmaydigan yozuv (begona korxona filiali snapshot'i) -> reconciled=false."""
    _seed(db, w)
    s = _sale(db, w['admin'], w['ca'], w['prod'], w['wh1'], 777, 1)
    s.branch_id = w['b1'].id                                   # begona korxona filiali
    db.flush()
    c = client.login(w['admin'])
    j = c.get(SUMMARY, params=PERIOD).json()
    assert j['reconciled'] is False
    assert j['total']['net_profit'] != c.get('/api/reports/profit-loss', params=PERIOD).json()['net_profit']


def test_branch_summary_empty_period(client, db, w):
    _seed(db, w)
    j = client.login(w['admin']).get(SUMMARY, params={'date_from': '1990-01-01', 'date_to': '1990-01-31'}).json()
    assert j['reconciled'] is True and len(j['rows']) == 3
    assert j['total']['net_profit'] == 0 and j['total']['check_count'] == 0 and j['total']['avg_check'] == 0
    assert j['unassigned']['gross_revenue'] == 0
    assert all(r['gross_revenue'] == 0 and r['avg_check'] == 0 for r in j['rows'])


def test_branch_summary_invalid_dates_422(client, db, w):
    c = client.login(w['admin'])
    assert c.get(SUMMARY, params={'date_from': 'bad'}).status_code == 422
    assert c.get(SUMMARY, params={'date_from': '2026-02-01', 'date_to': '2026-01-01'}).status_code == 422


def test_branch_summary_period_filter(client, db, w):
    _seed(db, w)
    j = client.login(w['admin']).get(SUMMARY, params={'date_from': '2099-01-01', 'date_to': '2099-12-31'}).json()
    assert j['total']['gross_revenue'] == 0


# ── 2. Cheklangan foydalanuvchi va rollar ────────────────────────────────────

def test_restricted_manager_gets_only_own_branch(client, db, w):
    _seed(db, w)
    r = client.login(w['manager_a1']).get(SUMMARY, params=PERIOD)
    assert r.status_code == 200, r.text
    j = r.json()
    assert [x['branch_id'] for x in j['rows']] == [w['a1'].id]
    assert j['unassigned'] is None and j['total'] is None and j['reconciled'] is None
    assert j['rows'][0]['gross_revenue'] == 12000


def test_unrestricted_manager_gets_all(client, db, w):
    _seed(db, w)
    j = client.login(w['manager_all']).get(SUMMARY, params=PERIOD).json()
    assert len(j['rows']) == 3 and j['total'] is not None and j['reconciled'] is True


def test_cashier_forbidden(client, db, w):
    assert client.login(w['cashier']).get(SUMMARY, params=PERIOD).status_code == 403


# ── 3. Ikki korxona izolyatsiyasi ────────────────────────────────────────────

def test_branch_summary_company_isolation(client, db, w):
    _seed(db, w)
    j = client.login(w['admin_b']).get(SUMMARY, params=PERIOD).json()
    ids = {r['branch_id'] for r in j['rows']}
    assert ids == {w['b1'].id}
    assert w['a1'].id not in ids
    assert j['total']['gross_revenue'] == 99999 and j['reconciled'] is True
    # A korxonaning xarajati B jamida yo'q
    assert j['total']['expenses'] == 0


# ── 4. pnl-compare tarif cheklovi ────────────────────────────────────────────

def _tariff(db, company, allowed):
    t = Tariff(name=f"Tarif {next(_seq)}", has_pnl_compare=allowed)
    db.add(t)
    db.flush()
    company.tariff_id = t.id
    db.flush()
    return t


def test_pnl_compare_403_when_not_in_tariff(client, db, w):
    _seed(db, w)
    _tariff(db, w['ca'], False)
    r = client.login(w['admin']).get('/api/reports/pnl-compare', params=CMP)
    assert r.status_code == 403
    d = r.json()['detail']
    assert d['code'] == 'feature_not_in_tariff' and d['feature'] == 'pnl_compare' and d['message']
    assert 'rows' not in r.json()


def test_pnl_compare_200_when_tariff_allows(client, db, w):
    _seed(db, w)
    _tariff(db, w['ca'], True)
    r = client.login(w['admin']).get('/api/reports/pnl-compare', params=CMP)
    assert r.status_code == 200 and r.json()['has_access'] is True and r.json()['rows']


def test_pnl_compare_200_when_no_tariff(client, db, w):
    _seed(db, w)
    assert w['ca'].tariff_id is None
    r = client.login(w['admin']).get('/api/reports/pnl-compare', params=CMP)
    assert r.status_code == 200 and r.json()['has_access'] is True


def test_pnl_compare_tariff_is_per_company(client, db, w):
    _tariff(db, w['ca'], False)
    r = client.login(w['admin_b']).get('/api/reports/pnl-compare', params=CMP)   # B tarifsiz
    assert r.status_code == 200


# ── 5. 1C eksport ────────────────────────────────────────────────────────────

def _jwt(user):
    """1c-export haqiqiy Bearer token talab qiladi (get_current_user override ishlamaydi)."""
    return {'Authorization': 'Bearer ' + create_access_token(
        {'sub': str(user.id), 'company_id': user.company_id, 'role': user.role.value})}


def _customer(db, company, name):
    from app.models.customer import Customer
    c = Customer(name=name, company_id=company.id)
    db.add(c)
    db.flush()
    return c


def test_1c_csv_new_columns_and_filename(client, db, w):
    ca = w['ca']
    cust = _customer(db, ca, "Ali Valiyev")
    _sale(db, w['admin'], ca, w['prod'], w['wh1'], 5000, 1000, customer=cust)
    _sale(db, w['admin'], ca, w['prod'], w['whn'], 700, 100)
    _sale(db, w['admin_b'], w['cb'], w['prod_b'], w['whb'], 123, 1)
    c = client
    r = c.get('/api/reports/1c-export', params={**PERIOD, 'format': 'csv'}, headers=_jwt(w['admin']))
    assert r.status_code == 200, r.text
    assert r.headers['content-disposition'] == 'attachment; filename=1c_export_2020-01-01_2099-12-31.csv'
    rows = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig'))))
    assert rows[0] == ["Raqam", "Sana", "Kassir", "Jami summa", "Chegirma", "To'lov turi", "Valyuta", "Kurs",
                       "Turi", "Ombor", "Filial", "Mijoz"]
    assert len(rows) == 3                                          # B korxona sotuvi yo'q
    by_total = {x[3]: x for x in rows[1:]}
    full = by_total['5000.00']
    assert full[-3:] == [w['wh1'].name, w['a1'].name, "Ali Valiyev"]
    nobr = by_total['700.00']
    assert nobr[-3:] == [w['whn'].name, "", ""]


def test_1c_filename_with_branch_and_xml(client, db, w):
    ca = w['ca']
    _sale(db, w['admin'], ca, w['prod'], w['wh2'], 900, 100)
    c = client
    h = _jwt(w['admin'])
    r = c.get('/api/reports/1c-export', params={**PERIOD, 'format': 'xml', 'branch_id': w['a2'].id}, headers=h)
    assert r.status_code == 200
    assert r.headers['content-disposition'] == 'attachment; filename=1c_export_2020-01-01_2099-12-31_Yunusobod.xml'
    body = r.content.decode()
    assert 'warehouse="Ombor Yunusobod"' in body and 'branch="Yunusobod"' in body and 'customer=""' in body
    assert body.index('type="sale"') < body.index('warehouse=')    # eski atributlar oldin, yangilari oxirida
    r2 = c.get('/api/reports/1c-export', params={**PERIOD, 'branch_id': UNASSIGNED_BRANCH}, headers=h)
    assert r2.headers['content-disposition'].endswith('_filialsiz.csv')


def test_1c_filename_non_ascii_branch_safe(client, db, w):
    b = w['a3']
    b.name = "Чиланзар"
    db.flush()
    r = client.get('/api/reports/1c-export', params={**PERIOD, 'branch_id': b.id}, headers=_jwt(w['admin']))
    assert r.status_code == 200
    disp = r.headers['content-disposition']
    disp.encode('ascii')
    assert disp.endswith(f'_b{b.id}.csv')


# ── 6. To'lovlar ro'yxatida branch_id ────────────────────────────────────────

def _seed_payments(db, w):
    ca = w['ca']
    _tx(db, ca, w['a1'].id, 100, ref="sale")
    _tx(db, ca, w['a2'].id, 200, ref="sale")
    _tx(db, ca, None, 400, ref="sale")
    _tx(db, ca, w['a1'].id, 10, ref="expense", tx_type="expense")
    _tx(db, ca, w['a2'].id, 20, ref="expense", tx_type="expense")
    _tx(db, ca, None, 40, ref="expense", tx_type="expense")
    _tx(db, w['cb'], w['b1'].id, 8000, ref="sale")
    _tx(db, w['cb'], w['b1'].id, 80, ref="expense", tx_type="expense")


@pytest.mark.parametrize("kind,vals", [("income", (100, 200, 400)), ("expense", (10, 20, 40))])
def test_payments_branch_filter(client, db, w, kind, vals):
    _seed_payments(db, w)
    c = client.login(w['admin'])
    url = f'/api/finance/payments/{kind}'

    def amounts(**params):
        r = c.get(url, params=params)
        assert r.status_code == 200, r.text
        return sorted(i['amount'] for i in r.json()['items']), r.json()['summary']['umumiy']

    v1, v2, vn = vals
    assert amounts()[0] == sorted(vals)                               # filtrsiz: butun korxona (B kirmaydi)
    assert amounts(branch_id=w['a1'].id) == ([v1], v1)
    assert amounts(branch_id=w['a2'].id) == ([v2], v2)
    assert amounts(branch_id=UNASSIGNED_BRANCH) == ([vn], vn)
    assert amounts(branch_id=w['b1'].id)[0] == []                     # begona korxona filiali -> bo'sh


@pytest.mark.parametrize("kind", ["income", "expense"])
def test_payments_restricted_manager_scope(client, db, w, kind):
    _seed_payments(db, w)
    c = client.login(w['manager_a1'])
    url = f'/api/finance/payments/{kind}'
    r = c.get(url)
    assert r.status_code == 200
    assert len(r.json()['items']) == 1                                # faqat o'z filiali (a1)
    assert c.get(url, params={'branch_id': w['a1'].id}).status_code == 200
    assert c.get(url, params={'branch_id': w['a2'].id}).status_code == 403
    assert c.get(url, params={'branch_id': UNASSIGNED_BRANCH}).status_code == 403


# ── 7. GET /branches include_inactive ────────────────────────────────────────

def test_branches_include_inactive(client, db, w):
    w['a3'].is_active = False
    db.flush()
    c = client.login(w['admin'])
    default = {b['id'] for b in c.get('/api/branches').json()}
    assert w['a3'].id not in default
    full = c.get('/api/branches', params={'include_inactive': 'true'}).json()
    by = {b['id']: b for b in full}
    assert by[w['a3'].id]['is_active'] is False and by[w['a1'].id]['is_active'] is True
    assert w['b1'].id not in by                                       # begona korxona filiali ko'rinmaydi


# ── 8. Frontend statik tekshiruvlar ──────────────────────────────────────────

def _read(rel):
    with open(os.path.join(ROOT, *rel.split('/')), encoding='utf-8') as f:
        return f.read()


KEYS_T2_5 = ["reports.tab.branches", "reports.unassigned", "reports.companyWide", "reports.reconcileWarning", "reports.closedSuffix", "reports.pnlNotInTariff", "reports.exportLimit", "reports.exportBranch", "reports.exportPeriod", "reports.bs.title", "reports.bs.revenue", "reports.bs.debtNote"]


def _merged_i18n(keys):
    """T2.x i18n kalitlari uz/ru/en lug'atlariga birlashtirilgan (pending fayl o'chirilgan):
    {til: {kalit: qiymat}}; kalit lug'atda yo'q bo'lsa KeyError."""
    import re as _re
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'i18n'))
    out = {}
    for lang in ('uz', 'ru', 'en'):
        with open(os.path.join(base, lang + '.js'), encoding='utf-8') as f:
            txt = f.read()
        found = {m.group(1): m.group(2) for m in _re.finditer(r"^\s*'([^']+)':\s*(.+?),?\s*$", txt, _re.M)}
        out[lang] = {k: found[k] for k in keys}
    return out


def _pending():
    return _merged_i18n(KEYS_T2_5)


def test_pending_i18n_same_keys_all_languages():
    p = _pending()
    assert set(p) == {'uz', 'ru', 'en'}
    assert set(p['uz']) == set(p['ru']) == set(p['en'])
    for k in ('reports.tab.branches', 'reports.unassigned', 'reports.companyWide',
              'reports.reconcileWarning', 'reports.closedSuffix', 'reports.pnlNotInTariff', 'reports.exportLimit'):
        assert k in p['uz'], k
    assert all(v.strip() for lang in p.values() for v in lang.values())


def test_pending_keys_used_in_frontend():
    p = _pending()['uz']
    src = ''.join(_read(f'frontend/src/{f}') for f in (
        'pages/admin/Reports.jsx', 'components/BranchSelect.jsx', 'pages/admin/Operations.jsx',
        'pages/admin/Finance.jsx', 'pages/admin/Warehouse.jsx'))
    for k in p:
        assert k in src, f"{k} frontendda ishlatilmagan"


def test_export_meta_helpers_exist():
    src = _read('frontend/src/utils/exportMeta.js')
    assert 'export function exportFileName' in src and 'export function sheetHeaderRows' in src


def test_reports_wiring():
    src = _read('frontend/src/pages/admin/Reports.jsx')
    assert '/reports/branch-summary' in src
    # C4.3: filiallar yagona hookdan (nofaollari ham) — api.get('/branches', include_inactive) o'rniga
    assert 'include_inactive' in src or 'useBranches({ includeInactive: true })' in src
    assert 'feature_not_in_tariff' in src
    assert 'SALES_EXPORT_LIMIT = 5000' in src and "limit: String(SALES_EXPORT_LIMIT)" in src
    assert 'truncated' in src and "'/reports/sales" in src.replace('`/reports/sales', "'/reports/sales")
    assert ("params: { include_inactive: true }" in src or 'useBranches({ includeInactive: true })' in src)         and 'filter(b => b.is_active)' not in src
    assert 'BranchSelect' in src and "tab === 'branches'" in src
    assert 'reconciled === false' in src
    assert 'exportFileName' in src and 'sheetHeaderRows' in src
    assert 'sotuvlar_${today()}' not in src and 'kassir_${today()}' not in src


def test_operations_tabs_accept_branches():
    src = _read('frontend/src/pages/admin/Operations.jsx')
    # T3.8: o'lik SalesTab / KirimlarTab Operations.jsx dan olib tashlandi; qolgan tablar filial tanlovini ishlatadi
    assert 'function SalesTab' not in src and 'function KirimlarTab' not in src
    assert 'BranchSelect' in src and 'allWarehouses' in src


def test_warehouse_export_name_uses_helper():
    src = _read('frontend/src/pages/admin/Warehouse.jsx')
    assert 'exportFileName' in src and 'ombor_${today()}' not in src


def test_finance_uses_branch_select_and_closed_branches():
    src = _read('frontend/src/pages/admin/Finance.jsx')
    assert 'BranchSelect' in src and 'include_inactive' in src and 'branch_id=${branchFilter}' in src


def test_branch_select_variants():
    src = _read('frontend/src/components/BranchSelect.jsx')
    assert 'value="-1"' in src or "UNASSIGNED_VALUE = '-1'" in src
    assert 'canSelectAll' in src                        # Filialsiz faqat cheklanmagan foydalanuvchiga
    assert 'reports.closedSuffix' in src and 'is_active === false' in src


def test_export_file_name_contract_in_source():
    """exportFileName: prefix[_filial]_davr.ext; maxsus belgilar almashtiriladi (node yo'q — manba tekshiruvi)."""
    src = _read('frontend/src/utils/exportMeta.js')
    assert "parts.join('_')" in src and 'safePart(branchName)' in src
    assert r"replace(/\s+/g, '_')" in src
